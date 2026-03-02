# Phase 3A Frontend Design — ImpactOS

**Date:** 2026-03-01
**Scope:** F-0 through F-6A (existing backend endpoints only)
**Stack:** Next.js 14+ App Router, TypeScript strict, Tailwind CSS, shadcn/ui, TanStack Query, Zustand, openapi-fetch, Recharts, Vitest

## Architecture Principles

### Data Flow
```
URL params (canonical IDs) → Server Component (initial fetch/layout)
                                       ↓
                              Client Component (interactivity)
                                       ↕
                              TanStack Query (server state cache)
                                       ↕
                              Zustand (UI-local state only)
```

### Rules
- **Server Components** for page shells, initial data loads, static layouts
- **Client Components** for forms, tables, polling, interactive elements
- **TanStack Query** = source of truth for all backend data
- **Zustand** = panel state, unsaved drafts, filter toggles, sidebar collapse — NOT entity data
- **URL** = source of truth for entity IDs (workspaceId, docId, compilationId, scenarioId, runId, exportId)
- **Generated openapi-fetch client** for every API call — zero hand-written fetch
- **Workspace ID**: `NEXT_PUBLIC_DEV_WORKSPACE_ID` env var for Phase 3A, centralized in one utility, fail-fast at boot if missing

### Route Structure
```
/login
/w/[workspaceId]/
  ├── documents/
  │   ├── page.tsx                    # Upload + recent
  │   └── [docId]/
  │       ├── page.tsx                # Line items after extraction
  │       └── compile/page.tsx        # Compile config → trigger
  ├── compilations/
  │   └── [compilationId]/
  │       └── page.tsx                # Decision review table
  ├── scenarios/
  │   ├── page.tsx                    # Create form
  │   └── [scenarioId]/
  │       └── page.tsx                # Compile + details
  ├── runs/
  │   └── [runId]/
  │       └── page.tsx                # Results + charts
  ├── governance/
  │   └── [runId]/
  │       └── page.tsx                # Status + claims + assumptions
  └── exports/
      ├── new/page.tsx                # Request form (?runId= query param)
      └── [exportId]/
          └── page.tsx                # Status + download
```

## API Client Architecture

### Generated Client
```typescript
// src/lib/api/client.ts
import createClient from 'openapi-fetch';
import type { paths } from './schema';

export const api = createClient<paths>({
  baseUrl: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000',
});
```

### Workspace Scoping
```typescript
// src/lib/api/workspace.ts
export function getWorkspaceId(): string {
  // In browser: read from URL params
  // Fallback: NEXT_PUBLIC_DEV_WORKSPACE_ID
  // Fail-fast if neither available
}
```

### TanStack Query Hooks
One hook file per domain in `src/lib/api/hooks/`:
- `useDocuments.ts` — upload, extract, job status, line items
- `useCompiler.ts` — compile, status, decisions
- `useScenarios.ts` — create, compile, versions, lock, mapping decisions
- `useRuns.ts` — create run, get results, batch
- `useGovernance.ts` — extract claims, NFF check, assumptions, status, blocking reasons
- `useExports.ts` — create, status, variance bridge

## Sprint Designs

### F-0: API Contract Freeze

**Deliverables:**
1. `openapi.json` — exported from running backend
2. `docs/frontend/endpoint_matrix.md` — what exists vs what's missing
3. `docs/frontend/backend_dependencies.md` — Phase 3B backend tickets
4. `docs/frontend/schema.ts` — generated TypeScript types
5. Backend test baseline count recorded (currently ~3,049 tests)
6. Commit: `[frontend] F-0: API contract freeze + endpoint matrix`

**Endpoint Matrix Summary (from exploration):**

Available now:
- Health, version (global)
- Model registration (global)
- Documents: upload, extract, job status, line items
- Compiler: compile, status, bulk decisions
- Scenarios: create, compile, versions, lock, mapping decisions
- Engine/Runs: single run, get results, batch, batch status
- Exports: create, status, variance bridge
- Governance: extract claims, NFF check, assumptions (create + approve), status, blocking reasons
- Feasibility: constraint CRUD, solve, results
- Data Quality: compute, get, freshness, overview
- Depth Engine: trigger plan, status, artifacts, suite
- Libraries: mapping entries/versions, assumption entries/versions, patterns, stats
- Metrics: record, engagement, dashboard, readiness
- Workforce: employment coefficients, occupation bridge, saudization rules, compute

Missing (Phase 3B):
- B-1: Workspace CRUD
- B-12: Export artifact download
- B-14: Model version list
- B-16: Run-from-scenario convenience endpoint
- B-17: GET /compiler/{compilationId} (return full suggestions)

