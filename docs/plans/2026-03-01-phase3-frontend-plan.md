# Phase 3A Frontend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Next.js 14+ frontend for ImpactOS covering document ingestion, AI-assisted mapping review, scenario creation/compilation/runs, governance summary, and export request/status — all against the existing backend API.

**Architecture:** Server Components for page shells and initial data loads; Client Components for interactivity, forms, tables, and polling. TanStack Query as server state source of truth. Zustand for UI-local state only. All entity IDs canonical in URL. Generated openapi-fetch client for every API call.

**Tech Stack:** Next.js 14+ (App Router), TypeScript strict, Tailwind CSS, shadcn/ui, TanStack Query v5, Zustand, openapi-fetch, openapi-typescript, Recharts, NextAuth.js, Vitest + React Testing Library

**Design Doc:** `docs/plans/2026-03-01-phase3-frontend-design.md`

**Backend API Base:** All workspace-scoped endpoints at `/v1/workspaces/{workspace_id}/...`. Global endpoints at `/health`, `/api/version`, `/v1/engine/models`.

---

## Prerequisites

- Backend running (`make up` from repo root, or `make serve` for host-based dev)
- Node.js 18+ installed
- pnpm installed (`npm install -g pnpm`)
- Working directory: repo root (`C:\Projects\ImpactOS\.claude\worktrees\loving-robinson`)

---

## F-0: API Contract Freeze

### Task 1: Generate OpenAPI Spec

**Files:**
- Create: `openapi.json`

**Step 1: Generate openapi.json from the FastAPI app**

```bash
cd C:\Projects\ImpactOS\.claude\worktrees\loving-robinson
python -c "import json; from src.api.main import app; print(json.dumps(app.openapi(), indent=2))" > openapi.json
```

If that fails (e.g., DB connection required), use:
```bash
# Start backend first
make serve &
# Wait for startup, then fetch
curl http://localhost:8000/openapi.json -o openapi.json
# Or on Windows PowerShell:
Invoke-WebRequest http://localhost:8000/openapi.json -OutFile openapi.json
```

**Step 2: Verify the file is valid JSON with routes**

```bash
python -c "import json; d=json.load(open('openapi.json')); print(f'Paths: {len(d[\"paths\"])}')"
```

Expected: `Paths: ` followed by a number > 40 (the backend has 60+ endpoints).

---

### Task 2: Generate TypeScript Schema

**Files:**
- Create: `docs/frontend/schema.ts`

**Step 1: Create docs/frontend directory**

```bash
mkdir -p docs/frontend
```

**Step 2: Generate TypeScript types from OpenAPI spec**

```bash
npx openapi-typescript openapi.json -o docs/frontend/schema.ts
```

**Step 3: Verify the generated file has path types**

```bash
head -50 docs/frontend/schema.ts
```

Expected: TypeScript interface with `paths` containing route definitions.

---

### Task 3: Create Endpoint Matrix

**Files:**
- Create: `docs/frontend/endpoint_matrix.md`

Write a markdown file documenting every endpoint found in `openapi.json`, organized by domain. Use the format from the design doc. Compare against the design doc's "Available now" list and verify accuracy.

The matrix must have two tables:
1. **Available Now (Phase 3A)** — endpoints that exist, with Method, Route, Purpose, Request Body summary, Response Shape summary, Frontend Sprint assignment
2. **Missing — Needed for Phase 3B** — endpoints that don't exist but are needed

Cross-reference `openapi.json` paths against these expected routes:
- Documents: POST upload, POST extract, GET job status, GET line items
- Compiler: POST compile, GET status, POST decisions
- Scenarios: POST create, POST compile, GET versions, POST lock, POST mapping-decisions
- Runs: POST single run, GET results, POST batch, GET batch status
- Exports: POST create, GET status, POST variance-bridge
- Governance: POST extract claims, POST NFF check, POST create assumption, POST approve assumption, GET status, GET blocking reasons

---

### Task 4: Create Backend Dependencies Document

**Files:**
- Create: `docs/frontend/backend_dependencies.md`

List every endpoint needed for Phase 3B that does NOT exist in `openapi.json`:

| Ticket | Endpoint | Purpose | Blocking Sprint |
|--------|----------|---------|-----------------|
| B-1 | Workspace CRUD | Create/list/get workspaces | Full workspace picker |
| B-12 | GET /exports/{id}/download | Download export artifacts | F-6B |
| B-14 | GET /v1/engine/models (list) | List available model versions | F-3A/F-4A dropdown |
| B-16 | POST /scenarios/{id}/run | Run from scenario convenience | F-4B |
| B-17 | GET /compiler/{id} | Return full compilation with suggestions | F-3A cache recovery |

Verify each against `openapi.json` — some may actually exist.

---

### Task 5: Record Test Baseline

**Step 1: Run backend tests and record count**

```bash
cd C:\Projects\ImpactOS\.claude\worktrees\loving-robinson
python -m pytest tests -q 2>&1 | tail -5
```

Record the exact pass count (expected ~3,049). Save to `docs/frontend/test_baseline.txt`:

```
Backend test baseline at F-0 freeze:
Date: 2026-03-01
Pass count: XXXX passed
Command: python -m pytest tests -q
```

---

### Task 6: Commit F-0

**Step 1: Commit all F-0 deliverables**

```bash
git add openapi.json docs/frontend/
git commit -m "[frontend] F-0: API contract freeze + endpoint matrix"
```

---

## F-1: Greenfield Scaffold + App Shell

### Task 7: Create Next.js Project

**Step 1: Scaffold the project**

```bash
cd C:\Projects\ImpactOS\.claude\worktrees\loving-robinson
npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir --import-alias "@/*" --use-pnpm
```

