"""Celery async tasks for document extraction — S0-3.

When CELERY_BROKER_URL is configured, extraction runs in a Celery worker.
When empty (dev/test), extraction runs synchronously inline.

The run_extraction function contains the shared orchestration logic
used by both sync and async paths.
"""

import asyncio
import logging
from uuid import UUID

from src.config.settings import get_settings
from src.ingestion.boq_structuring import BoQStructuringPipeline
from src.ingestion.extraction import ExtractionService
from src.ingestion.providers.base import ExtractionOptions
from src.ingestion.providers.router import ExtractionRouter

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Celery app (lazy init — only created if broker URL is configured)
# ---------------------------------------------------------------------------

_celery_app = None


def get_celery_app():
    """Get or create the Celery application."""
    global _celery_app
    if _celery_app is None:
        from celery import Celery

        settings = get_settings()
        broker_url = settings.CELERY_BROKER_URL or settings.REDIS_URL
        _celery_app = Celery(
            "impactos",
            broker=broker_url,
            backend=broker_url,
        )
        _celery_app.conf.task_serializer = "json"
        _celery_app.conf.result_serializer = "json"
    return _celery_app


# ---------------------------------------------------------------------------
# Shared extraction orchestration
# ---------------------------------------------------------------------------

_extraction_service = ExtractionService()
_boq_pipeline = BoQStructuringPipeline()


async def run_extraction(
    *,
    job_id: UUID,
    doc_id: UUID,
    workspace_id: UUID,
    document_bytes: bytes,
    mime_type: str,
    filename: str,
    classification: str,
    doc_checksum: str,
    extract_tables: bool = True,
    extract_line_items: bool = True,
    language_hint: str = "en",
    job_repo=None,
    line_item_repo=None,
    evidence_snippet_repo=None,
) -> str:
    """Run the full extraction pipeline.

    This is the core orchestration function called by both the sync path
    (inline in the API endpoint) and the async path (Celery task).

    Returns:
        Final job status string ("COMPLETED" or "FAILED").
    """
    settings = get_settings()
    router = ExtractionRouter(
        azure_di_endpoint=settings.AZURE_DI_ENDPOINT,
        azure_di_key=settings.AZURE_DI_KEY,
    )

    error_message: str | None = None
    error_code: str | None = None
    provider_name: str | None = None
    fallback_provider_name: str | None = None
    status = "RUNNING"

    if job_repo is not None:
        await job_repo.update_status(job_id, "RUNNING")

    try:
        provider = router.select_provider(
            classification, mime_type,
            environment=settings.ENVIRONMENT,
        )
        provider_name = provider.name
        logger.info(
            "Extraction job %s: using provider %s for %s [%s]",
            job_id, provider_name, mime_type, classification,
        )

        options = ExtractionOptions(
            extract_tables=extract_tables,
            extract_line_items=extract_line_items,
            language_hint=language_hint,
            doc_checksum=doc_checksum,
        )

        try:
            graph = await provider.extract(
                document_bytes, mime_type, doc_id, options,
            )
        except Exception as exc:
            is_non_dev = settings.ENVIRONMENT in ("staging", "prod")
            if provider.name == "azure-di" and not is_non_dev:
                logger.warning(
                    "Azure DI failed for job %s, falling back to "
                    "local-pdf (dev only): %s", job_id, exc,
                )
                from src.ingestion.providers.local_pdf import (
                    LocalPdfProvider,
                )
                fallback = LocalPdfProvider()
                fallback_provider_name = fallback.name
                graph = await fallback.extract(
                    document_bytes, mime_type, doc_id, options,
                )
            else:
                raise

        snippets = _extraction_service.generate_evidence_snippets(
            document_graph=graph,
            source_id=doc_id,
            doc_checksum=doc_checksum,
        )

        # Idempotent persistence: clear previous job artifacts before insert
        if line_item_repo is not None:
            await line_item_repo.delete_by_job(job_id)

        if evidence_snippet_repo is not None and snippets:
            snippet_dicts = []
            for s in snippets:
                snippet_dicts.append({
                    "snippet_id": s.snippet_id,
                    "source_id": s.source_id,
                    "page": s.page,
                    "bbox_x0": s.bbox.x0,
                    "bbox_y0": s.bbox.y0,
                    "bbox_x1": s.bbox.x1,
                    "bbox_y1": s.bbox.y1,
                    "extracted_text": s.extracted_text,
                    "table_cell_ref": (
                        s.table_cell_ref.model_dump()
                        if s.table_cell_ref else None
                    ),
                    "checksum": s.checksum,
                })
            await evidence_snippet_repo.create_many(snippet_dicts)

        if extract_line_items and line_item_repo is not None:
            items = _boq_pipeline.structure(
                document_graph=graph,
                evidence_snippets=snippets,
                extraction_job_id=job_id,
            )
            line_item_dicts = []
            for item in items:
                d = item.model_dump()
                d["evidence_snippet_ids"] = [
                    str(uid) for uid in d["evidence_snippet_ids"]
                ]
                line_item_dicts.append(d)
            await line_item_repo.create_many(line_item_dicts)

        status = "COMPLETED"

    except Exception as exc:
        logger.exception("Extraction job %s failed: %s", job_id, exc)
        status = "FAILED"
        error_message = str(exc)
        error_code = type(exc).__name__

    if job_repo is not None:
        await job_repo.update_status(
            job_id, status,
            error_message=error_message,
            error_code=error_code,
            provider_name=provider_name,
            fallback_provider_name=fallback_provider_name,
        )
        if status == "FAILED":
            await job_repo.increment_attempt(job_id)

    if status == "FAILED" and error_message is not None:
        raise RuntimeError(error_message)

    return status