### F-1: Greenfield Scaffold + App Shell

**Directory:**
```
frontend/
├── src/
│   ├── app/
│   │   ├── layout.tsx            # Root: providers, fonts
│   │   ├── page.tsx              # Redirect to /w/[workspaceId]/documents
│   │   ├── login/page.tsx
│   │   └── w/[workspaceId]/
│   │       ├── layout.tsx        # Shell: sidebar + topnav
│   │       ├── documents/...
│   │       ├── compilations/...
│   │       ├── scenarios/...
│   │       ├── runs/...
│   │       ├── governance/...
│   │       └── exports/...
│   ├── components/
│   │   ├── ui/                   # shadcn/ui primitives
│   │   ├── layout/               # Shell, Sidebar, TopNav
│   │   └── shared/               # StatusBadge, ConfidenceBar, etc.
│   ├── lib/
│   │   ├── api/
│   │   │   ├── schema.ts         # Generated from OpenAPI
│   │   │   ├── client.ts         # openapi-fetch instance
│   │   │   ├── workspace.ts      # Workspace ID resolution
│   │   │   └── hooks/            # TanStack Query hooks per domain
│   │   ├── store/                # Zustand stores (UI-local state)
│   │   └── utils/                # Formatters, constants, enums
│   └── types/                    # Shared TypeScript types
├── vitest.config.ts
├── next.config.ts
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

**App Shell:**
- Sidebar: Logo, nav (Documents, Compilations, Scenarios, Runs, Governance, Exports), collapse toggle, user menu
- Top nav: Breadcrumbs, Sandbox/Governed mode badge, health indicator (polls `/health`), quick actions
- Content: Consistent padding, Skeleton loading, error boundaries

**Design Tokens:**
- Primary: navy/slate (`slate-900`, `slate-700`)
- Success: emerald (`emerald-500`)
- Warning: amber (`amber-500`)
- Error: red (`red-500`)
- Information-dense, desktop-first, consulting aesthetic

**Dev Auth:** NextAuth CredentialsProvider, hardcoded user with stable UUID, session exposes `userId`

### F-2: Document Ingest Flow

**Upload page** (`/w/[wid]/documents`):
- Drag-drop zone (Client Component)
- File validation: PDF, XLSX, CSV
- Multi-file upload with progress
- Upload form fields:
  - `file`: binary
  - `doc_type`: select → `"BOQ" | "CAPEX" | "POLICY" | "OTHER"`
  - `source_type`: select → `"CLIENT" | "PUBLIC" | "INTERNAL"`
  - `classification`: select → `"PUBLIC" | "INTERNAL" | "CONFIDENTIAL" | "RESTRICTED"`
  - `language`: select → `"en" | "ar" | "bilingual"` (default: "en")
  - `uploaded_by`: UUID from session (hidden field)
- After upload: auto-trigger extraction via `POST /documents/{docId}/extract`
- Job status polling: TanStack Query `refetchInterval` on `GET /jobs/{jobId}`

**Line items page** (`/w/[wid]/documents/[docId]`):
- TanStack Table with columns: Line #, Description, Amount, Unit, Currency, Confidence
- Sortable, filterable
- "Proceed to Compile" → `/w/[wid]/documents/[docId]/compile`

### F-3A: Suggestion Review UI

**Compile config page** (`/w/[wid]/documents/[docId]/compile`):
- Form fields:
  - `scenario_name`: text input
  - `base_model_version_id`: text input (no list endpoint — manual UUID entry, B-14 for Phase 3B)
  - `base_year`: number input
  - `start_year`: number input
  - `end_year`: number input
  - `document_id`: from URL param (hidden)
- Submit: `POST /compiler/compile`
- Response contains full `suggestions` array — cached in TanStack Query keyed by `compilationId`
- Redirect to `/w/[wid]/compilations/[compilationId]`

**Decision review page** (`/w/[wid]/compilations/[compilationId]`):
- **Data source:** TanStack Query cache from compile response. If cache cold (hard refresh), show "Compilation data unavailable — recompile required" with link back.
- Add B-17: `GET /compiler/{compilationId}` to Phase 3B backend dependencies.
- Decision table: line items with suggestion, confidence, sector, status
- Bulk operations: "Accept All" / "Reject All" via `POST /compiler/{compilationId}/decisions`
- Individual override: click row → sector code text input → save with note
- Confidence summary bar: accepted / pending / rejected counts
- "Proceed to Scenario" → `/w/[wid]/scenarios?compilationId=[id]`

### F-4A: Scenario Create + Run

**Create page** (`/w/[wid]/scenarios`):
- Form: `name`, `base_model_version_id` (text), `base_year`, `start_year`, `end_year`
- Submit: `POST /scenarios` → redirect to `/w/[wid]/scenarios/[scenarioId]`

**Scenario detail + compile** (`/w/[wid]/scenarios/[scenarioId]`):
- Compile form showing decisions + phasing
- Decision mapping from compiler output:
  - **Accepted** → `decision_type: "APPROVED"`, `final_sector_code` from suggestion
  - **Rejected** → `decision_type: "EXCLUDED"`, `final_sector_code: null` — **MUST be included to prevent auto-approval**
  - **Overridden** → `decision_type: "OVERRIDDEN"`, `final_sector_code` from user input
  - `decided_by`: UUID from session
  - `suggested_confidence`: from compiler suggestion
- Phasing: explicit `dict[str, float]` (year → share), always provided
- Source: `document_id` (preferred) or inline `line_items`
- Submit: `POST /scenarios/{scenarioId}/compile` (synchronous — loading spinner)
- Display compiled shock items from response

**Run** (if user has all data):
- Form: `model_version_id`, `base_year`, `annual_shocks` (JSON editor), `satellite_coefficients` (JSON editor), optional `deflators`
- Submit: `POST /engine/runs` (synchronous)
- "View Results" → `/w/[wid]/runs/[runId]`
- Note: complex manual input. Document B-16 (run-from-scenario convenience) for Phase 3B.

**Results page** (`/w/[wid]/runs/[runId]`):
- Headline numbers: whatever the backend returns in `result_sets`
- Sector impact table from `values` dict
- Recharts horizontal bar chart: sector breakdown (direct vs indirect if available)

### F-5A: Governance Summary

**Governance page** (`/w/[wid]/governance/[runId]`):
- Server Component loads governance status via `GET /governance/status/{runId}`
- NFF status badge: PASS (emerald) / BLOCKED (red)
- Blocking reasons from `GET /governance/blocking-reasons/{runId}`

**Claim extraction** (Client Component):
- Form: `draft_text` (textarea), `run_id` (from URL, hidden)
- Submit: `POST /governance/claims/extract`
- Display extracted claims table: text, type (`"MODEL" | "SOURCE_FACT" | "ASSUMPTION" | "RECOMMENDATION"`), status

**Assumption management** (Client Component):
- Create form:
  - `type`: select → `"IMPORT_SHARE" | "PHASING" | "DEFLATOR" | "WAGE_PROXY" | "CAPACITY_CAP" | "JOBS_COEFF"`
  - `value`: number
  - `units`: text
  - `justification`: textarea
- Approve form:
  - `range_min`: number (required)
  - `range_max`: number (required, >= range_min)
  - `actor`: UUID from session

**Publication gate:**
- Visual: PASS → "Proceed to Export" link (`/w/[wid]/exports/new?runId=...`)
- BLOCKED → "Resolve Issues" with blocking reasons list

### F-6A: Export Request + Status

**Export request page** (`/w/[wid]/exports/new?runId=...`):
- `run_id`: from URL query param (display, not editable)
- `mode`: select → `"SANDBOX" | "GOVERNED"` (uppercase ExportMode enum)
- `export_formats`: checkboxes → `"excel"`, `"pptx"` (lowercase, from orchestrator)
- `pack_data`: JSON editor (structured dict for Decision Pack metadata)
- Submit: `POST /exports` → redirect to `/w/[wid]/exports/[exportId]`

**Export status page** (`/w/[wid]/exports/[exportId]`):
- Status: typically COMPLETED or BLOCKED immediately (synchronous)
- COMPLETED: show checksums, "Download not yet available" (B-12 for Phase 3B)
- BLOCKED: show blocking reasons list
- Defensive: if status is PENDING/GENERATING, poll with `refetchInterval`

## Phase 3B Backend Dependencies

| Ticket | Description | Blocking Sprint |
|--------|-------------|-----------------|
| B-1 | Workspace CRUD (create/list/get) | Full workspace picker |
| B-12 | Export artifact download (`GET /exports/{id}/download`) | F-6B |
| B-14 | Model version list endpoint | F-3A/F-4A dropdown |
| B-16 | Run-from-scenario convenience endpoint | F-4B |
| B-17 | GET /compiler/{compilationId} with full suggestions | F-3A cache-cold recovery |

## Constraints
- TypeScript strict mode — no `any`, no implicit `any`
- Generated API client only — every call through openapi-fetch
- `npm run build` must succeed with zero errors after each sprint
- Tests for every component — Vitest + React Testing Library
- Desktop-first — consultants use laptops
- No LLM calls from frontend
- Backend tests must still pass (~3,049 baseline)
- Branch stays unmerged for review
