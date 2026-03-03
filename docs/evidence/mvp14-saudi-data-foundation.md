# MVP-14 Saudi Data Foundation Evidence

## Scope

This artifact records Sprint 14 completion evidence for:

- extended `ModelData` persistence fields for Phase 2-E prerequisites,
- deterministic artifact checksum behavior,
- strict fail-closed validation for malformed Saudi IO artifacts,
- additive API compatibility for model detail retrieval.

## Required Checks

- Migration `011_model_data_extended_fields` applied successfully.
- `POST /v1/engine/models` accepts valid extended fields.
- Invalid extended fields return HTTP `422` with stable `reason_code`.
- `GET /v1/workspaces/{workspace_id}/models/versions/{model_version_id}` returns additive extended fields.
- Targeted tests for loader/db/api/docs pass.

## Verification Commands

```bash
python -m pytest tests/data/test_io_loader.py tests/db/test_tables.py tests/api/test_models.py tests/data/test_mvp14_evidence.py -q
python -m alembic upgrade head
python -m alembic check
python -m ruff check src tests
```
