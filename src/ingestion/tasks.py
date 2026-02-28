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
from src.models.document import LanguageCode

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
    status = "RUNNING"

    # Update job to RUNNING
    if job_repo is not None:
        await job_repo.update_status(job_id, "RUNNING")

    try:
        # Select provider based on classification + MIME type
        provider = router.select_provider(classification, mime_type)
        logger.info(
            "Extraction job %s: using provider %s for %s [%s]",
            job_id, provider.name, mime_type, classification,
        )

        # Extract document → DocumentGraph
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
            # If Azure DI fails, fall back to local PDF
            if provider.name == "azure-di":
                logger.warning(
                    "Azure DI failed for job %s, falling back to local-pdf: %s",
                    job_id, exc,
                )
                from src.ingestion.providers.local_pdf import LocalPdfProvider
                fallback = LocalPdfProvider()
                graph = await fallback.extract(
                    document_bytes, mime_type, doc_id, options,
                )
            else:
                raise

        # Generate evidence snippets
        snippets = _extraction_service.generate_evidence_snippets(
            document_graph=graph,
            source_id=doc_id,
            doc_checksum=doc_checksum,
        )

        # Structure BoQ line items
        if extract_line_items and line_item_repo is not None:
            items = _boq_pipeline.structure(
                document_graph=graph,
                evidence_snippets=snippets,
                extraction_job_id=job_id,
            )
            line_item_dicts = []
            for item in items:
                d = item.model_dump()
                d["evidence_snippet_ids"] = [str(uid) for uid in d["evidence_snippet_ids"]]
                line_item_dicts.append(d)
            await line_item_repo.create_many(line_item_dicts)

        status = "COMPLETED"

    except Exception as exc:
        logger.exception("Extraction job %s failed: %s", job_id, exc)
        status = "FAILED"
        error_message = str(exc)

    # Update job status
    if job_repo is not None:
        await job_repo.update_status(job_id, status, error_message=error_message)

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

    async def _run():
        async with async_session_factory() as session:
            job_repo = ExtractionJobRepository(session)
            line_item_repo = LineItemRepository(session)

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
    task = app.task(name="impactos.extract")(_celery_extract_task)
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
