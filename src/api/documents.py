"""FastAPI document endpoints — MVP-2 Section 6.2.5.

POST /v1/workspaces/{workspace_id}/documents               — upload
POST /v1/workspaces/{workspace_id}/documents/{doc_id}/extract  — trigger extraction
GET  /v1/workspaces/{workspace_id}/jobs/{job_id}           — job status
GET  /v1/workspaces/{workspace_id}/documents/{doc_id}/line-items — extracted items

This is a deterministic pipeline — no LLM calls.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from src.api.dependencies import (
    get_document_repo,
    get_extraction_job_repo,
    get_line_item_repo,
)
from src.models.common import DataClassification
from src.models.document import (
    BoQLineItem,
    DocumentType,
    ExtractionJob,
    ExtractionStatus,
    LanguageCode,
    SourceType,
)
from src.ingestion.boq_structuring import BoQStructuringPipeline
from src.ingestion.extraction import ExtractionService
from src.ingestion.storage import DocumentStorageService
from src.repositories.documents import (
    DocumentRepository,
    ExtractionJobRepository,
    LineItemRepository,
)

router = APIRouter(prefix="/v1/workspaces", tags=["documents"])

# ---------------------------------------------------------------------------
# Stateless services (no DB needed)
# ---------------------------------------------------------------------------

_storage = DocumentStorageService(storage_root="./uploads")
_extraction_service = ExtractionService()
_boq_pipeline = BoQStructuringPipeline()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class ExtractRequest(BaseModel):
    extract_tables: bool = True
    extract_line_items: bool = True
    language_hint: str = "en"


class UploadResponse(BaseModel):
    doc_id: str
    status: str
    hash_sha256: str


class ExtractResponse(BaseModel):
    job_id: str
    status: str


class JobStatusResponse(BaseModel):
    job_id: str
    doc_id: str
    status: str
    error_message: str | None = None


class LineItemsResponse(BaseModel):
    items: list[BoQLineItem]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/{workspace_id}/documents", status_code=201, response_model=UploadResponse)
async def upload_document(
    workspace_id: UUID,
    doc_repo: DocumentRepository = Depends(get_document_repo),
    file: UploadFile = File(...),
    doc_type: str = Form(...),
    source_type: str = Form(...),
    classification: str = Form(...),
    language: str = Form("en"),
    uploaded_by: str = Form(...),
) -> UploadResponse:
    """Upload a document (Section 6.2.5)."""
    content = await file.read()

    if len(content) == 0:
        raise HTTPException(status_code=422, detail="File content must not be empty.")

    doc = _storage.upload(
        workspace_id=workspace_id,
        filename=file.filename or "unknown",
        content=content,
        mime_type=file.content_type or "application/octet-stream",
        uploaded_by=UUID(uploaded_by),
        doc_type=DocumentType(doc_type),
        source_type=SourceType(source_type),
        classification=DataClassification(classification),
        language=LanguageCode(language),
    )

    # Persist document metadata to DB
    await doc_repo.create(
        doc_id=doc.doc_id,
        workspace_id=doc.workspace_id,
        filename=doc.filename,
        mime_type=doc.mime_type,
        size_bytes=doc.size_bytes,
        hash_sha256=doc.hash_sha256,
        storage_key=doc.storage_key,
        uploaded_by=doc.uploaded_by,
        doc_type=doc.doc_type.value,
        source_type=doc.source_type.value,
        classification=doc.classification.value,
        language=doc.language.value,
    )

    return UploadResponse(
        doc_id=str(doc.doc_id),
        status="stored",
        hash_sha256=doc.hash_sha256,
    )


@router.post(
    "/{workspace_id}/documents/{doc_id}/extract",
    status_code=202,
    response_model=ExtractResponse,
)
async def extract_document(
    workspace_id: UUID,
    doc_id: UUID,
    body: ExtractRequest,
    doc_repo: DocumentRepository = Depends(get_document_repo),
    job_repo: ExtractionJobRepository = Depends(get_extraction_job_repo),
    line_item_repo: LineItemRepository = Depends(get_line_item_repo),
) -> ExtractResponse:
    """Trigger extraction (Section 6.2.5). Runs synchronously for MVP."""
    doc_row = await doc_repo.get(doc_id)
    if doc_row is None:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found.")

    job = ExtractionJob(
        doc_id=doc_id,
        workspace_id=workspace_id,
        extract_tables=body.extract_tables,
        extract_line_items=body.extract_line_items,
        language_hint=LanguageCode(body.language_hint) if body.language_hint else LanguageCode.EN,
    )

    # For MVP, run extraction synchronously
    try:
        content = _storage.retrieve(doc_row.storage_key)

        # Determine extraction method from MIME type
        mime = doc_row.mime_type.lower()
        if "csv" in mime or doc_row.filename.endswith(".csv"):
            graph = _extraction_service.extract_csv(
                doc_id=doc_id, content=content, doc_checksum=doc_row.hash_sha256,
            )
        elif "spreadsheet" in mime or "excel" in mime or doc_row.filename.endswith((".xlsx", ".xls")):
            graph = _extraction_service.extract_excel(
                doc_id=doc_id, content=content, doc_checksum=doc_row.hash_sha256,
            )
        else:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported file type: {doc_row.mime_type}",
            )

        snippets = _extraction_service.generate_evidence_snippets(
            document_graph=graph, source_id=doc_id, doc_checksum=doc_row.hash_sha256,
        )

        if body.extract_line_items:
            items = _boq_pipeline.structure(
                document_graph=graph,
                evidence_snippets=snippets,
                extraction_job_id=job.job_id,
            )
            # Persist line items to DB
            line_item_dicts = []
            for item in items:
                d = item.model_dump()
                # Convert UUID list to string list for JSON storage
                d["evidence_snippet_ids"] = [str(uid) for uid in d["evidence_snippet_ids"]]
                line_item_dicts.append(d)
            await line_item_repo.create_many(line_item_dicts)

        job = job.model_copy(update={"status": ExtractionStatus.COMPLETED})

    except HTTPException:
        raise
    except Exception as exc:
        job = job.model_copy(update={
            "status": ExtractionStatus.FAILED,
            "error_message": str(exc),
        })

    # Persist job to DB
    await job_repo.create(
        job_id=job.job_id,
        doc_id=job.doc_id,
        workspace_id=job.workspace_id,
        status=job.status.value,
        extract_tables=job.extract_tables,
        extract_line_items=job.extract_line_items,
        language_hint=job.language_hint.value if isinstance(job.language_hint, LanguageCode) else str(job.language_hint),
        error_message=job.error_message,
    )

    return ExtractResponse(
        job_id=str(job.job_id),
        status=job.status.value,
    )


@router.get("/{workspace_id}/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    workspace_id: UUID,
    job_id: UUID,
    job_repo: ExtractionJobRepository = Depends(get_extraction_job_repo),
) -> JobStatusResponse:
    """Poll job status (Section 6.2.5)."""
    row = await job_repo.get(job_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    return JobStatusResponse(
        job_id=str(row.job_id),
        doc_id=str(row.doc_id),
        status=row.status,
        error_message=row.error_message,
    )


@router.get(
    "/{workspace_id}/documents/{doc_id}/line-items",
    response_model=LineItemsResponse,
)
async def get_line_items(
    workspace_id: UUID,
    doc_id: UUID,
    line_item_repo: LineItemRepository = Depends(get_line_item_repo),
) -> LineItemsResponse:
    """Get extracted line items for a document."""
    rows = await line_item_repo.get_by_doc(doc_id)
    items = [
        BoQLineItem(
            line_item_id=r.line_item_id,
            doc_id=r.doc_id,
            extraction_job_id=r.extraction_job_id,
            raw_text=r.raw_text,
            description=r.description or "",
            quantity=r.quantity,
            unit=r.unit,
            unit_price=r.unit_price,
            total_value=r.total_value,
            currency_code=r.currency_code,
            year_or_phase=r.year_or_phase,
            vendor=r.vendor,
            category_code=r.category_code,
            page_ref=r.page_ref,
            evidence_snippet_ids=[UUID(s) for s in (r.evidence_snippet_ids or [])],
            completeness_score=r.completeness_score,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return LineItemsResponse(items=items)
