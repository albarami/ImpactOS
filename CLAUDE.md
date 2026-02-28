# CLAUDE.md — ImpactOS Project Instructions

## What is This Project?
ImpactOS is an internal Impact & Scenario Intelligence System for Strategic Gears (Saudi consulting firm). It industrializes Leontief input-output economic modeling with AI-assisted scenario compilation and audit-grade governance (No Free Facts).

## Architecture Reference
- Full tech spec: `docs/ImpactOS_Technical_Specification_v1_0.md`
- Concept document: `docs/ImpactOS_Comprehensive_Project_Document_v3.md`
- Data/API requirements: `docs/ImpactOS_Data_Sources_APIs_BuildPack_v1.0.md`

## The One Rule That Cannot Be Broken
**Agent-to-Math Boundary:** AI components produce structured JSON only. The deterministic engine in `src/engine/` performs ALL numerical computations. AI never computes, modifies, or generates economic results. This separation is what makes the system auditable and trustworthy.

## Project Structure
```
src/
├── engine/       # Deterministic I-O computation (NumPy/SciPy) — NO LLM calls here
├── compiler/     # Scenario Compiler: doc → shock mapping
├── ingestion/    # Document extraction, BoQ structuring
├── governance/   # NFF: claims, evidence, assumptions, publication gate
├── agents/       # Al-Muhāsibī Depth Engine, AI drafting agents
├── api/          # FastAPI endpoints
├── models/       # Pydantic schemas (source of truth for all data structures)
└── export/       # Decision Pack generation (PPT/Excel/PDF)
tests/            # Mirrors src/ structure
```

## Development Rules
1. **Test first.** Write failing test → write code → pass test → commit. Always.
2. **Schema first.** Define Pydantic models before writing service logic.
3. **Read the spec.** Before building a component, read the relevant tech spec section.
4. **Type everything.** All functions have type hints. No `any`.
5. **Commit often.** Format: `[component] brief description`
6. **No secrets in code.** Use .env and environment variables.

## Tech Stack
- Python 3.11+, FastAPI, Pydantic v2
- NumPy/SciPy (engine only)
- PostgreSQL + pgvector
- S3-compatible object storage
- Redis/Celery for job queues
- React/Next.js frontend (later phases)

## Key Pydantic Models (src/models/)
These are the core entities — build everything around them:
- `ModelVersion` (immutable)
- `ScenarioSpec` (versioned)
- `RunSnapshot` (immutable)
- `ResultSet` (immutable)
- `Assumption` (versioned, governed)
- `Claim` (versioned, governed)
- `EvidenceSnippet` (immutable)
- `Workspace` (isolation boundary)
- `ShockItem` (union type: FinalDemandShock | ImportSubstitution | LocalContent | ConstraintOverride)

## Current Phase: MVP (Phase 1)
Build order per tech spec Section 16.1:
1. MVP-1: Workspace/RBAC + document ingestion + object storage + audit logging
2. MVP-2: Extraction pipeline + BoQ structuring + EvidenceSnippet generation
3. MVP-3: Deterministic I-O engine + ModelVersion management + batch runs
4. MVP-4: HITL reconciliation UI + mapping state machine + ScenarioSpec versioning
5. MVP-5: NFF governance MVP + sandbox/governed gate
6. MVP-6: Reporting/export engine + Excel escape hatch + watermarking
7. MVP-7: Pilot enablement