When prompted, accept defaults (Yes to ESLint, Yes to Tailwind, Yes to src/ directory, Yes to App Router, Yes to import alias @/*).

**Step 2: Verify it builds**

```bash
cd frontend && pnpm run build
```

Expected: Build succeeds with zero errors.

---

### Task 8: Install Core Dependencies

**Step 1: Install runtime dependencies**

```bash
cd C:\Projects\ImpactOS\.claude\worktrees\loving-robinson\frontend
pnpm add @tanstack/react-query @tanstack/react-table zustand recharts next-auth openapi-fetch lucide-react
```

**Step 2: Install dev dependencies**

```bash
pnpm add -D openapi-typescript vitest @testing-library/react @testing-library/jest-dom @testing-library/user-event jsdom @vitejs/plugin-react
```

**Step 3: Verify install succeeded**

```bash
pnpm ls --depth=0
```

---

### Task 9: Install shadcn/ui

**Step 1: Initialize shadcn/ui**

```bash
cd C:\Projects\ImpactOS\.claude\worktrees\loving-robinson\frontend
npx shadcn@latest init
```

Choose: TypeScript, Default style, slate base color, CSS variables.

**Step 2: Add component primitives**

```bash
npx shadcn@latest add button input label select textarea
npx shadcn@latest add dialog sheet popover dropdown-menu command
npx shadcn@latest add toast badge card separator
npx shadcn@latest add table tabs scroll-area
npx shadcn@latest add alert alert-dialog
npx shadcn@latest add skeleton progress tooltip
```

**Step 3: Verify components exist**

```bash
ls frontend/src/components/ui/
```

Expected: Multiple `.tsx` files for each installed component.

---

### Task 10: Configure Tailwind Design Tokens

**Files:**
- Modify: `frontend/tailwind.config.ts`

Extend the Tailwind config with ImpactOS design tokens. The shadcn/ui init already sets up CSS variables. Ensure the color palette matches:
- Primary: navy/slate
- Success: emerald
- Warning: amber
- Error/destructive: red
- Info-dense: tight spacing, good readability

Keep the shadcn/ui defaults and extend only where needed. Do NOT override shadcn's CSS variable system — extend it.

---

### Task 11: Configure Vitest

**Files:**
- Create: `frontend/vitest.config.ts`
- Create: `frontend/src/test/setup.ts`

**Step 1: Create Vitest config**

```typescript
// frontend/vitest.config.ts
import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
});
```

**Step 2: Create test setup**

```typescript
// frontend/src/test/setup.ts
import '@testing-library/jest-dom/vitest';
```

**Step 3: Add test script to package.json**

In `frontend/package.json`, add to `"scripts"`:
```json
"test": "vitest run",
"test:watch": "vitest"
```

**Step 4: Write a smoke test**

```typescript
// frontend/src/test/smoke.test.ts
import { describe, it, expect } from 'vitest';

describe('smoke test', () => {
  it('should pass', () => {
    expect(1 + 1).toBe(2);
  });
});
```

**Step 5: Run it**

```bash
cd frontend && pnpm test
```

Expected: 1 test passed.

---

### Task 12: API Client Setup

**Files:**
- Create: `frontend/src/lib/api/schema.ts` (copy from docs/frontend/)
- Create: `frontend/src/lib/api/client.ts`

**Step 1: Copy generated schema**

```bash
cp docs/frontend/schema.ts frontend/src/lib/api/schema.ts
```

**Step 2: Create the openapi-fetch client**

```typescript
// frontend/src/lib/api/client.ts
import createClient from 'openapi-fetch';
import type { paths } from './schema';

const baseUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const api = createClient<paths>({ baseUrl });
```

**Step 3: Write a test for client creation**

```typescript
// frontend/src/lib/api/__tests__/client.test.ts
import { describe, it, expect } from 'vitest';
import { api } from '../client';

describe('api client', () => {
  it('should be defined', () => {
    expect(api).toBeDefined();
    expect(api.GET).toBeDefined();
    expect(api.POST).toBeDefined();
  });
});
```

**Step 4: Run tests**

```bash
cd frontend && pnpm test
```

---

### Task 13: Workspace ID Utility

**Files:**
- Create: `frontend/src/lib/api/workspace.ts`
- Test: `frontend/src/lib/api/__tests__/workspace.test.ts`

**Step 1: Write the failing test**

```typescript
// frontend/src/lib/api/__tests__/workspace.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('getDevWorkspaceId', () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
  });

  it('returns workspace ID from env var', () => {
    vi.stubEnv('NEXT_PUBLIC_DEV_WORKSPACE_ID', '550e8400-e29b-41d4-a716-446655440000');
    // Dynamic import to pick up env
    return import('../workspace').then(({ getDevWorkspaceId }) => {
      expect(getDevWorkspaceId()).toBe('550e8400-e29b-41d4-a716-446655440000');
    });
  });

  it('throws if env var is missing', () => {
    vi.stubEnv('NEXT_PUBLIC_DEV_WORKSPACE_ID', '');
    return import('../workspace').then(({ getDevWorkspaceId }) => {
      expect(() => getDevWorkspaceId()).toThrow();
    });
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd frontend && pnpm test -- src/lib/api/__tests__/workspace.test.ts
```

**Step 3: Write implementation**

```typescript
// frontend/src/lib/api/workspace.ts

/**
 * Returns the dev workspace ID from environment.
 * In Phase 3A, all API calls use this single workspace.
 * Fail-fast if not configured.
 */
export function getDevWorkspaceId(): string {
  const id = process.env.NEXT_PUBLIC_DEV_WORKSPACE_ID;
  if (!id || id.trim() === '') {
    throw new Error(
      'NEXT_PUBLIC_DEV_WORKSPACE_ID is required. Set it in .env.local or environment.'
    );
  }
  return id;
}
```

**Step 4: Run tests**

```bash
cd frontend && pnpm test -- src/lib/api/__tests__/workspace.test.ts
```

Expected: PASS.

---

### Task 14: TanStack Query Provider

**Files:**
- Create: `frontend/src/lib/providers.tsx`

**Step 1: Create providers wrapper**

```tsx
// frontend/src/lib/providers.tsx
'use client';

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useState, type ReactNode } from 'react';
import { SessionProvider } from 'next-auth/react';

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30 * 1000, // 30 seconds
            retry: 1,
          },
        },
      })
  );

  return (
    <SessionProvider>
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    </SessionProvider>
  );
}
```

**Step 2: Wire into root layout**

```tsx
// frontend/src/app/layout.tsx
import type { Metadata } from 'next';
import { Inter } from 'next/font/google';
import './globals.css';
import { Providers } from '@/lib/providers';

