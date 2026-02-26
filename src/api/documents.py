"""FastAPI document endpoints — MVP-2 Section 6.2.5.

POST /v1/workspaces/{workspace_id}/documents               — upload
POST /v1/workspaces/{workspace_id}/documents/{doc_id}/extract  — trigger extraction
GET  /v1/workspaces/{workspace_id}/jobs/{job_id}           — job status
GET  /v1/workspaces/{workspace_id}/documents/{doc_id}/line-items — extracted items

This is a deterministic pipeline — no LLM calls.
In-memory stores are used here for MVP; production will use PostgreSQL.
"""

from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from src.models.common import DataClassification
from src.models.document import (
    BoQLineItem,
    Document,
    DocumentType,
    ExtractionJob,
    ExtractionStatus,
    LanguageCode,
    SourceType,
)
from src.ingestion.boq_structuring import BoQStructuringPipeline
from src.ingestion.extraction import ExtractionService
from src.ingestion.storage import DocumentStorageService

router = APIRouter(prefix="/v1/workspaces", tags=["documents"])

# ---------------------------------------------------------------------------
# In-memory stores (MVP only — will be replaced by PostgreSQL)
# ---------------------------------------------------------------------------

_storage = DocumentStorageService(storage_root="./uploads")
_extraction_service = ExtractionService()
_boq_pipeline = BoQStructuringPipeline()

# doc_id -> Document
_documents: dict[UUID, Document] = {}
# job_id -> ExtractionJob
_jobs: dict[UUID, ExtractionJob] = {}
# doc_id -> list[BoQLineItem]
_line_items: dict[UUID, list[BoQLineItem]] = {}


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

    _documents[doc.doc_id] = doc

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
) -> ExtractResponse:
    """Trigger extraction (Section 6.2.5). Runs synchronously for MVP."""
    doc = _documents.get(doc_id)
    if doc is None:
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
        content = _storage.retrieve(doc.storage_key)

        # Determine extraction method from MIME type
        mime = doc.mime_type.lower()
        if "csv" in mime or doc.filename.endswith(".csv"):
            graph = _extraction_service.extract_csv(
                doc_id=doc_id, content=content, doc_checksum=doc.hash_sha256,
            )
        elif "spreadsheet" in mime or "excel" in mime or doc.filename.endswith((".xlsx", ".xls")):
            graph = _extraction_service.extract_excel(
                doc_id=doc_id, content=content, doc_checksum=doc.hash_sha256,
            )
        else:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported file type: {doc.mime_type}",
            )

        snippets = _extraction_service.generate_evidence_snippets(
            document_graph=graph, source_id=doc_id, doc_checksum=doc.hash_sha256,
        )

        if body.extract_line_items:
            items = _boq_pipeline.structure(
                document_graph=graph,
                evidence_snippets=snippets,
                extraction_job_id=job.job_id,
            )
            _line_items[doc_id] = items

        job = job.model_copy(update={"status": ExtractionStatus.COMPLETED})

    except HTTPException:
        raise
    except Exception as exc:
        job = job.model_copy(update={
            "status": ExtractionStatus.FAILED,
            "error_message": str(exc),
        })

    _jobs[job.job_id] = job

    return ExtractResponse(
        job_id=str(job.job_id),
        status=job.status.value,
    )


@router.get("/{workspace_id}/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    workspace_id: UUID,
    job_id: UUID,
) -> JobStatusResponse:
    """Poll job status (Section 6.2.5)."""
    job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found.")

    return JobStatusResponse(
        job_id=str(job.job_id),
        doc_id=str(job.doc_id),
        status=job.status.value,
        error_message=job.error_message,
    )


@router.get(
    "/{workspace_id}/documents/{doc_id}/line-items",
    response_model=LineItemsResponse,
)
async def get_line_items(
    workspace_id: UUID,
    doc_id: UUID,
) -> LineItemsResponse:
    """Get extracted line items for a document."""
    items = _line_items.get(doc_id, [])
    return LineItemsResponse(items=items)
