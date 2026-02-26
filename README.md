# ImpactOS

**Internal Impact & Scenario Intelligence System for Strategic Gears**

ImpactOS industrializes Leontief input-output economic modeling for consulting engagements. It transforms weeks-long impact studies into a governed, repeatable process that delivers 20+ scenarios instead of 2–3, with audit-grade traceability on every number.

## What It Does

- **Scenario Compiler:** Converts project documents (BoQs, CAPEX plans, procurement schedules) into defensible demand shocks with confidence scoring and human-in-the-loop review.
- **Deterministic I-O Engine:** Computes Leontief impacts, multipliers, and satellite accounts (jobs, imports, value added) with full reproducibility.
- **No Free Facts Governance:** Every claim in a deliverable must be model-derived, source-backed, or an explicit assumption — otherwise it's blocked from export.
- **Al-Muhāsibī Depth Engine:** Structured red-teaming and contrarian scenario generation producing auditable artifacts.
- **Decision Pack Export:** Auto-generated deck-ready outputs with charts, tables, narratives, and evidence appendices.

## Architecture

```
Deterministic Core (NumPy/SciPy)     ←→    AI Layer (LLM agents)
         ↓                                        ↓
    Matrix math only                    Structured JSON only
    Reproducible                        Schema-validated
    Auditable                           Never computes results
         ↓                                        ↓
              → Governance Gate (NFF) →
                       ↓
              Decision Pack Export
```

**Critical boundary:** AI components propose; the deterministic engine computes. AI never generates economic results.

## Tech Stack

- **Backend:** Python 3.11+, FastAPI, Pydantic v2
- **Computation:** NumPy, SciPy
- **Database:** PostgreSQL, pgvector
- **Queue:** Redis, Celery
- **AI:** Anthropic Claude, OpenAI (via enterprise ZDR endpoints)
- **Frontend:** React/Next.js (Phase 2+)

## Project Status

**Phase 1 (MVP)** — In Development

## Documentation

- [Concept Document](docs/concept_document_v3.md)
- [Technical Specification](docs/technical_specification_v1.md)
- [Data & API Requirements](docs/data_and_api_requirements.md)

## Setup

```bash
# Clone
git clone https://github.com/albarami/ImpactOS.git
cd ImpactOS

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install dependencies
pip install -e ".[dev]"

# Copy environment config
cp .env.example .env
# Edit .env with your API keys

# Run tests
pytest

# Start development server
uvicorn src.api.main:app --reload
```

## License

Proprietary — Strategic Gears Internal Use Only.

Al-Muhāsibī Depth Engine methodology © Salim Al-Barami. Licensed to Strategic Gears under separate terms.