const inter = Inter({ subsets: ['latin'] });

export const metadata: Metadata = {
  title: 'ImpactOS',
  description: 'Impact & Scenario Intelligence System',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
```

---

### Task 15: Dev Auth Stub

**Files:**
- Create: `frontend/src/app/api/auth/[...nextauth]/route.ts`
- Create: `frontend/src/lib/auth.ts`
- Create: `frontend/src/app/login/page.tsx`

**Step 1: Create auth config**

```typescript
// frontend/src/lib/auth.ts
import type { NextAuthOptions } from 'next-auth';
import CredentialsProvider from 'next-auth/providers/credentials';

// Stable dev user UUID — used as uploaded_by, actor, decided_by in API calls
export const DEV_USER_ID = '00000000-0000-7000-8000-000000000001';

export const authOptions: NextAuthOptions = {
  providers: [
    CredentialsProvider({
      name: 'Dev Login',
      credentials: {
        email: { label: 'Email', type: 'email', placeholder: 'dev@impactos.local' },
      },
      async authorize(credentials) {
        // Dev-only: accept any login
        return {
          id: DEV_USER_ID,
          email: credentials?.email || 'dev@impactos.local',
          name: 'Dev User',
        };
      },
    }),
  ],
  callbacks: {
    async session({ session, token }) {
      if (session.user) {
        (session.user as any).id = token.sub;
      }
      return session;
    },
  },
  pages: {
    signIn: '/login',
  },
  secret: process.env.NEXTAUTH_SECRET || 'dev-secret-do-not-use-in-production',
};
```

**Step 2: Create NextAuth route handler**

```typescript
// frontend/src/app/api/auth/[...nextauth]/route.ts
import NextAuth from 'next-auth';
import { authOptions } from '@/lib/auth';

const handler = NextAuth(authOptions);
export { handler as GET, handler as POST };
```

**Step 3: Create login page**

```tsx
// frontend/src/app/login/page.tsx
'use client';

import { signIn } from 'next-auth/react';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';

export default function LoginPage() {
  const [email, setEmail] = useState('dev@impactos.local');
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const result = await signIn('credentials', {
      email,
      redirect: false,
    });
    if (result?.ok) {
      router.push('/');
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle>ImpactOS</CardTitle>
          <CardDescription>Dev Login (Phase 3A stub)</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <Label htmlFor="email">Email</Label>
              <Input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <Button type="submit" className="w-full">
              Sign In
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
```

**Step 4: Add env vars to `.env.local`**

Create `frontend/.env.local`:
```
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_DEV_WORKSPACE_ID=550e8400-e29b-41d4-a716-446655440000
NEXTAUTH_URL=http://localhost:3000
NEXTAUTH_SECRET=dev-secret-do-not-use-in-production
```

---

### Task 16: Sidebar Component

**Files:**
- Create: `frontend/src/components/layout/sidebar.tsx`
- Test: `frontend/src/components/layout/__tests__/sidebar.test.tsx`

**Step 1: Write the failing test**

```tsx
// frontend/src/components/layout/__tests__/sidebar.test.tsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Sidebar } from '../sidebar';

// Mock next/navigation
vi.mock('next/navigation', () => ({
  usePathname: () => '/w/test-ws/documents',
  useParams: () => ({ workspaceId: 'test-ws' }),
}));

describe('Sidebar', () => {
  it('renders navigation links', () => {
    render(<Sidebar />);
    expect(screen.getByText('Documents')).toBeInTheDocument();
    expect(screen.getByText('Scenarios')).toBeInTheDocument();
    expect(screen.getByText('Governance')).toBeInTheDocument();
    expect(screen.getByText('Exports')).toBeInTheDocument();
  });

  it('highlights active link', () => {
    render(<Sidebar />);
    const documentsLink = screen.getByText('Documents').closest('a');
    expect(documentsLink).toHaveAttribute('href', '/w/test-ws/documents');
  });
});
```

**Step 2: Run test to verify it fails**

```bash
cd frontend && pnpm test -- src/components/layout/__tests__/sidebar.test.tsx
```

**Step 3: Implement sidebar**

```tsx
// frontend/src/components/layout/sidebar.tsx
'use client';

import Link from 'next/link';
import { usePathname, useParams } from 'next/navigation';
import { cn } from '@/lib/utils';
import {
  FileText,
  GitCompare,
  Layers,
  Play,
  Shield,
  Download,
} from 'lucide-react';

const navItems = [
  { label: 'Documents', href: '/documents', icon: FileText },
  { label: 'Compilations', href: '/compilations', icon: GitCompare },
  { label: 'Scenarios', href: '/scenarios', icon: Layers },
  { label: 'Runs', href: '/runs', icon: Play },
  { label: 'Governance', href: '/governance', icon: Shield },
  { label: 'Exports', href: '/exports', icon: Download },
];

export function Sidebar() {
  const pathname = usePathname();
  const params = useParams();
  const workspaceId = params.workspaceId as string;

  return (
    <aside className="flex h-full w-56 flex-col border-r bg-slate-50">
      <div className="flex h-14 items-center border-b px-4">
        <span className="text-lg font-semibold text-slate-900">ImpactOS</span>
      </div>
      <nav className="flex-1 space-y-1 p-2">
        {navItems.map((item) => {
          const fullHref = `/w/${workspaceId}${item.href}`;
          const isActive = pathname.startsWith(fullHref);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={fullHref}
              className={cn(
                'flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium',
                isActive
                  ? 'bg-slate-200 text-slate-900'
                  : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
```

**Step 4: Run tests**

```bash
cd frontend && pnpm test -- src/components/layout/__tests__/sidebar.test.tsx
```

---

### Task 17: Top Navigation Component

**Files:**
- Create: `frontend/src/components/layout/topnav.tsx`
- Test: `frontend/src/components/layout/__tests__/topnav.test.tsx`

**Step 1: Write the failing test**

```tsx
// frontend/src/components/layout/__tests__/topnav.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { TopNav } from '../topnav';

vi.mock('next-auth/react', () => ({
  useSession: () => ({ data: { user: { name: 'Dev User' } }, status: 'authenticated' }),
  signOut: vi.fn(),
}));

describe('TopNav', () => {
  it('renders the mode badge', () => {
    render(<TopNav />);
    expect(screen.getByText('SANDBOX')).toBeInTheDocument();
  });

  it('shows health indicator', () => {
    render(<TopNav />);
    expect(screen.getByTestId('health-indicator')).toBeInTheDocument();
  });
});
```

**Step 2: Run test to verify it fails, then implement**

The TopNav should include:
- Breadcrumbs (placeholder for now)
- Sandbox/Governed mode badge (always visible, prominent)
- Health indicator (green dot / red dot)
- User name from session

**Step 3: Implement, run tests, verify pass**

---

### Task 18: Health Indicator Hook

**Files:**
- Create: `frontend/src/lib/api/hooks/useHealth.ts`
- Test: `frontend/src/lib/api/hooks/__tests__/useHealth.test.ts`

**Step 1: Write the failing test**

```typescript
// frontend/src/lib/api/hooks/__tests__/useHealth.test.ts
import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useHealth } from '../useHealth';
import { api } from '../../client';

vi.mock('../../client', () => ({
  api: {
    GET: vi.fn(),
  },
}));

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

describe('useHealth', () => {
  it('returns health status', async () => {
    vi.mocked(api.GET).mockResolvedValueOnce({
      data: { status: 'ok', version: '0.1.0', environment: 'dev', checks: { api: true, database: true, redis: true, object_storage: true } },
      error: undefined,
      response: new Response(),
    });

    const { result } = renderHook(() => useHealth(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.status).toBe('ok');
  });
});
```

**Step 2: Implement the hook**

```typescript
// frontend/src/lib/api/hooks/useHealth.ts
import { useQuery } from '@tanstack/react-query';
import { api } from '../client';

export function useHealth() {
  return useQuery({
    queryKey: ['health'],
    queryFn: async () => {
      const { data, error } = await api.GET('/health');
      if (error) throw error;
      return data;
    },
    refetchInterval: 30_000, // Poll every 30s
  });
}
```

**Step 3: Run tests, verify pass**

---

### Task 19: App Shell Layout

**Files:**
- Create: `frontend/src/app/w/[workspaceId]/layout.tsx`
- Create: `frontend/src/app/page.tsx` (redirect)

**Step 1: Create workspace layout (Server Component shell, Client Components for sidebar/topnav)**

```tsx
// frontend/src/app/w/[workspaceId]/layout.tsx
import { Sidebar } from '@/components/layout/sidebar';
import { TopNav } from '@/components/layout/topnav';

export default function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen">
      <Sidebar />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopNav />
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
    </div>
  );
}
```

**Step 2: Create root page redirect**

```tsx
// frontend/src/app/page.tsx
import { redirect } from 'next/navigation';

export default function Home() {
  const workspaceId = process.env.NEXT_PUBLIC_DEV_WORKSPACE_ID;
  if (!workspaceId) {
    redirect('/login');
  }
  redirect(`/w/${workspaceId}/documents`);
}
```

**Step 3: Create placeholder pages for each route**

Create minimal `page.tsx` files in each route directory:
- `frontend/src/app/w/[workspaceId]/documents/page.tsx`
- `frontend/src/app/w/[workspaceId]/compilations/page.tsx`
- `frontend/src/app/w/[workspaceId]/scenarios/page.tsx`
- `frontend/src/app/w/[workspaceId]/runs/page.tsx`
- `frontend/src/app/w/[workspaceId]/governance/page.tsx`
- `frontend/src/app/w/[workspaceId]/exports/page.tsx`

Each placeholder:
```tsx
export default function XPage() {
  return <div><h1 className="text-2xl font-bold">X</h1><p>Coming in sprint F-N.</p></div>;
}
```

---

### Task 20: Add Frontend to Docker Compose

**Files:**
- Modify: `docker-compose.yml`

**Step 1: Add frontend service**

Add after the `celery-worker` service:

```yaml
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    container_name: impactos-frontend
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_API_URL=http://api:8000
      - NEXT_PUBLIC_DEV_WORKSPACE_ID=${DEV_WORKSPACE_ID:-550e8400-e29b-41d4-a716-446655440000}
      - NEXTAUTH_URL=http://localhost:3000
      - NEXTAUTH_SECRET=dev-secret-do-not-use-in-production
    depends_on:
      api:
        condition: service_healthy
    networks:
      - impactos
    volumes:
      - ./frontend/src:/app/src
```

**Step 2: Create frontend Dockerfile**

```dockerfile
# frontend/Dockerfile
FROM node:18-alpine AS base

FROM base AS deps
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile

FROM base AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN corepack enable && pnpm run build

FROM base AS runner
WORKDIR /app
ENV NODE_ENV=production
RUN addgroup --system --gid 1001 nodejs && adduser --system --uid 1001 nextjs
COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
USER nextjs
EXPOSE 3000
CMD ["node", "server.js"]
```

**Step 3: Update next.config to enable standalone output**

In `frontend/next.config.ts`, add `output: 'standalone'`.

---

### Task 21: Verify F-1 Build + Commit

**Step 1: Run frontend tests**

```bash
cd frontend && pnpm test
```

Expected: All tests pass.

**Step 2: Run build**

```bash
cd frontend && pnpm run build
```

Expected: Build succeeds with zero errors.

**Step 3: Verify backend tests still pass**

```bash
cd C:\Projects\ImpactOS\.claude\worktrees\loving-robinson
python -m pytest tests -q 2>&1 | tail -3
```

Expected: Same pass count as baseline.

**Step 4: Commit**

```bash
git add frontend/ docker-compose.yml
git commit -m "[frontend] F-1: greenfield scaffold + app shell + auth + providers"
```

---

## F-2: Document Ingest Flow

### Task 22: Document API Hooks

**Files:**
- Create: `frontend/src/lib/api/hooks/useDocuments.ts`
- Test: `frontend/src/lib/api/hooks/__tests__/useDocuments.test.ts`

**Step 1: Write failing tests for upload, extract, job status, and line items hooks**

Test each hook:
- `useUploadDocument` — mutation hook calling `POST /v1/workspaces/{workspace_id}/documents`
- `useExtractDocument` — mutation calling `POST /v1/workspaces/{workspace_id}/documents/{doc_id}/extract`
- `useJobStatus(jobId)` — query with `refetchInterval` calling `GET /v1/workspaces/{workspace_id}/jobs/{job_id}`
- `useLineItems(docId)` — query calling `GET /v1/workspaces/{workspace_id}/documents/{doc_id}/line-items`

Each test mocks `api.GET`/`api.POST` and verifies the hook returns expected data shape.

**Step 2: Implement all four hooks**

Key details for upload mutation:
- Must send multipart/form-data with fields: `file`, `doc_type`, `source_type`, `classification`, `language`, `uploaded_by`
- Note: openapi-fetch may need special handling for multipart. If it doesn't support it natively, use a thin wrapper around `fetch` with the correct Content-Type.

Key details for job status:
- `refetchInterval: (query) => query.state.data?.status === 'COMPLETED' || query.state.data?.status === 'FAILED' ? false : 2000`
- Stops polling when status is terminal.

**Step 3: Run tests, verify pass**

---

### Task 23: Upload Form Component

**Files:**
- Create: `frontend/src/components/documents/upload-form.tsx`
- Test: `frontend/src/components/documents/__tests__/upload-form.test.tsx`

**Step 1: Write failing test**

Test that the form renders all required fields:
- File input (drag-drop zone)
- `doc_type` select with options: BOQ, CAPEX, POLICY, OTHER
- `source_type` select with options: CLIENT, PUBLIC, INTERNAL
- `classification` select with options: PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED
- `language` select with options: en, ar, bilingual
- Submit button

Test that submit calls the upload mutation with correct payload.

**Step 2: Implement the component as a Client Component**

Use shadcn/ui `Select`, `Button`, `Card`. Include drag-drop zone for file selection. On submit, call `useUploadDocument` mutation, then auto-trigger extraction.

**Step 3: Run tests, verify pass**

---

### Task 24: Job Status Poller Component

**Files:**
- Create: `frontend/src/components/documents/extraction-status.tsx`
- Test: `frontend/src/components/documents/__tests__/extraction-status.test.tsx`

**Step 1: Write failing test**

Test states:
- Shows "Extracting..." with progress skeleton when status is RUNNING
- Shows "Complete" badge when status is COMPLETED
- Shows error message when status is FAILED
- Shows "Queued" when status is QUEUED

**Step 2: Implement using `useJobStatus` hook + shadcn Progress/Badge**

**Step 3: Run tests, verify pass**

---

### Task 25: Line Items Table Component

**Files:**
- Create: `frontend/src/components/documents/line-items-table.tsx`
- Test: `frontend/src/components/documents/__tests__/line-items-table.test.tsx`

**Step 1: Write failing test**

Test with mock data:
- Table renders correct column headers: Description, Amount, Unit, Currency, Confidence
- Rows render mock line item data
- "Proceed to Compile" button is present and links correctly

**Step 2: Implement with TanStack Table**

Use `useLineItems(docId)` hook. Columns:
- `description` (string)
- `total_value` (formatted number)
- `unit` (string)
- `currency_code` (string)
- `completeness_score` (percentage badge with color coding)

Include "Proceed to Compile" button linking to `/w/{workspaceId}/documents/{docId}/compile`.

**Step 3: Run tests, verify pass**

---

### Task 26: Documents Page

**Files:**
- Modify: `frontend/src/app/w/[workspaceId]/documents/page.tsx`
- Create: `frontend/src/app/w/[workspaceId]/documents/[docId]/page.tsx`

**Step 1: Build documents index page**

Compose `UploadForm` + recent uploads list. Since there's no document list endpoint, show a simple "Upload a document to get started" prompt with the upload form. After successful upload, show the document ID and link to the detail page.

**Step 2: Build document detail page**

Server Component shell that renders:
- `ExtractionStatus` (polls job status)
- `LineItemsTable` (shows once extraction complete)

**Step 3: Write page-level tests verifying composition**

---

### Task 27: Verify F-2 Build + Commit

**Step 1: Run all frontend tests**

```bash
cd frontend && pnpm test
```

**Step 2: Run build**

```bash
cd frontend && pnpm run build
```

**Step 3: Verify backend tests**

```bash
python -m pytest tests -q 2>&1 | tail -3
```

**Step 4: Commit**

```bash
git add frontend/
git commit -m "[frontend] F-2: document upload + extraction + line items"
```

---

## F-3A: Suggestion Review UI

### Task 28: Compiler API Hooks

**Files:**
- Create: `frontend/src/lib/api/hooks/useCompiler.ts`
- Test: `frontend/src/lib/api/hooks/__tests__/useCompiler.test.ts`

**Step 1: Write failing tests for three hooks:**

- `useCompile` — mutation calling `POST /v1/workspaces/{wid}/compiler/compile`
  - Request: `{ scenario_name, base_model_version_id, base_year, start_year, end_year, document_id }`
  - Response: `{ compilation_id, suggestions: [...], high_confidence, medium_confidence, low_confidence }`
- `useCompilationStatus(compilationId)` — query calling `GET /v1/workspaces/{wid}/compiler/{compilation_id}/status`
- `useBulkDecisions(compilationId)` — mutation calling `POST /v1/workspaces/{wid}/compiler/{compilation_id}/decisions`
  - Request: `{ decisions: [{ line_item_id, action: "accept"|"reject", override_sector_code?, note? }] }`

**Step 2: Implement hooks**

For `useCompile`, the mutation's `onSuccess` should update the query cache so that `useCompilationStatus` and any page reading the compilation data can access the full suggestions from the compile response.

**Step 3: Run tests, verify pass**

---

### Task 29: Compile Config Form

**Files:**
- Create: `frontend/src/components/compiler/compile-config-form.tsx`
- Test: `frontend/src/components/compiler/__tests__/compile-config-form.test.tsx`

**Step 1: Write failing test**

- Form renders fields: scenario_name, base_model_version_id, base_year, start_year, end_year
- base_model_version_id is a text input (manual UUID entry — no list endpoint)
- document_id is passed as prop (from URL param) and submitted as hidden field
- Submit calls useCompile mutation
- On success, navigates to `/w/{wid}/compilations/{compilationId}`

**Step 2: Implement**

```tsx
// Props: { documentId: string; workspaceId: string }
// Fields: scenario_name (text), base_model_version_id (text), base_year (number), start_year (number), end_year (number)
// Hidden: document_id from props
// On submit: call useCompile, on success router.push(`/w/${workspaceId}/compilations/${data.compilation_id}`)
```

**Step 3: Run tests, verify pass**

---

### Task 30: Decision Review Table

**Files:**
- Create: `frontend/src/components/compiler/decision-table.tsx`
- Test: `frontend/src/components/compiler/__tests__/decision-table.test.tsx`

**Step 1: Write failing test**

Test with mock suggestions data:
- Table renders columns: Line Item, Suggestion, Confidence, Sector, Status
- Each row shows the AI suggestion details
- Confidence scores show color-coded badges (green ≥ 0.8, amber ≥ 0.5, red < 0.5)
- Status badge shows "Pending" initially

**Step 2: Implement with TanStack Table**

Columns: `line_item_id` (truncated), `explanation` (text), `confidence` (badge), `sector_code`, status (local state: pending/accepted/rejected/overridden).

Use local component state (not Zustand) to track per-row accept/reject status before bulk submission.

**Step 3: Run tests, verify pass**

---

### Task 31: Bulk Decision Controls

**Files:**
- Create: `frontend/src/components/compiler/bulk-controls.tsx`
- Test: `frontend/src/components/compiler/__tests__/bulk-controls.test.tsx`

**Step 1: Write failing test**

- "Accept All" button calls bulkDecisions mutation with action: "accept" for all items
- "Reject All" button calls with action: "reject"
- Confirmation dialog appears before bulk action
- Shows count of items affected

**Step 2: Implement**

Use shadcn/ui `AlertDialog` for confirmation. Call `useBulkDecisions` mutation. Show toast on success.

**Step 3: Run tests, verify pass**

---

### Task 32: Confidence Summary Bar

**Files:**
- Create: `frontend/src/components/compiler/confidence-summary.tsx`
- Test: `frontend/src/components/compiler/__tests__/confidence-summary.test.tsx`

**Step 1: Write failing test**

- Shows accepted / pending / rejected counts
- Shows high / medium / low confidence counts from compilation status
- Progress bar segments with color coding

**Step 2: Implement**

Simple horizontal stacked bar using shadcn/ui `Progress` or div-based segments.

**Step 3: Run tests, verify pass**

---

### Task 33: Compile + Compilation Pages

**Files:**
- Create: `frontend/src/app/w/[workspaceId]/documents/[docId]/compile/page.tsx`
- Create: `frontend/src/app/w/[workspaceId]/compilations/[compilationId]/page.tsx`

**Step 1: Build compile page**

Server Component shell rendering `CompileConfigForm` with `docId` and `workspaceId` from URL params.

**Step 2: Build compilation detail page**

Client Component that:
- Reads compilation data from TanStack Query cache (set during compile)
- If cache cold: shows "Compilation data unavailable — please recompile" with link
- Otherwise: renders `DecisionTable` + `BulkControls` + `ConfidenceSummary`
- "Proceed to Scenario" link at bottom

**Step 3: Run tests, verify pass**

---

### Task 34: Verify F-3A Build + Commit

```bash
cd frontend && pnpm test && pnpm run build
python -m pytest tests -q 2>&1 | tail -3
git add frontend/
git commit -m "[frontend] F-3A: compiler suggestion review UI"
```

---

## F-4A: Scenario Create + Run

### Task 35: Scenario API Hooks

**Files:**
- Create: `frontend/src/lib/api/hooks/useScenarios.ts`
- Test: `frontend/src/lib/api/hooks/__tests__/useScenarios.test.ts`

Hooks:
- `useCreateScenario` — mutation: `POST /v1/workspaces/{wid}/scenarios`
  - Body: `{ name, base_model_version_id, base_year, start_year, end_year }`
- `useCompileScenario(scenarioId)` — mutation: `POST /v1/workspaces/{wid}/scenarios/{scenario_id}/compile`
  - Body: `{ document_id?, line_items?, decisions: [...], phasing: {...}, default_domestic_share? }`
  - Critical: rejected items MUST be included with `decision_type: "EXCLUDED"`
- `useScenarioVersions(scenarioId)` — query: `GET /v1/workspaces/{wid}/scenarios/{scenario_id}/versions`

TDD: write failing tests, implement, verify pass.

---

### Task 36: Run API Hooks

**Files:**
- Create: `frontend/src/lib/api/hooks/useRuns.ts`
- Test: `frontend/src/lib/api/hooks/__tests__/useRuns.test.ts`

Hooks:
- `useCreateRun` — mutation: `POST /v1/workspaces/{wid}/engine/runs`
  - Body: `{ model_version_id, annual_shocks, base_year, satellite_coefficients, deflators? }`
- `useRunResults(runId)` — query: `GET /v1/workspaces/{wid}/engine/runs/{run_id}`

TDD: write failing tests, implement, verify pass.

---

### Task 37: Scenario Create Form

**Files:**
- Create: `frontend/src/components/scenarios/create-form.tsx`
- Test: `frontend/src/components/scenarios/__tests__/create-form.test.tsx`

Fields: `name`, `base_model_version_id` (text), `base_year`, `start_year`, `end_year`.
On success: navigate to `/w/{wid}/scenarios/{scenarioId}`.

TDD: write failing test, implement, verify pass.

---

### Task 38: Scenario Compile Form

**Files:**
- Create: `frontend/src/components/scenarios/compile-form.tsx`
- Test: `frontend/src/components/scenarios/__tests__/compile-form.test.tsx`

Complex form that:
1. Accepts `compilationId` (optional query param) to load compiler decisions from cache
2. Shows decisions table (read-only summary of accepted/rejected/overridden items)
3. Maps decisions to scenario compile format:
   - Accepted → `{ line_item_id, final_sector_code, decision_type: "APPROVED", decided_by, suggested_confidence }`
   - Rejected → `{ line_item_id, final_sector_code: null, decision_type: "EXCLUDED", decided_by, suggested_confidence }`
   - Overridden → `{ line_item_id, final_sector_code: <user_value>, decision_type: "OVERRIDDEN", decided_by, suggested_confidence }`
4. Phasing editor: year → share inputs (must sum to 1.0)
5. `document_id` input (or from compilation cache)
6. Submit: `POST /scenarios/{id}/compile` (synchronous)
7. Display shock items from response

TDD: write failing test focusing on decision mapping logic and phasing validation.

---

### Task 39: Run Execution Form

**Files:**
- Create: `frontend/src/components/runs/run-form.tsx`
- Test: `frontend/src/components/runs/__tests__/run-form.test.tsx`

Fields:
- `model_version_id` (text — manual UUID)
- `base_year` (number)
- `annual_shocks` (JSON textarea — `{"2025": [1.0, 2.0, ...]}`)
- `satellite_coefficients` (JSON textarea — `{"jobs_coeff": [...], "import_ratio": [...], "va_ratio": [...]}`)
- `deflators` (optional JSON textarea)

Validation: JSON must parse. Required fields must be present.

On submit: `POST /engine/runs` → on success navigate to `/w/{wid}/runs/{runId}`.

Note: This is a power-user form. Add helper text explaining expected JSON shapes. Document B-16 (run-from-scenario) as a Phase 3B UX improvement.

TDD: write failing test, implement, verify pass.

---

### Task 40: Results Display

**Files:**
- Create: `frontend/src/components/runs/results-display.tsx`
- Test: `frontend/src/components/runs/__tests__/results-display.test.tsx`

Uses `useRunResults(runId)` hook. Displays:
1. Headline card: total impact value (sum of all sector values)
2. Sector impact table: sector_code → value from `result_sets[0].values`
3. Sector breakdowns if available in `sector_breakdowns`

TDD: write failing test with mock data, implement, verify pass.

---

### Task 41: Sector Bar Chart

**Files:**
- Create: `frontend/src/components/runs/sector-chart.tsx`
- Test: `frontend/src/components/runs/__tests__/sector-chart.test.tsx`

Recharts horizontal `BarChart`:
- Y axis: sector codes
- X axis: impact values
- Color: slate-700 for bars
- Sorted by value descending

TDD: test that chart renders with mock data (test for SVG elements or container).

---

### Task 42: Scenario + Run Pages

**Files:**
- Modify: `frontend/src/app/w/[workspaceId]/scenarios/page.tsx`
- Create: `frontend/src/app/w/[workspaceId]/scenarios/[scenarioId]/page.tsx`
- Create: `frontend/src/app/w/[workspaceId]/runs/[runId]/page.tsx`

Scenarios index: `ScenarioCreateForm`
Scenario detail: `ScenarioCompileForm` + optional `RunForm` section
Run results: `ResultsDisplay` + `SectorChart`

---

### Task 43: Verify F-4A Build + Commit

```bash
cd frontend && pnpm test && pnpm run build
python -m pytest tests -q 2>&1 | tail -3
git add frontend/
git commit -m "[frontend] F-4A: scenario create + compile + run + results"
```

---

## F-5A: Governance Summary

### Task 44: Governance API Hooks

**Files:**
- Create: `frontend/src/lib/api/hooks/useGovernance.ts`
- Test: `frontend/src/lib/api/hooks/__tests__/useGovernance.test.ts`

Hooks:
- `useGovernanceStatus(runId)` — query: `GET /v1/workspaces/{wid}/governance/status/{run_id}`
- `useBlockingReasons(runId)` — query: `GET /v1/workspaces/{wid}/governance/blocking-reasons/{run_id}`
- `useExtractClaims` — mutation: `POST /v1/workspaces/{wid}/governance/claims/extract`
  - Body: `{ draft_text, run_id, workspace_id? }`
- `useNffCheck` — mutation: `POST /v1/workspaces/{wid}/governance/nff/check`
  - Body: `{ claim_ids: [...] }`
- `useCreateAssumption` — mutation: `POST /v1/workspaces/{wid}/governance/assumptions`
  - Body: `{ type: AssumptionType, value, units, justification }`
- `useApproveAssumption(assumptionId)` — mutation: `POST /v1/workspaces/{wid}/governance/assumptions/{id}/approve`
  - Body: `{ range_min, range_max, actor }`

TDD for each hook.

---

### Task 45: Governance Status Display

**Files:**
- Create: `frontend/src/components/governance/status-display.tsx`
- Test: `frontend/src/components/governance/__tests__/status-display.test.tsx`

Displays:
- NFF status badge: PASS (emerald bg) / BLOCKED (red bg)
- Claims: total, resolved, unresolved counts
- Assumptions: total, approved counts
- Blocking reasons list (if any)

TDD: test both PASS and BLOCKED states with mock data.

---

### Task 46: Claim Extraction Form

**Files:**
- Create: `frontend/src/components/governance/claim-extraction.tsx`
- Test: `frontend/src/components/governance/__tests__/claim-extraction.test.tsx`

Form:
- `draft_text` (textarea, required)
- `run_id` passed as prop (from URL)
- Submit button
- After extraction: shows claims table with columns: text, type, status

TDD: test form rendering, submission, and results display.

---

### Task 47: Assumption Forms

**Files:**
- Create: `frontend/src/components/governance/assumption-create.tsx`
- Create: `frontend/src/components/governance/assumption-approve.tsx`
- Test: `frontend/src/components/governance/__tests__/assumption-forms.test.tsx`

Create form fields:
- `type` select: IMPORT_SHARE | PHASING | DEFLATOR | WAGE_PROXY | CAPACITY_CAP | JOBS_COEFF
- `value` number input
- `units` text input
- `justification` textarea

Approve form fields (shown after creation):
- `range_min` number
- `range_max` number (validated >= range_min)
- `actor` = UUID from session (hidden)

TDD: test both forms.

---

### Task 48: Publication Gate Component

**Files:**
- Create: `frontend/src/components/governance/publication-gate.tsx`
- Test: `frontend/src/components/governance/__tests__/publication-gate.test.tsx`

Visual:
- PASS state: green border card, "Publication Gate: PASS" heading, "Proceed to Export" button → `/w/{wid}/exports/new?runId={runId}`
- BLOCKED state: red border card, "Publication Gate: BLOCKED" heading, list of blocking reasons, "Resolve Issues" text

TDD: test both states.

---

### Task 49: Governance Page

**Files:**
- Create: `frontend/src/app/w/[workspaceId]/governance/[runId]/page.tsx`

Compose: `GovernanceStatusDisplay` + `ClaimExtraction` + `AssumptionCreate` + `AssumptionApprove` + `PublicationGate`

---

### Task 50: Verify F-5A Build + Commit

```bash
cd frontend && pnpm test && pnpm run build
python -m pytest tests -q 2>&1 | tail -3
git add frontend/
git commit -m "[frontend] F-5A: governance status + claims + assumptions + publication gate"
```

---

## F-6A: Export Request + Status

### Task 51: Export API Hooks

**Files:**
- Create: `frontend/src/lib/api/hooks/useExports.ts`
- Test: `frontend/src/lib/api/hooks/__tests__/useExports.test.ts`

Hooks:
- `useCreateExport` — mutation: `POST /v1/workspaces/{wid}/exports`
  - Body: `{ run_id, mode: "SANDBOX"|"GOVERNED", export_formats: ["excel","pptx"], pack_data: {...} }`
- `useExportStatus(exportId)` — query: `GET /v1/workspaces/{wid}/exports/{export_id}`
  - Defensive polling: `refetchInterval` only if status is PENDING or GENERATING

TDD for each hook.

---

### Task 52: Export Request Form

**Files:**
- Create: `frontend/src/components/exports/export-form.tsx`
- Test: `frontend/src/components/exports/__tests__/export-form.test.tsx`

Form:
- `run_id` from URL query param (display, not editable)
- `mode` select: SANDBOX | GOVERNED (uppercase, matching ExportMode enum)
- `export_formats` checkboxes: "excel", "pptx" (lowercase, matching orchestrator)
- `pack_data` JSON textarea (with placeholder example)
- Submit button

On success: navigate to `/w/{wid}/exports/{exportId}`.

TDD: test form rendering, enum values, submission.

---

### Task 53: Export Status Display

**Files:**
- Create: `frontend/src/components/exports/export-status.tsx`
- Test: `frontend/src/components/exports/__tests__/export-status.test.tsx`

Display based on status:
- **COMPLETED**: green badge, checksums table, "Download not yet available (Phase 3B)" message
- **BLOCKED**: red badge, blocking reasons list
- **PENDING/GENERATING**: amber badge with spinner (defensive — usually doesn't happen)
- **FAILED**: red badge with error message

TDD: test all four states with mock data.

---

### Task 54: Export Pages

**Files:**
- Create: `frontend/src/app/w/[workspaceId]/exports/new/page.tsx`
- Create: `frontend/src/app/w/[workspaceId]/exports/[exportId]/page.tsx`

Export new: reads `runId` from `searchParams`, renders `ExportForm`.
Export status: reads `exportId` from params, renders `ExportStatus`.

---

### Task 55: Verify F-6A Build + Commit

```bash
cd frontend && pnpm test && pnpm run build
python -m pytest tests -q 2>&1 | tail -3
git add frontend/
git commit -m "[frontend] F-6A: export request + status"
```

---

## Final Verification

### Task 56: End-to-End Verification

**Step 1: Run full test suite**

```bash
cd C:\Projects\ImpactOS\.claude\worktrees\loving-robinson\frontend
pnpm test
```

Expected: All tests pass, zero failures.

**Step 2: Run production build**

```bash
pnpm run build
```

Expected: Zero errors, zero warnings.

**Step 3: Run linter**

```bash
pnpm run lint
```

Expected: Clean.

**Step 4: Verify TypeScript strict mode**

Check `tsconfig.json` has `"strict": true`. Run:

```bash
npx tsc --noEmit
```

Expected: No type errors.

**Step 5: Verify backend tests unchanged**

```bash
cd C:\Projects\ImpactOS\.claude\worktrees\loving-robinson
python -m pytest tests -q 2>&1 | tail -3
```

Expected: Same pass count as F-0 baseline.

**Step 6: Verify no `any` types**

```bash
cd frontend
grep -r ": any" src/ --include="*.ts" --include="*.tsx" | grep -v "node_modules" | grep -v ".d.ts"
```

Expected: Zero results (except possibly the NextAuth session callback which is a known issue — document it).

**Step 7: Verify all API calls use generated client**

```bash
grep -r "fetch(" src/ --include="*.ts" --include="*.tsx" | grep -v "node_modules" | grep -v "openapi-fetch"
```

Expected: Zero hand-written fetch calls (except inside hooks that wrap openapi-fetch).

**Step 8: Final commit**

```bash
git add -A
git status
```

Verify no sensitive files (.env.local, secrets) are staged. Then:

```bash
git commit -m "[frontend] Phase 3A: final verification pass"
```

---

## Summary

| Sprint | Tasks | Key Deliverables |
|--------|-------|-----------------|
| F-0 | 1-6 | openapi.json, endpoint matrix, TS schema, backend dependencies, test baseline |
| F-1 | 7-21 | Next.js scaffold, shadcn/ui, auth stub, API client, app shell, Docker |
| F-2 | 22-27 | Upload, extraction, job polling, line items table |
| F-3A | 28-34 | Compile config, AI suggestions, bulk decisions, confidence summary |
| F-4A | 35-43 | Scenario CRUD, compile, run execution, results + charts |
| F-5A | 44-50 | Governance status, claims, assumptions, publication gate |
| F-6A | 51-55 | Export request, status display |
| Final | 56 | Full verification |

**Total: 56 tasks across 8 checkpoints.**

**Branch:** `claude/loving-robinson` — stays unmerged for review.