# ---------------------------------------------------------------------------
# Celery task wrapper
# ---------------------------------------------------------------------------


def _celery_extract_task(
    job_id_str: str,
    doc_id_str: str,
    workspace_id_str: str,
    document_bytes_hex: str,
    mime_type: str,
    filename: str,
    classification: str,
    doc_checksum: str,
    extract_tables: bool,
    extract_line_items: bool,
    language_hint: str,
) -> str:
    """Celery task that runs extraction in a worker process.

    Creates its own async session and runs the orchestration function.
    All UUIDs/bytes are serialized as strings for JSON transport.
    """
    from src.db.session import async_session_factory
    from src.repositories.documents import ExtractionJobRepository, LineItemRepository
    from src.repositories.governance import EvidenceSnippetRepository

    async def _run():
        async with async_session_factory() as session:
            job_repo = ExtractionJobRepository(session)
            line_item_repo = LineItemRepository(session)
            evidence_snippet_repo = EvidenceSnippetRepository(session)

            result = await run_extraction(
                job_id=UUID(job_id_str),
                doc_id=UUID(doc_id_str),
                workspace_id=UUID(workspace_id_str),
                document_bytes=bytes.fromhex(document_bytes_hex),
                mime_type=mime_type,
                filename=filename,
                classification=classification,
                doc_checksum=doc_checksum,
                extract_tables=extract_tables,
                extract_line_items=extract_line_items,
                language_hint=language_hint,
                job_repo=job_repo,
                line_item_repo=line_item_repo,
                evidence_snippet_repo=evidence_snippet_repo,
            )

            await session.commit()
            return result

    return asyncio.run(_run())


def dispatch_extraction(
    *,
    job_id: UUID,
    doc_id: UUID,
    workspace_id: UUID,
    document_bytes: bytes,
    mime_type: str,
    filename: str,
    classification: str,
    doc_checksum: str,
    extract_tables: bool = True,
    extract_line_items: bool = True,
    language_hint: str = "en",
) -> None:
    """Dispatch extraction to Celery worker.

    Serializes all arguments as JSON-safe types for Celery transport.
    """
    app = get_celery_app()
    task = app.task(
        name="impactos.extract",
        autoretry_for=(Exception,),
        retry_backoff=True,
        retry_backoff_max=300,
        max_retries=3,
    )(_celery_extract_task)
    task.delay(
        str(job_id),
        str(doc_id),
        str(workspace_id),
        document_bytes.hex(),
        mime_type,
        filename,
        classification,
        doc_checksum,
        extract_tables,
        extract_line_items,
        language_hint,
    )
