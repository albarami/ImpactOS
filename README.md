# ImpactOS

**Internal Impact & Scenario Intelligence System for Strategic Gears**

ImpactOS industrializes Leontief input-output economic modeling for consulting engagements. It transforms weeks-long impact studies into a governed, repeatable process that delivers 20+ scenarios instead of 2-3, with audit-grade traceability on every number.

## What It Does

- **Scenario Compiler:** Converts project documents (BoQs, CAPEX plans, procurement schedules) into defensible demand shocks with confidence scoring and human-in-the-loop review.
- **Deterministic I-O Engine:** Computes Leontief impacts, multipliers, and satellite accounts (jobs, imports, value added) with full reproducibility.
- **No Free Facts Governance:** Every claim in a deliverable must be model-derived, source-backed, or an explicit assumption — otherwise it's blocked from export.
- **AI-Powered Mapping:** Library-based + LLM-assisted sector mapping with learning loop for continuous improvement.
- **Decision Pack Export:** Auto-generated deck-ready outputs with charts, tables, narratives, and evidence appendices.

## Architecture

```
Deterministic Core (NumPy/SciPy)     <-->    AI Layer (LLM agents)
         |                                        |
    Matrix math only                    Structured JSON only
    Reproducible                        Schema-validated
    Auditable                           Never computes results
         |                                        |
              --> Governance Gate (NFF) -->
                       |
              Decision Pack Export
```

**Critical boundary:** AI components propose; the deterministic engine computes. AI never generates economic results.

## Quick Start

```bash
git clone https://github.com/albarami/ImpactOS.git
cd ImpactOS
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
make up        # Start Postgres, Redis, MinIO
make migrate   # Create database tables
make seed      # Load sample IO model + BoQ
make serve     # API at http://localhost:8000/docs
```

See [docs/LOCAL_RUNBOOK.md](docs/LOCAL_RUNBOOK.md) for detailed setup instructions.

## Project Status

| Component | Tests | Status |
|-----------|-------|--------|
| MVP-1: Foundation (schemas, API, config) | 60 | Done |
| MVP-2: Document Ingestion Pipeline | 88 | Done |
| MVP-3: Deterministic I-O Engine | 83 | Done |
| MVP-4: HITL Reconciliation + Scenario Compiler | 99 | Done |
| MVP-5: No Free Facts Governance | 102 | Done |
| MVP-6: Reporting/Export Engine | 74 | Done |
| MVP-7: Pilot Enablement + Observability | 73 | Done |
| MVP-8: AI-Powered Scenario Compiler | 103 | Done |
| S0-1: Repository Layer + Persistence | 838 | Done |
| S0-2: Docker Compose + Local Runtime | 852+ | Done |

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, Pydantic v2
- **Computation:** NumPy, SciPy
- **Database:** PostgreSQL 16 + pgvector, SQLAlchemy 2.0+, Alembic
- **Queue:** Redis 7, Celery
- **Storage:** MinIO (S3-compatible)
- **AI:** Anthropic Claude, OpenAI (via enterprise ZDR endpoints)
- **Frontend:** React/Next.js (Phase 2+)

## Documentation

- [Local Development Runbook](docs/LOCAL_RUNBOOK.md)
- [Comprehensive Project Document](docs/ImpactOS_Comprehensive_Project_Document_v3.md)
- [Technical Specification](docs/ImpactOS_Technical_Specification_v1_0.md)
- [Data & API Requirements](docs/ImpactOS_Data_Sources_APIs_BuildPack_v1.0.md)

## Development

```bash
make test    # Run tests (no Docker needed — uses aiosqlite)
make lint    # Run ruff + mypy
make fmt     # Auto-format code
```

## License

Proprietary — Strategic Gears Internal Use Only.

Al-Muhāsibī Depth Engine methodology © Salim Al-Barami. Licensed to Strategic Gears under separate terms.
