# Plan 013: Build the React + Monaco web UI in `web/` (one root per cluster, Explain/Expand, unverified fix diffs)

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report. Do not improvise. When done, update the status row for this plan
> in `plans/README.md` (the "Milestone 2" table, row 013), unless a reviewer
> dispatched you and told you they maintain the index. End your final report
> with a **Viva notes** list: the decisions, trade-offs or deviations an
> examiner might ask about (see `plans/README.md`, "Viva notes convention").
> Do not edit `VIVA.md`; the advisor folds your notes into it.
>
> Every code block marked "exact content" is the whole file to write; copy it
> verbatim (UTF-8, LF line endings are fine). Do not reformat or "improve" it.
> The advisor ran exactly these files on 2026-10-11 (Node 22.13.1, npm 11.5.2,
> Windows, Git Bash): a fresh `npm install` from this `package.json`, then
> `npm test` (30 passed) and `npm run build` (exit 0), and drove the dev UI in a
> browser against the plan-012 backend. If a verification fails and your file is
> identical to the plan, STOP and report.
>
> The only file you do not copy from this plan is `web/package-lock.json`:
> `npm install` generates it in Step 1, and you commit it.
>
> **Never open, read, list or run anything under `tests/corpus/heldout/`.**
>
> **Drift check (run first, from the project root, in Git Bash)**:
> 1. `git diff --stat 40d4ef9..HEAD -- web` must print nothing, and `ls web 2>&1 | grep -c "No such file"` must print `1`.
> 2. Plan 012 has landed: `.venv/Scripts/python -m pytest -q tests/unit/test_api.py` ends with `58 passed`.
> 3. `node --version` prints `v22.` followed by anything, and `npm --version` prints `11.` followed by anything. (Other versions: STOP.)
> 4. `grep -n "node_modules/\|dist/" .gitignore` shows the generic `node_modules/` and `dist/` lines (they exist at `40d4ef9`).
>
> If any check fails, STOP and report which one and its output.

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: LOW (a new, self-contained `web/` folder; no Python changes)
- **Depends on**: `plans/012-fastapi-backend.md` (merged into `main`)
- **Category**: direction (milestone 2 UI for PRD F2, F3, F4)
- **Planned at**: commit `40d4ef9`, 2026-10-11

## Why this matters

The project is a course compiler for a strict C99 subset with an AI error-assistant layer. Milestones 1–2 produce structured error records, group cascades under root causes (F2), tag severity (F4) and explain errors through a compiler-scoped agent (F3), all behind the FastAPI backend of plan 012. The PRD's demo is an editor-style UI: "React, with a code editor component (Monaco) and a diff viewer … Editor-style UI with inline errors and patch diffs." This plan builds that UI in `web/`, so a student (and the examiner) sees one root error per cluster with a collapsed "+N related" count, a fatal/warning badge, the summary line, short and expanded explanations, and fix diffs that are clearly labelled **Unverified preview** until F8 (milestone 4) verifies them.

## Current state

- There is no `web/` folder. Root `.gitignore` already has generic `node_modules/` and `dist/` lines; this plan adds explicit `web/node_modules/` and `web/dist/` entries as the contract requires.
- `plans/m2-architecture.md` §4 (binding contract), quoted: "Vite + React + TypeScript, with `@monaco-editor/react` for the editor and Monaco's `DiffEditor` for fixes. Versions are pinned in `package-lock.json`, which is committed; `node_modules/` is git-ignored. UI features: Inline markers in the editor. An error panel showing **one root per cluster**, with a collapsed "+N related" count, a fatal/warning badge and the F4 summary line. Per-root **Expand** and **Suggest fix** buttons. The fix opens the diff with an **"Unverified preview"** badge. The UI talks only to `/api/*` through the Vite dev proxy. Checks are `npm run build` and `npm test` (Vitest + React Testing Library, mocking `fetch`)." §5: "No network in tests … `web/node_modules/` and `web/dist/` are git-ignored."
- PRD lines this UI implements (from `cd project prd.docx`): F2 "The UI shows one root error with a collapsed count of related symptoms." F3 "Default response: two sentences at most … An "Expand" action gives the full explanation; a "Suggest fix" action returns a diff view … the agent refuses questions unrelated to the compiler." F4 "The summary line shows counts, for example "2 fatal, 3 warnings"." Goals: "The agent does not auto-edit source files; the student applies fixes." Architecture: "UI shows root errors, severity, explanation, diff and the follow-up chat."
- The backend (plan 012, `src/cea/api.py`) serves, on `http://127.0.0.1:8000`:
  - `POST /api/compile {source}` → `{ok, summary, records, clusters:[{root_id, symptom_ids}]}`; each record has `id, phase, code, severity, line, column, found, expected, snippet, root_id, rule_ref, language, caused_by, span_end:{line, column}, message`. Clusters come with roots in (line, column) order. `span_end` is inclusive.
  - `POST /api/explain {source, record_id, mode:"short"|"expand"}` → `{text, rule_ref, cited_rule, mode}`
  - `POST /api/fix {source, record_id}` → `{diff, patched_source, verified}` (`verified` is always `false` in milestone 2)
  - `POST /api/ask {source, record_id, question}` → `{text, refused}`
  - `GET /api/health` → `{status:"ok", llm:"primary"|"fallback"|"none"}`
  - Errors: `{detail: "..."}` with 404 (unknown record id), 413 (source over 64 KB), 422, 502 (agent failed), 503 (LLM not configured). CORS allows only `http://localhost:5173`.
  - The server is stateless: a record id only means something together with the source it came from.
- `src/test/fixtures.ts` below is the real `/api/compile` response for the sample program, captured from the plan-012 backend at `40d4ef9` + plan 009. It has 7 records in 3 clusters: `E-0007` (WRN-UNUSED-VAR, no symptoms), `E-0002` (SEM-UNDECLARED-VAR, symptoms `E-0003`..`E-0006`), `E-0001` (SYN-MISSING-SEMICOLON). Summary `6 fatal, 1 warning`.

### Advisor decisions you must not change

1. **Versions** (exact, verified by a fresh install on 2026-10-11): `react` / `react-dom` 19.3.0, `@monaco-editor/react` 4.7.0, `monaco-editor` 0.57.0; dev: `vite` 8.3.4, `@vitejs/plugin-react` 6.1.2, `typescript` 7.0.2, `vitest` 5.0.3, `jsdom` 29.1.1, `@testing-library/react` 16.3.3, `@testing-library/dom` 10.4.2, `@testing-library/jest-dom` 7.0.1, `@testing-library/user-event` 14.6.7, `@types/react` / `@types/react-dom` 19.3.0.
2. **Monaco is bundled locally** (`src/monaco-setup.ts`: `loader.config({ monaco })` with the editor core, the C language registration and the editor worker via Vite's `?worker` import). The default of `@monaco-editor/react` downloads Monaco from a CDN at runtime, which breaks an offline demo. Note the monaco-editor 0.57 import paths: `monaco-editor/editor/editor.api`, `monaco-editor/languages/definitions/cpp/register`, `monaco-editor/editor/editor.worker?worker` (the old `esm/vs/...` paths no longer resolve).
3. **Tests never load Monaco**: `src/test/setup.ts` mocks `@monaco-editor/react` with `src/test/monaco-mock.tsx` (a textarea `Editor` whose `onMount` passes a fake `monaco.editor.setModelMarkers` spy, and a `<pre>` `DiffEditor`). `fetch` is mocked per test with `src/test/fetch-mock.ts`.
4. **Inline markers**: every record gets a marker; fatal roots are `Error` (8), warning roots `Warning` (4), symptoms `Info` (2) with "(related to E-000N)". Monaco's end column is exclusive, so `endColumn = span_end.column + 1`.
5. **Actions per root card**: Explain (`mode: "short"`), Expand (`mode: "expand"`), Suggest fix, and a one-line Ask box (the PRD's follow-up chat; `/api/ask` exists). A refused answer is shown as "Out of scope:". There is no "Apply fix" button: the student applies fixes (PRD goal).
6. **Stateless backend**: the panel always sends the source it compiled (not the live editor text), and after an edit shows "The code changed since the last compile. Compile again to update."
7. **Dev server port 5173 with `strictPort: true`**, because the backend's CORS allows only that origin; the proxy maps `/api` to `http://127.0.0.1:8000`.
8. `npm audit` reports **2 low-severity** advisories (DOMPurify, a dependency of `monaco-editor` 0.57.0; the suggested "fix" is a breaking downgrade). The UI never feeds untrusted HTML to Monaco's sanitizer, so the advisor accepts them; `npm audit --audit-level=high` exits 0.

## Commands you will need

| Purpose | Command (from `web/`, Git Bash) | Expected on success |
|---|---|---|
| Install (Step 1) | `npm install` | exit 0; creates `package-lock.json` |
| Tests | `npm test` | see each step |
| Build | `npm run build` | exit 0; `dist/index.html` exists |
| Dev server | `npm run dev` | `Local: http://localhost:5173/` |
| Backend (project root) | `.venv/Scripts/python -m uvicorn cea.api:app --reload --app-dir src` | `Uvicorn running on http://127.0.0.1:8000` |

## Scope

**In scope** (the only files you may create or modify):
- `web/package.json`, `web/package-lock.json` (generated), `web/tsconfig.json`, `web/vite.config.ts`, `web/index.html`, `web/README.md`
- `web/src/` : `main.tsx`, `monaco-setup.ts`, `App.tsx`, `App.css`, `api.ts`, `types.ts`, `clusters.ts`, `sample.ts`, `components/CodeEditor.tsx`, `components/ErrorPanel.tsx`, `components/FixDiff.tsx`, `test/setup.ts`, `test/monaco-mock.tsx`, `test/fetch-mock.ts`, `test/fixtures.ts`, `clusters.test.ts`, `api.test.ts`, `App.test.tsx`
- `.gitignore` (append 3 lines), `README.md` (append one section at the end), `plans/README.md` (status row 013 only)

**Out of scope** (do NOT touch):
- Everything under `src/` and `tests/` (Python). If the UI seems to need a backend change, STOP.
- `VIVA.md`, `plans/m2-architecture.md`, `docs/**`.
- ESLint/Prettier or any tool not listed (keep the dependency list exactly as given).
- Never commit `web/node_modules/` or `web/dist/`.

## Git workflow

- Branch: `advisor/013-react-ui` from `main`.
- One commit per step. Stage by explicit path (never `git add -A` / `git add .`; never `git add web`). Message style as in `git log`: `web: ... (plan 013 step N)`, `docs: ...`, `plans: ...`. Every commit message ends with a blank line and then:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  ```
- Do NOT push (there is no remote). Do NOT merge; the owner reviews first.

## Steps

### Step 1: Scaffold `web/`, install the pinned packages, ignore build output

1a. Create these files with exact content.

`web/package.json`:
```json
{
  "name": "cea-web",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit -p tsconfig.json && vite build",
    "test": "vitest run",
    "preview": "vite preview"
  },
  "dependencies": {
    "@monaco-editor/react": "4.7.0",
    "monaco-editor": "0.57.0",
    "react": "19.3.0",
    "react-dom": "19.3.0"
  },
  "devDependencies": {
    "@testing-library/dom": "10.4.2",
    "@testing-library/jest-dom": "7.0.1",
    "@testing-library/react": "16.3.3",
    "@testing-library/user-event": "14.6.7",
    "@types/react": "19.3.0",
    "@types/react-dom": "19.3.0",
    "@vitejs/plugin-react": "6.1.2",
    "jsdom": "29.1.1",
    "typescript": "7.0.2",
    "vite": "8.3.4",
    "vitest": "5.0.3"
  }
}
```

`web/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "moduleResolution": "bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "isolatedModules": true,
    "skipLibCheck": true,
    "noEmit": true,
    "types": ["vite/client"]
  },
  "include": ["src"]
}
```

`web/vite.config.ts`:
```ts
/// <reference types="vitest/config" />
// Vite + Vitest configuration for the CEA web UI (plan 013, plans/m2-architecture.md section 4).
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    // The UI talks only to /api/*; the FastAPI backend (plan 012) runs on 127.0.0.1:8000.
    proxy: { "/api": { target: "http://127.0.0.1:8000", changeOrigin: false } },
  },
  build: { chunkSizeWarningLimit: 8000 },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    unstubGlobals: true,
  },
});
```

`web/index.html`:
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Compiler Error Assistant</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

1b. Append these three lines to the END of the root `.gitignore`:
```
# Web UI (plan 013)
web/node_modules/
web/dist/
```

1c. Run `cd web && npm install` (network needed; about a minute). It creates `web/node_modules/` and `web/package-lock.json`.

**Verify** (from `web/`):
- `npm ls --depth=0` → exit 0 and exactly these 15 lines after the first: `@monaco-editor/react@4.7.0`, `@testing-library/dom@10.4.2`, `@testing-library/jest-dom@7.0.1`, `@testing-library/react@16.3.3`, `@testing-library/user-event@14.6.7`, `@types/react-dom@19.3.0`, `@types/react@19.3.0`, `@vitejs/plugin-react@6.1.2`, `jsdom@29.1.1`, `monaco-editor@0.57.0`, `react-dom@19.3.0`, `react@19.3.0`, `typescript@7.0.2`, `vite@8.3.4`, `vitest@5.0.3` (no `UNMET` or `invalid`)
- `npm audit --audit-level=high` → exit 0 (2 low advisories are expected, see decision 8)
- From the project root: `git check-ignore web/node_modules web/dist` → prints both paths
- From the project root: `git status --porcelain -uall web | grep -c node_modules` → `0`

Commit: `web: scaffold Vite + React + TypeScript with pinned packages (plan 013 step 1)`, staging `.gitignore web/package.json web/package-lock.json web/tsconfig.json web/vite.config.ts web/index.html`.

### Step 2: API client, cluster/marker helpers, test harness and their tests

Create these files with exact content.

`web/src/types.ts`:
```ts
// JSON shapes of the FastAPI backend (plan 012, plans/m2-architecture.md section 3).

export type Severity = "fatal" | "warning";

export interface ErrorRecord {
  id: string;
  phase: "lexical" | "syntax" | "semantic";
  code: string;
  severity: Severity;
  line: number;
  column: number;
  found: string;
  expected: string[];
  snippet: string;
  root_id: string;
  rule_ref: string;
  language: string;
  caused_by: string | null;
  span_end: { line: number; column: number };
  message: string;
}

export interface ClusterRef {
  root_id: string;
  symptom_ids: string[];
}

export interface CompileResponse {
  ok: boolean;
  summary: string;
  records: ErrorRecord[];
  clusters: ClusterRef[];
}

export type ExplainMode = "short" | "expand";

export interface Explanation {
  text: string;
  rule_ref: string;
  cited_rule: string | null;
  mode: ExplainMode;
}

export interface FixSuggestion {
  diff: string;
  patched_source: string;
  verified: boolean;
}

export interface Answer {
  text: string;
  refused: boolean;
}

export interface Health {
  status: string;
  llm: "primary" | "fallback" | "none";
}
```

`web/src/api.ts`:
```ts
// Typed calls to the backend. Every request goes to /api/*, which the Vite dev
// proxy forwards to FastAPI (plan 012). Only the source text and record ids are
// sent: never a filename or any student identity (PRD privacy note).
import type { Answer, CompileResponse, Explanation, ExplainMode, FixSuggestion, Health } from "./types";

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, body?: object): Promise<T> {
  const init: RequestInit = body === undefined
    ? { method: "GET" }
    : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const resp = await fetch(path, init);
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`.trim();
    try {
      const data = await resp.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      // not JSON: keep the status line
    }
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

export const compile = (source: string) => request<CompileResponse>("/api/compile", { source });

export const explain = (source: string, recordId: string, mode: ExplainMode) =>
  request<Explanation>("/api/explain", { source, record_id: recordId, mode });

export const suggestFix = (source: string, recordId: string) =>
  request<FixSuggestion>("/api/fix", { source, record_id: recordId });

export const ask = (source: string, recordId: string, question: string) =>
  request<Answer>("/api/ask", { source, record_id: recordId, question });

export const health = () => request<Health>("/api/health");
```

`web/src/clusters.ts`:
```ts
// Pure helpers: turn the /api/compile response into the error-panel view (PRD F2:
// one root per cluster with a collapsed count of related symptoms) and into
// Monaco marker data (inline errors). No React, no Monaco import: unit-testable.
import type { CompileResponse, ErrorRecord } from "./types";

export interface ClusterView {
  root: ErrorRecord;
  symptoms: ErrorRecord[];
}

/** One entry per cluster, in the backend's order (roots by line, column). */
export function clusterViews(resp: CompileResponse): ClusterView[] {
  const byId = new Map(resp.records.map((r) => [r.id, r]));
  const views: ClusterView[] = [];
  for (const c of resp.clusters) {
    const root = byId.get(c.root_id);
    if (!root) continue;
    const symptoms = c.symptom_ids.map((id) => byId.get(id)).filter((r): r is ErrorRecord => r !== undefined);
    views.push({ root, symptoms });
  }
  return views;
}

/** "+N related" for a cluster with N symptoms; "" for none. */
export function relatedLabel(count: number): string {
  return count > 0 ? `+${count} related` : "";
}

/** Monaco's MarkerSeverity values (monaco.MarkerSeverity), duplicated so this file needs no Monaco import. */
export const MarkerSeverity = { Hint: 1, Info: 2, Warning: 4, Error: 8 } as const;

export interface MarkerData {
  startLineNumber: number;
  startColumn: number;
  endLineNumber: number;
  endColumn: number;
  severity: number;
  message: string;
  code: string;
  source: string;
}

/** Inline markers: roots as Error (fatal) or Warning; symptoms as Info, pointing at their root. */
export function toMarkers(records: ErrorRecord[]): MarkerData[] {
  return records.map((r) => {
    const isRoot = r.root_id === r.id;
    const severity = !isRoot ? MarkerSeverity.Info : r.severity === "fatal" ? MarkerSeverity.Error : MarkerSeverity.Warning;
    return {
      startLineNumber: r.line,
      startColumn: r.column,
      endLineNumber: r.span_end.line,
      endColumn: r.span_end.column + 1, // span_end is inclusive; Monaco's end column is exclusive
      severity,
      message: isRoot ? r.message : `${r.message} (related to ${r.root_id})`,
      code: r.code,
      source: "cea",
    };
  });
}
```

`web/src/sample.ts` (the `\\n` inside the template literal is intentional: the C source contains the two characters `\n`):
```ts
// The program the editor starts with: one missing ';', one undeclared loop
// counter used five times (one F2 cluster) and one unused variable (a warning).
export const SAMPLE_SOURCE = `#include <stdio.h>

int main(void) {
    int total = 0;
    int unused = 3;
    for (i = 0; i < 3; i = i + 1) {
        total = total + i;
    }
    printf("%d\\n", total)
    return 0;
}
`;
```

`web/src/test/setup.ts`:
```ts
// Vitest setup: jest-dom matchers, the Monaco mock, and cleanup after each test.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { monacoMock } from "./monaco-mock";

vi.mock("@monaco-editor/react", () => import("./monaco-mock"));

afterEach(() => {
  cleanup();
  monacoMock.setModelMarkers.mockReset();
});
```

`web/src/test/monaco-mock.tsx`:
```tsx
// A stand-in for @monaco-editor/react: Monaco cannot run in jsdom. Editor is a
// textarea that calls onMount with a fake editor and a fake monaco whose
// setModelMarkers is the spy below; DiffEditor renders the patched source.
import { useEffect } from "react";
import { vi } from "vitest";

export const monacoMock = {
  setModelMarkers: vi.fn(),
  model: { id: "model" },
};

interface EditorProps {
  value?: string;
  onChange?: (value: string | undefined) => void;
  onMount?: (editor: unknown, monaco: unknown) => void;
}

export function Editor({ value, onChange, onMount }: EditorProps) {
  useEffect(() => {
    onMount?.({ getModel: () => monacoMock.model }, { editor: { setModelMarkers: monacoMock.setModelMarkers } });
  }, []);
  return <textarea data-testid="editor" value={value} onChange={(e) => onChange?.(e.target.value)} />;
}

export function DiffEditor({ original, modified }: { original?: string; modified?: string }) {
  return (
    <pre data-testid="diff-editor" data-original={original}>
      {modified}
    </pre>
  );
}

export const loader = { config: vi.fn() };
export default Editor;
```

`web/src/test/fetch-mock.ts`:
```ts
// Replaces global fetch with a router keyed by "METHOD /path". Each handler gets
// the parsed JSON body and returns { status?, json }. Unknown routes give 500.
import { vi } from "vitest";

export interface Reply {
  status?: number;
  json: unknown;
}
export type Routes = Record<string, (body: Record<string, unknown>) => Reply>;

export function mockFetch(routes: Routes) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const handler = routes[`${init?.method ?? "GET"} ${url}`];
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
    const { status = 200, json } = handler ? handler(body) : { status: 500, json: { detail: "no route" } };
    return new Response(JSON.stringify(json), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

/** The parsed JSON bodies of every call to `path`, in call order. */
export function bodiesFor(fn: ReturnType<typeof mockFetch>, path: string): Record<string, unknown>[] {
  return fn.mock.calls
    .filter(([url]) => url === path)
    .map(([, init]) => JSON.parse(String(init?.body)) as Record<string, unknown>);
}
```

`web/src/test/fixtures.ts`:
```ts
// The real /api/compile response for SAMPLE_SOURCE (src/sample.ts), captured from the plan-012 backend.
import type { CompileResponse } from "../types";

export const SAMPLE_COMPILE: CompileResponse = {
  ok: false,
  summary: "6 fatal, 1 warning",
  records: [
    {"id": "E-0001", "phase": "syntax", "code": "SYN-MISSING-SEMICOLON", "severity": "fatal", "line": 9, "column": 26, "found": "return", "expected": [";"], "snippet": "    }\n    printf(\"%d\\n\", total)\n    return 0;", "root_id": "E-0001", "rule_ref": "expr_stmt", "language": "c", "caused_by": null, "span_end": {"line": 9, "column": 26}, "message": "Expected ';' after the expression statement but found 'return'"},
    {"id": "E-0002", "phase": "semantic", "code": "SEM-UNDECLARED-VAR", "severity": "fatal", "line": 6, "column": 10, "found": "i", "expected": [], "snippet": "    int unused = 3;\n    for (i = 0; i < 3; i = i + 1) {\n        total = total + i;", "root_id": "E-0002", "rule_ref": "sem.declare_before_use", "language": "c", "caused_by": null, "span_end": {"line": 6, "column": 10}, "message": "Variable 'i' is used before it is declared"},
    {"id": "E-0003", "phase": "semantic", "code": "SEM-UNDECLARED-VAR", "severity": "fatal", "line": 6, "column": 17, "found": "i", "expected": [], "snippet": "    int unused = 3;\n    for (i = 0; i < 3; i = i + 1) {\n        total = total + i;", "root_id": "E-0002", "rule_ref": "sem.declare_before_use", "language": "c", "caused_by": null, "span_end": {"line": 6, "column": 17}, "message": "Variable 'i' is used before it is declared"},
    {"id": "E-0004", "phase": "semantic", "code": "SEM-UNDECLARED-VAR", "severity": "fatal", "line": 6, "column": 24, "found": "i", "expected": [], "snippet": "    int unused = 3;\n    for (i = 0; i < 3; i = i + 1) {\n        total = total + i;", "root_id": "E-0002", "rule_ref": "sem.declare_before_use", "language": "c", "caused_by": null, "span_end": {"line": 6, "column": 24}, "message": "Variable 'i' is used before it is declared"},
    {"id": "E-0005", "phase": "semantic", "code": "SEM-UNDECLARED-VAR", "severity": "fatal", "line": 6, "column": 28, "found": "i", "expected": [], "snippet": "    int unused = 3;\n    for (i = 0; i < 3; i = i + 1) {\n        total = total + i;", "root_id": "E-0002", "rule_ref": "sem.declare_before_use", "language": "c", "caused_by": null, "span_end": {"line": 6, "column": 28}, "message": "Variable 'i' is used before it is declared"},
    {"id": "E-0006", "phase": "semantic", "code": "SEM-UNDECLARED-VAR", "severity": "fatal", "line": 7, "column": 25, "found": "i", "expected": [], "snippet": "    for (i = 0; i < 3; i = i + 1) {\n        total = total + i;\n    }", "root_id": "E-0002", "rule_ref": "sem.declare_before_use", "language": "c", "caused_by": null, "span_end": {"line": 7, "column": 25}, "message": "Variable 'i' is used before it is declared"},
    {"id": "E-0007", "phase": "semantic", "code": "WRN-UNUSED-VAR", "severity": "warning", "line": 5, "column": 9, "found": "unused", "expected": [], "snippet": "    int total = 0;\n    int unused = 3;\n    for (i = 0; i < 3; i = i + 1) {", "root_id": "E-0007", "rule_ref": "sem.unused_declaration", "language": "c", "caused_by": null, "span_end": {"line": 5, "column": 14}, "message": "Variable 'unused' is declared but never used"},
  ],
  clusters: [
    {"root_id": "E-0007", "symptom_ids": []},
    {"root_id": "E-0002", "symptom_ids": ["E-0003", "E-0004", "E-0005", "E-0006"]},
    {"root_id": "E-0001", "symptom_ids": []},
  ],
};
```

`web/src/clusters.test.ts`:
```ts
import { describe, expect, it } from "vitest";
import { clusterViews, MarkerSeverity, relatedLabel, toMarkers } from "./clusters";
import { SAMPLE_COMPILE } from "./test/fixtures";

describe("clusterViews", () => {
  it("gives one view per cluster, in backend order, with symptoms", () => {
    const views = clusterViews(SAMPLE_COMPILE);
    expect(views.map((v) => [v.root.id, v.symptoms.map((s) => s.id)])).toEqual([
      ["E-0007", []],
      ["E-0002", ["E-0003", "E-0004", "E-0005", "E-0006"]],
      ["E-0001", []],
    ]);
  });

  it("skips ids that are not in the records", () => {
    const resp = { ...SAMPLE_COMPILE, clusters: [{ root_id: "E-0099", symptom_ids: [] }, { root_id: "E-0002", symptom_ids: ["E-0003", "E-0098"] }] };
    expect(clusterViews(resp).map((v) => [v.root.id, v.symptoms.length])).toEqual([["E-0002", 1]]);
  });

  it("is empty for a clean program", () => {
    expect(clusterViews({ ok: true, summary: "0 fatal, 0 warnings", records: [], clusters: [] })).toEqual([]);
  });
});

describe("relatedLabel", () => {
  it.each([
    [0, ""],
    [1, "+1 related"],
    [4, "+4 related"],
  ])("%i symptoms -> %j", (n, label) => {
    expect(relatedLabel(n)).toBe(label);
  });
});

describe("toMarkers", () => {
  const markers = toMarkers(SAMPLE_COMPILE.records);

  it("makes one marker per record", () => {
    expect(markers).toHaveLength(7);
  });

  it("marks fatal roots as errors, warning roots as warnings and symptoms as info", () => {
    expect(markers.map((m) => [m.code, m.severity])).toEqual([
      ["SYN-MISSING-SEMICOLON", MarkerSeverity.Error],
      ["SEM-UNDECLARED-VAR", MarkerSeverity.Error],
      ["SEM-UNDECLARED-VAR", MarkerSeverity.Info],
      ["SEM-UNDECLARED-VAR", MarkerSeverity.Info],
      ["SEM-UNDECLARED-VAR", MarkerSeverity.Info],
      ["SEM-UNDECLARED-VAR", MarkerSeverity.Info],
      ["WRN-UNUSED-VAR", MarkerSeverity.Warning],
    ]);
  });

  it("converts the inclusive span end to Monaco's exclusive end column", () => {
    expect(markers[6]).toMatchObject({ startLineNumber: 5, startColumn: 9, endLineNumber: 5, endColumn: 15, source: "cea" });
  });

  it("points symptoms at their root", () => {
    expect(markers[2].message).toBe("Variable 'i' is used before it is declared (related to E-0002)");
    expect(markers[1].message).toBe("Variable 'i' is used before it is declared");
  });
});
```

`web/src/api.test.ts`:
```ts
import { describe, expect, it, vi } from "vitest";
import { ApiError, ask, compile, explain, health, suggestFix } from "./api";
import { bodiesFor, mockFetch } from "./test/fetch-mock";

const SRC = "int main(void) {\n    return 0;\n}\n";

describe("api", () => {
  it("posts only the source to /api/compile", async () => {
    const fetchFn = mockFetch({ "POST /api/compile": () => ({ json: { ok: true, summary: "0 fatal, 0 warnings", records: [], clusters: [] } }) });
    const resp = await compile(SRC);
    expect(resp.summary).toBe("0 fatal, 0 warnings");
    expect(bodiesFor(fetchFn, "/api/compile")).toEqual([{ source: SRC }]);
    expect(fetchFn.mock.calls[0][1]?.headers).toEqual({ "Content-Type": "application/json" });
  });

  it("sends exactly the contract fields to explain, fix and ask", async () => {
    const fetchFn = mockFetch({
      "POST /api/explain": () => ({ json: { text: "t", rule_ref: "r", cited_rule: null, mode: "expand" } }),
      "POST /api/fix": () => ({ json: { diff: "", patched_source: SRC, verified: false } }),
      "POST /api/ask": () => ({ json: { text: "a", refused: false } }),
    });
    await explain(SRC, "E-0001", "expand");
    await suggestFix(SRC, "E-0001");
    await ask(SRC, "E-0001", "why?");
    expect(bodiesFor(fetchFn, "/api/explain")).toEqual([{ source: SRC, record_id: "E-0001", mode: "expand" }]);
    expect(bodiesFor(fetchFn, "/api/fix")).toEqual([{ source: SRC, record_id: "E-0001" }]);
    expect(bodiesFor(fetchFn, "/api/ask")).toEqual([{ source: SRC, record_id: "E-0001", question: "why?" }]);
  });

  it("reads /api/health with GET", async () => {
    const fetchFn = mockFetch({ "GET /api/health": () => ({ json: { status: "ok", llm: "fallback" } }) });
    expect(await health()).toEqual({ status: "ok", llm: "fallback" });
    expect(fetchFn.mock.calls[0][1]).toEqual({ method: "GET" });
  });

  it("throws ApiError with the server's detail", async () => {
    mockFetch({ "POST /api/compile": () => ({ status: 413, json: { detail: "Source is larger than 65536 bytes." } }) });
    const err = await compile("x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 413, message: "Source is larger than 65536 bytes." });
  });

  it("falls back to the status line when the error body is not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>bad gateway</html>", { status: 502, statusText: "Bad Gateway" })));
    await expect(compile("x")).rejects.toMatchObject({ status: 502, message: "502 Bad Gateway" });
  });
});
```

**Verify** (from `web/`):
- `npm test` → `Test Files  2 passed (2)` and `Tests  15 passed (15)` (clusters 10, api 5)
- `npx tsc --noEmit -p tsconfig.json` → exit 0, no output

Commit: `web: API client, cluster view and marker helpers with tests (plan 013 step 2)`, staging the 10 files above by path (`web/src/types.ts web/src/api.ts web/src/clusters.ts web/src/sample.ts web/src/test/setup.ts web/src/test/monaco-mock.tsx web/src/test/fetch-mock.ts web/src/test/fixtures.ts web/src/clusters.test.ts web/src/api.test.ts`).

### Step 3: Editor, error panel, fix diff, the app, and the UI tests

Create these files with exact content.

`web/src/components/CodeEditor.tsx`:
```tsx
// The Monaco source editor with inline error markers (setModelMarkers).
import Editor, { type Monaco, type OnMount } from "@monaco-editor/react";
import { useEffect, useRef, useState } from "react";
import { toMarkers } from "../clusters";
import type { ErrorRecord } from "../types";

export const MARKER_OWNER = "cea";

type EditorInstance = Parameters<OnMount>[0];
type MarkerList = Parameters<Monaco["editor"]["setModelMarkers"]>[2];

interface Props {
  value: string;
  onChange: (value: string) => void;
  records: ErrorRecord[];
}

export default function CodeEditor({ value, onChange, records }: Props) {
  const mounted = useRef<{ editor: EditorInstance; monaco: Monaco } | null>(null);
  const [ready, setReady] = useState(false);

  const handleMount: OnMount = (editor, monaco) => {
    mounted.current = { editor, monaco };
    setReady(true);
  };

  useEffect(() => {
    const m = mounted.current;
    const model = m?.editor.getModel();
    if (!m || !model) return;
    m.monaco.editor.setModelMarkers(model, MARKER_OWNER, toMarkers(records) as MarkerList);
  }, [records, ready]);

  return (
    <Editor
      height="100%"
      defaultLanguage="c"
      value={value}
      onChange={(v) => onChange(v ?? "")}
      onMount={handleMount}
      options={{ minimap: { enabled: false }, fontSize: 14, scrollBeyondLastLine: false }}
    />
  );
}
```

`web/src/components/FixDiff.tsx`:
```tsx
// A suggested fix as a Monaco diff, labelled "Unverified preview" in
// milestone 2 (fixes are not re-compiled until F8, milestone 4).
import { DiffEditor } from "@monaco-editor/react";
import type { FixSuggestion } from "../types";

interface Props {
  original: string;
  fix: FixSuggestion;
}

export default function FixDiff({ original, fix }: Props) {
  if (fix.patched_source === original) {
    return <p className="note">The assistant has no code change to suggest for this error.</p>;
  }
  return (
    <section className="fix" aria-label="Suggested fix">
      <div className="fix-head">
        {fix.verified ? (
          <span className="badge verified">Verified</span>
        ) : (
          <span className="badge unverified">Unverified preview</span>
        )}
        <span className="fix-note">
          {fix.verified ? "This fix was compiled and checked." : "Not compiled or checked. Read it before you change your code."}
        </span>
      </div>
      <div className="diff">
        <DiffEditor
          height="240px"
          language="c"
          original={original}
          modified={fix.patched_source}
          options={{ readOnly: true, renderSideBySide: false, minimap: { enabled: false }, scrollBeyondLastLine: false }}
        />
      </div>
    </section>
  );
}
```

`web/src/components/ErrorPanel.tsx`:
```tsx
// The error panel (PRD F2/F3/F4): one card per root cause, a fatal/warning
// badge, a collapsed "+N related" list of symptoms, and the per-root
// Explain / Expand / Suggest fix / Ask actions.
import { useState, type FormEvent } from "react";
import { ask, explain, suggestFix } from "../api";
import { relatedLabel, type ClusterView } from "../clusters";
import type { Answer, Explanation, FixSuggestion } from "../types";
import FixDiff from "./FixDiff";

interface PanelProps {
  views: ClusterView[];
  source: string; // the source these records came from (the server is stateless)
}

export default function ErrorPanel({ views, source }: PanelProps) {
  return (
    <ol className="clusters" aria-label="Root causes">
      {views.map((v) => (
        <RootCard key={v.root.id} view={v} source={source} />
      ))}
    </ol>
  );
}

interface CardProps {
  view: ClusterView;
  source: string;
}

export function RootCard({ view, source }: CardProps) {
  const { root, symptoms } = view;
  const [open, setOpen] = useState(false);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [fix, setFix] = useState<FixSuggestion | null>(null);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run<T>(call: () => Promise<T>, done: (value: T) => void) {
    setBusy(true);
    setError(null);
    try {
      done(await call());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function onAsk(e: FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (q) void run(() => ask(source, root.id, q), setAnswer);
  }

  return (
    <li className={`card ${root.severity}`} aria-label={`${root.code} at line ${root.line}`}>
      <div className="card-head">
        <span className={`badge ${root.severity}`}>{root.severity}</span>
        <code className="code">{root.code}</code>
        <span className="pos">
          line {root.line}, col {root.column}
        </span>
      </div>
      <p className="message">{root.message}</p>
      {symptoms.length > 0 && (
        <button type="button" className="related" aria-expanded={open} onClick={() => setOpen(!open)}>
          {relatedLabel(symptoms.length)}
        </button>
      )}
      {open && (
        <ul className="symptoms" aria-label={`Errors related to ${root.id}`}>
          {symptoms.map((s) => (
            <li key={s.id}>
              <code>{s.code}</code> line {s.line}, col {s.column}: {s.message}
            </li>
          ))}
        </ul>
      )}
      <div className="actions">
        <button type="button" disabled={busy} onClick={() => run(() => explain(source, root.id, "short"), setExplanation)}>
          Explain
        </button>
        <button type="button" disabled={busy} onClick={() => run(() => explain(source, root.id, "expand"), setExplanation)}>
          Expand
        </button>
        <button type="button" disabled={busy} onClick={() => run(() => suggestFix(source, root.id), setFix)}>
          Suggest fix
        </button>
      </div>
      {busy && (
        <p className="note" role="status">
          Asking the assistant...
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {explanation && (
        <div className="explanation" data-mode={explanation.mode}>
          <p>{explanation.text}</p>
          <p className="rule">
            Rule: <code>{explanation.rule_ref}</code>
          </p>
        </div>
      )}
      {fix && <FixDiff original={source} fix={fix} />}
      <form className="ask" onSubmit={onAsk}>
        <input
          aria-label={`Question about ${root.id}`}
          placeholder="Ask about this error"
          maxLength={1000}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button type="submit" disabled={busy || question.trim() === ""}>
          Ask
        </button>
      </form>
      {answer && (
        <p className={answer.refused ? "answer refused" : "answer"}>
          {answer.refused && <strong>Out of scope: </strong>}
          {answer.text}
        </p>
      )}
    </li>
  );
}
```

`web/src/App.tsx`:
```tsx
// The demo page: Monaco editor on the left, the F2 error panel on the right.
import { useEffect, useState } from "react";
import { compile, health } from "./api";
import { clusterViews } from "./clusters";
import CodeEditor from "./components/CodeEditor";
import ErrorPanel from "./components/ErrorPanel";
import { SAMPLE_SOURCE } from "./sample";
import type { CompileResponse, Health } from "./types";

interface Compiled {
  source: string;
  resp: CompileResponse;
  run: number; // remounts the panel so per-root state never outlives its compile
}

export default function App() {
  const [source, setSource] = useState(SAMPLE_SOURCE);
  const [compiled, setCompiled] = useState<Compiled | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [llm, setLlm] = useState<Health["llm"] | "offline" | null>(null);

  useEffect(() => {
    health()
      .then((h) => setLlm(h.llm))
      .catch(() => setLlm("offline"));
  }, []);

  async function onCompile() {
    setBusy(true);
    setError(null);
    try {
      const resp = await compile(source);
      setCompiled((prev) => ({ source, resp, run: (prev?.run ?? 0) + 1 }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const views = compiled ? clusterViews(compiled.resp) : [];
  const stale = compiled !== null && compiled.source !== source;
  const count = compiled?.resp.records.length ?? 0;

  return (
    <div className="app">
      <header className="top">
        <h1>Compiler Error Assistant</h1>
        <span className="llm">AI: {llm ?? "..."}</span>
        <button type="button" className="primary" onClick={onCompile} disabled={busy}>
          {busy ? "Compiling..." : "Compile"}
        </button>
      </header>
      <main className="layout">
        <div className="editor-pane">
          <CodeEditor value={source} onChange={setSource} records={compiled?.resp.records ?? []} />
        </div>
        <aside className="panel" aria-label="Errors">
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          {!compiled && !error && <p className="note">Press Compile to check your program.</p>}
          {compiled && (
            <>
              <p className="summary">
                <span className={compiled.resp.ok ? "status ok" : "status fail"}>
                  {compiled.resp.ok ? "Compiles" : "Does not compile"}
                </span>
                <span data-testid="summary">{compiled.resp.summary}</span>
              </p>
              <p className="note">
                {views.length} root {views.length === 1 ? "cause" : "causes"} shown for {count}{" "}
                {count === 1 ? "error" : "errors"}
              </p>
              {stale && (
                <p className="note stale" role="status">
                  The code changed since the last compile. Compile again to update.
                </p>
              )}
              {views.length === 0 ? (
                <p className="note">No errors. The program compiles.</p>
              ) : (
                <ErrorPanel key={compiled.run} views={views} source={compiled.source} />
              )}
            </>
          )}
        </aside>
      </main>
    </div>
  );
}
```

`web/src/monaco-setup.ts`:
```ts
// Use the locally installed monaco-editor package instead of the default CDN
// download of @monaco-editor/react, so the demo works offline. Only the editor
// core and C syntax colouring are bundled. Imported only by main.tsx; tests
// mock @monaco-editor/react and never load Monaco.
import * as monaco from "monaco-editor/editor/editor.api";
import "monaco-editor/languages/definitions/cpp/register";
import EditorWorker from "monaco-editor/editor/editor.worker?worker";
import { loader } from "@monaco-editor/react";

self.MonacoEnvironment = { getWorker: () => new EditorWorker() };
loader.config({ monaco });
```

`web/src/main.tsx`:
```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./monaco-setup";
import App from "./App";
import "./App.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

`web/src/App.css`:
```css
:root {
  --bg: #f6f7f9;
  --surface: #ffffff;
  --text: #1d2330;
  --muted: #5b6475;
  --border: #d9dde5;
  --fatal: #b42318;
  --fatal-bg: #fdecea;
  --warning: #9a6700;
  --warning-bg: #fff4d6;
  --accent: #2457c5;
  --unverified: #8a3ffc;
  --unverified-bg: #f1e8ff;
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  color: var(--text);
  background: var(--bg);
}

* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); }

.app { display: flex; flex-direction: column; height: 100vh; }
.top {
  display: flex; align-items: center; gap: 16px;
  padding: 10px 16px; background: var(--surface); border-bottom: 1px solid var(--border);
}
.top h1 { font-size: 18px; margin: 0; flex: 1; }
.llm { color: var(--muted); font-size: 13px; }

button {
  font: inherit; font-size: 13px; padding: 5px 12px; border-radius: 6px;
  border: 1px solid var(--border); background: var(--surface); color: var(--text); cursor: pointer;
}
button:hover:not(:disabled) { border-color: var(--accent); }
button:disabled { opacity: 0.55; cursor: default; }
button.primary { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }

.layout { flex: 1; display: grid; grid-template-columns: minmax(0, 3fr) minmax(320px, 2fr); min-height: 0; }
.editor-pane { min-height: 0; border-right: 1px solid var(--border); background: var(--surface); }
.panel { overflow-y: auto; padding: 14px 16px; }

.summary { display: flex; align-items: center; gap: 10px; font-weight: 600; margin: 0 0 4px; }
.status { padding: 2px 8px; border-radius: 999px; font-size: 12px; }
.status.ok { background: #e3f6e8; color: #1a7f37; }
.status.fail { background: var(--fatal-bg); color: var(--fatal); }
.note { color: var(--muted); font-size: 13px; margin: 6px 0; }
.stale { color: var(--warning); }
.error { color: var(--fatal); background: var(--fatal-bg); padding: 8px 10px; border-radius: 6px; font-size: 13px; }

.clusters { list-style: none; padding: 0; margin: 12px 0 0; display: flex; flex-direction: column; gap: 12px; }
.card {
  background: var(--surface); border: 1px solid var(--border); border-left: 4px solid var(--fatal);
  border-radius: 8px; padding: 10px 12px;
}
.card.warning { border-left-color: var(--warning); }
.card-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; font-size: 13px; }
.code { font-size: 12px; }
.pos { color: var(--muted); }
.message { margin: 6px 0; }

.badge { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.04em; padding: 2px 7px; border-radius: 4px; }
.badge.fatal { background: var(--fatal-bg); color: var(--fatal); }
.badge.warning { background: var(--warning-bg); color: var(--warning); }
.badge.unverified { background: var(--unverified-bg); color: var(--unverified); font-size: 12px; border: 1px solid var(--unverified); }
.badge.verified { background: #e3f6e8; color: #1a7f37; }

.related { border: none; background: none; color: var(--accent); padding: 0; }
.symptoms { margin: 6px 0; padding-left: 18px; font-size: 13px; color: var(--muted); }
.actions { display: flex; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
.explanation { margin-top: 8px; padding: 8px 10px; background: var(--bg); border-radius: 6px; font-size: 14px; }
.explanation p { margin: 4px 0; }
.rule { color: var(--muted); font-size: 12px; }

.fix { margin-top: 10px; border: 1px solid var(--unverified); border-radius: 6px; overflow: hidden; }
.fix-head { display: flex; align-items: center; gap: 10px; padding: 6px 8px; background: var(--unverified-bg); }
.fix-note { font-size: 12px; color: var(--muted); }
.diff { height: 240px; }

.ask { display: flex; gap: 6px; margin-top: 10px; }
.ask input { flex: 1; font: inherit; font-size: 13px; padding: 5px 8px; border: 1px solid var(--border); border-radius: 6px; }
.answer { font-size: 14px; margin: 6px 0 0; }
.answer.refused { color: var(--muted); font-style: italic; }

@media (max-width: 800px) {
  .layout { grid-template-columns: 1fr; grid-template-rows: 50vh auto; }
  .editor-pane { border-right: none; border-bottom: 1px solid var(--border); }
}
```

`web/src/App.test.tsx`:
```tsx
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import App from "./App";
import { SAMPLE_SOURCE } from "./sample";
import { bodiesFor, mockFetch, type Routes } from "./test/fetch-mock";
import { SAMPLE_COMPILE } from "./test/fixtures";
import { monacoMock } from "./test/monaco-mock";

const PATCHED = SAMPLE_SOURCE.replace("total)\n", "total);\n");

function routes(extra: Routes = {}): Routes {
  return {
    "GET /api/health": () => ({ json: { status: "ok", llm: "none" } }),
    "POST /api/compile": () => ({ json: SAMPLE_COMPILE }),
    "POST /api/explain": (b) => ({ json: { text: `${b.mode} text for ${b.record_id}`, rule_ref: "sem.declare_before_use", cited_rule: null, mode: b.mode } }),
    "POST /api/fix": () => ({ json: { diff: "--- a\n+++ b\n", patched_source: PATCHED, verified: false } }),
    "POST /api/ask": () => ({ json: { text: "I only answer questions about your compiler errors.", refused: true } }),
    ...extra,
  };
}

async function compileSample(extra: Routes = {}) {
  const fetchFn = mockFetch(routes(extra));
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole("button", { name: "Compile" }));
  await screen.findByTestId("summary");
  return { fetchFn, user };
}

function card(code: string, line: number) {
  return screen.getByRole("listitem", { name: `${code} at line ${line}` });
}

describe("App", () => {
  it("starts with the sample program and a hint", async () => {
    mockFetch(routes());
    render(<App />);
    expect(screen.getByTestId("editor")).toHaveValue(SAMPLE_SOURCE);
    expect(screen.getByText("Press Compile to check your program.")).toBeInTheDocument();
    expect(await screen.findByText("AI: none")).toBeInTheDocument();
  });

  it("shows the backend as offline when /api/health fails", async () => {
    mockFetch(routes({ "GET /api/health": () => ({ status: 500, json: {} }) }));
    render(<App />);
    expect(await screen.findByText("AI: offline")).toBeInTheDocument();
  });

  it("compiles the editor text and shows the F4 summary line", async () => {
    const { fetchFn } = await compileSample();
    expect(screen.getByTestId("summary")).toHaveTextContent("6 fatal, 1 warning");
    expect(screen.getByText("Does not compile")).toBeInTheDocument();
    expect(screen.getByText("3 root causes shown for 7 errors")).toBeInTheDocument();
    expect(bodiesFor(fetchFn, "/api/compile")).toEqual([{ source: SAMPLE_SOURCE }]);
  });

  it("shows one card per root cause, not one per record", async () => {
    await compileSample();
    const list = screen.getByRole("list", { name: "Root causes" });
    const cards = within(list).getAllByRole("listitem");
    expect(cards.map((c) => c.getAttribute("aria-label"))).toEqual([
      "WRN-UNUSED-VAR at line 5",
      "SEM-UNDECLARED-VAR at line 6",
      "SYN-MISSING-SEMICOLON at line 9",
    ]);
  });

  it("labels each root fatal or warning", async () => {
    await compileSample();
    expect(within(card("WRN-UNUSED-VAR", 5)).getByText("warning")).toHaveClass("badge", "warning");
    expect(within(card("SEM-UNDECLARED-VAR", 6)).getByText("fatal")).toHaveClass("badge", "fatal");
    expect(within(card("SYN-MISSING-SEMICOLON", 9)).getByText("fatal")).toHaveClass("badge", "fatal");
  });

  it("collapses symptoms behind +N related and expands them on click", async () => {
    const { user } = await compileSample();
    const root = card("SEM-UNDECLARED-VAR", 6);
    const toggle = within(root).getByRole("button", { name: "+4 related" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("list", { name: "Errors related to E-0002" })).toBeNull();
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const symptoms = within(screen.getByRole("list", { name: "Errors related to E-0002" })).getAllByRole("listitem");
    expect(symptoms).toHaveLength(4);
    expect(symptoms[0]).toHaveTextContent("SEM-UNDECLARED-VAR line 6, col 17");
    expect(within(card("SYN-MISSING-SEMICOLON", 9)).queryByRole("button", { name: /related/ })).toBeNull();
  });

  it("sets inline markers for every record", async () => {
    await compileSample();
    await waitFor(() => expect(monacoMock.setModelMarkers).toHaveBeenLastCalledWith(monacoMock.model, "cea", expect.any(Array)));
    const markers = monacoMock.setModelMarkers.mock.lastCall?.[2] as { code: string; severity: number }[];
    expect(markers).toHaveLength(7);
    expect(markers.filter((m) => m.severity === 8).map((m) => m.code)).toEqual(["SYN-MISSING-SEMICOLON", "SEM-UNDECLARED-VAR"]);
  });

  it("Explain asks for the short explanation and Expand for the full one", async () => {
    const { fetchFn, user } = await compileSample();
    const root = card("SEM-UNDECLARED-VAR", 6);
    await user.click(within(root).getByRole("button", { name: "Explain" }));
    expect(await within(root).findByText("short text for E-0002")).toBeInTheDocument();
    await user.click(within(root).getByRole("button", { name: "Expand" }));
    expect(await within(root).findByText("expand text for E-0002")).toBeInTheDocument();
    expect(within(root).getByText("sem.declare_before_use")).toBeInTheDocument();
    expect(bodiesFor(fetchFn, "/api/explain")).toEqual([
      { source: SAMPLE_SOURCE, record_id: "E-0002", mode: "short" },
      { source: SAMPLE_SOURCE, record_id: "E-0002", mode: "expand" },
    ]);
  });

  it("Suggest fix shows the diff with an Unverified preview badge", async () => {
    const { fetchFn, user } = await compileSample();
    const root = card("SYN-MISSING-SEMICOLON", 9);
    await user.click(within(root).getByRole("button", { name: "Suggest fix" }));
    const fix = await within(root).findByRole("region", { name: "Suggested fix" });
    expect(within(fix).getByText("Unverified preview")).toHaveClass("badge", "unverified");
    expect(within(fix).queryByText("Verified")).toBeNull();
    const diff = within(fix).getByTestId("diff-editor");
    expect(diff).toHaveAttribute("data-original", SAMPLE_SOURCE);
    expect(diff.textContent).toBe(PATCHED);
    expect(bodiesFor(fetchFn, "/api/fix")).toEqual([{ source: SAMPLE_SOURCE, record_id: "E-0001" }]);
  });

  it("says so when the fix changes nothing", async () => {
    const { user } = await compileSample({
      "POST /api/fix": () => ({ json: { diff: "", patched_source: SAMPLE_SOURCE, verified: false } }),
    });
    const root = card("SYN-MISSING-SEMICOLON", 9);
    await user.click(within(root).getByRole("button", { name: "Suggest fix" }));
    expect(await within(root).findByText("The assistant has no code change to suggest for this error.")).toBeInTheDocument();
    expect(within(root).queryByTestId("diff-editor")).toBeNull();
  });

  it("Ask shows a refused answer as out of scope", async () => {
    const { fetchFn, user } = await compileSample();
    const root = card("SEM-UNDECLARED-VAR", 6);
    const askButton = within(root).getByRole("button", { name: "Ask" });
    expect(askButton).toBeDisabled();
    await user.type(within(root).getByRole("textbox", { name: "Question about E-0002" }), "  What is the capital of France?  ");
    await user.click(askButton);
    expect(await within(root).findByText("Out of scope:")).toBeInTheDocument();
    expect(bodiesFor(fetchFn, "/api/ask")).toEqual([
      { source: SAMPLE_SOURCE, record_id: "E-0002", question: "What is the capital of France?" },
    ]);
  });

  it("shows a backend error from compile", async () => {
    mockFetch(routes({ "POST /api/compile": () => ({ status: 413, json: { detail: "Source is larger than 65536 bytes." } }) }));
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Compile" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Source is larger than 65536 bytes.");
  });

  it("shows an assistant error inside the card", async () => {
    const { user } = await compileSample({
      "POST /api/explain": () => ({ status: 503, json: { detail: "The AI assistant is not configured. See .env.example." } }),
    });
    const root = card("SEM-UNDECLARED-VAR", 6);
    await user.click(within(root).getByRole("button", { name: "Explain" }));
    expect(await within(root).findByRole("alert")).toHaveTextContent("The AI assistant is not configured.");
  });

  it("reports a clean program", async () => {
    await compileSample({
      "POST /api/compile": () => ({ json: { ok: true, summary: "0 fatal, 0 warnings", records: [], clusters: [] } }),
    });
    expect(screen.getByText("Compiles")).toBeInTheDocument();
    expect(screen.getByText("No errors. The program compiles.")).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Root causes" })).toBeNull();
  });

  it("after an edit, warns that results are stale and still sends the compiled source", async () => {
    const { fetchFn, user } = await compileSample();
    await user.type(screen.getByTestId("editor"), "// edited");
    expect(screen.getByText("The code changed since the last compile. Compile again to update.")).toBeInTheDocument();
    await user.click(within(card("SEM-UNDECLARED-VAR", 6)).getByRole("button", { name: "Explain" }));
    await screen.findByText("short text for E-0002");
    expect(bodiesFor(fetchFn, "/api/explain")[0].source).toBe(SAMPLE_SOURCE);
  });
});
```

**Verify** (from `web/`):
- `npm test` → `Test Files  3 passed (3)` and `Tests  30 passed (30)` (clusters 10, api 5, App 15)
- `npm run build` → exit 0; the output ends with `✓ built in …`; `ls dist/index.html dist/assets | head` lists `index.html` and an `editor.worker-*.js` asset. Vite may also print a `[PLUGIN_TIMINGS]` note; that is informational.
- From the project root: `git status --porcelain -uall web | grep -c "web/dist/\|node_modules"` → `0`

Commit: `web: editor with markers, root-cause panel, unverified fix diff (plan 013 step 3)`, staging `web/src/components/CodeEditor.tsx web/src/components/FixDiff.tsx web/src/components/ErrorPanel.tsx web/src/App.tsx web/src/monaco-setup.ts web/src/main.tsx web/src/App.css web/src/App.test.tsx`.

### Step 4: README and an end-to-end proxy smoke run

4a. Create `web/README.md`, exact content:

````markdown
# Compiler Error Assistant: web UI

React + TypeScript + Vite front end for the course compiler (plan 013). It shows
the program in a Monaco editor with inline error markers, and an error panel with
**one card per root cause** (PRD F2), a fatal/warning badge and the summary line
(PRD F4), and per-root **Explain**, **Expand**, **Suggest fix** and **Ask**
actions (PRD F3). Suggested fixes open in a diff view labelled
**Unverified preview**: milestone 2 does not compile-check fixes (that is F8,
milestone 4).

The UI talks only to `/api/*`. In development the Vite server proxies `/api` to
the FastAPI backend at `http://127.0.0.1:8000` (`src/cea/api.py`, plan 012).
Only the source text and record ids are sent: never a filename or a student's
name.

## How to run the demo

You need Python 3.11+ with the project venv, and Node 22 with npm 11.

1. **Backend** (terminal 1, project root):

       python -m venv .venv                                  # once
       .venv/Scripts/python -m pip install -r requirements-dev.txt
       .venv/Scripts/python -m uvicorn cea.api:app --reload --app-dir src

   For AI explanations and fixes, set the `CEA_LLM_*` variables described in
   `.env.example` (Gemini primary, Ollama fallback) before starting uvicorn.
   Without them, compiling still works and the AI buttons show
   "The AI assistant is not configured".

2. **Front end** (terminal 2):

       cd web
       npm install                                           # once; uses package-lock.json
       npm run dev

3. Open `http://localhost:5173`. The header shows `AI: primary`, `fallback`,
   `none` (backend up, no LLM configured) or `offline` (backend not running).

### Demo script

1. Press **Compile** on the sample program. The panel says
   `6 fatal, 1 warning` and "3 root causes shown for 7 errors"; the editor
   underlines every error.
2. The `SEM-UNDECLARED-VAR` card shows **+4 related**: click it to see the four
   later uses of `i` grouped under the first one (F2).
3. Click **Explain** (two sentences at most) and then **Expand** (the full
   explanation) on any card (F3).
4. Click **Suggest fix** on the missing-`;` card: a diff opens with the
   **Unverified preview** badge. Apply the change yourself in the editor; the
   assistant never edits your code.
5. Ask an off-topic question (for example "What is the capital of France?"):
   the answer is marked **Out of scope** (F3 scope guard).
6. Edit the code: the panel warns that results are stale until you compile again.

## Checks

    npm test          # Vitest + React Testing Library (Monaco and fetch are mocked)
    npm run build     # type-check (tsc) and production build into web/dist/

`npm run build` output (`dist/`) and `node_modules/` are git-ignored.

## Notes

- Monaco is bundled from the local `monaco-editor` package (`src/monaco-setup.ts`),
  so the editor works offline; nothing is downloaded from a CDN.
- Port 5173 is fixed (`strictPort`), because the backend's CORS setting allows
  only `http://localhost:5173`. If the port is busy, stop the other process.
- Dependency versions are exact in `package.json` and locked in `package-lock.json`.
````

4b. Append this section to the END of the root `README.md` (exact content, preceded by one blank line):

```markdown
## Run the web UI (milestone 2)

The React + Monaco UI lives in `web/` (plan 013). Start the backend first (previous section), then `cd web && npm install && npm run dev` and open `http://localhost:5173`. See `web/README.md`, "How to run the demo".
```

4c. Smoke-run the proxy. First check the ports are free: `netstat -ano | grep -E ":(8000|5173) .*LISTEN"` → no output (if either is busy, STOP and report; do not change the ports). Then run this as ONE Git Bash command from the project root. It starts both servers, loads the page and compiles through the Vite proxy, then stops both:
```
.venv/Scripts/python -m uvicorn cea.api:app --app-dir src --port 8000 > /tmp/cea-api.log 2>&1 &
(cd web && npm run dev > /tmp/cea-web.log 2>&1 &)
sleep 8
curl -s http://localhost:5173/ | grep -c "<title>Compiler Error Assistant</title>"
curl -s -X POST -H "Content-Type: application/json" -d '{"source":"int main(void) { return 0; }\n"}' http://localhost:5173/api/compile; echo
kill %1
powershell -NoProfile -Command 'Get-CimInstance Win32_Process | Where-Object { $_.Name -eq "node.exe" -and $_.CommandLine -like "*vite*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }'
sleep 2; netstat -ano | grep -E ":(8000|5173) .*LISTEN"; echo "smoke done"
```
Expected output: `1`, then `{"ok":true,"summary":"0 fatal, 0 warnings","records":[],"clusters":[]}`, then `smoke done` with no `LISTEN` line before it. (Keep the `$_.Name -eq "node.exe"` filter: without it the pattern also matches, and kills, the shell running this command.)

Optional, if you have a browser tool: open `http://localhost:5173`, press Compile, and check the panel shows "3 root causes shown for 7 errors" and a "+4 related" button.

**Verify**:
- `grep -c "How to run the demo" web/README.md` → `1` (the heading) and `grep -c "Run the web UI (milestone 2)" README.md` → `1`
- `cd web && npm test` → `Tests  30 passed (30)`

Commit: `docs: web UI README and how to run the demo (plan 013 step 4)`, staging `web/README.md README.md`.

### Step 5: Status row

In `plans/README.md`, "Milestone 2" table, set row 013's Status to `DONE (30 web tests; build ok)`. Commit `plans: 013 done`, staging `plans/README.md`.

## Test plan

- `web/src/clusters.test.ts` (10): cluster views in backend order with symptoms; unknown ids skipped; clean program; `relatedLabel` for 0/1/4; one marker per record; marker severities (fatal root Error, warning root Warning, symptoms Info); inclusive-to-exclusive end column; symptom messages point at their root.
- `web/src/api.test.ts` (5): `/api/compile` gets only `{source}` with a JSON content type; explain/fix/ask get exactly the contract fields (no filename); health uses GET; `ApiError` carries the server's `detail`; a non-JSON error body falls back to the status line.
- `web/src/App.test.tsx` (15): sample + hint on load; `AI: none` / `AI: offline`; compile shows the F4 summary and "3 root causes shown for 7 errors"; one card per root (not per record); fatal/warning badges; "+4 related" collapsed then expanded (and absent on roots without symptoms); `setModelMarkers` gets 7 markers; Explain sends `short`, Expand sends `expand`; Suggest fix shows the diff with the **Unverified preview** badge and never "Verified"; a no-change fix shows a note instead of a diff; Ask trims the question and shows a refused answer as "Out of scope:"; a 413 on compile and a 503 on explain are shown as alerts; a clean program says "No errors"; after an edit the stale notice appears and actions still send the compiled source.
- Final: `npm test` → 3 files, 30 tests; `npm run build` exit 0.

## Done criteria

- [ ] `cd web && npm test` → `Test Files  3 passed (3)`, `Tests  30 passed (30)`
- [ ] `cd web && npm run build` → exit 0
- [ ] `cd web && npm ls --depth=0` → the 15 exact versions of Step 1
- [ ] `git ls-files web | grep -c "node_modules\|^web/dist/"` → `0`, and `git ls-files web/package-lock.json` → prints the path
- [ ] `git check-ignore web/node_modules web/dist` → both printed
- [ ] `.venv/Scripts/python -m pytest -q` → the same count as before this plan (no Python change)
- [ ] `git diff --name-only main..HEAD` lists only `.gitignore`, `README.md`, `plans/README.md` and files under `web/` from the Scope list (27 paths in all, `web/package-lock.json` included)
- [ ] `plans/README.md` row 013 updated

## STOP conditions

Stop and report (do not improvise) if:
- Any drift check fails (no `web/` expected; plan 012 must be merged; Node 22 / npm 11).
- `npm install` fails, or `npm ls --depth=0` shows a version other than the 15 listed. Do not change versions, add `--legacy-peer-deps`, or run `npm audit fix`; report the output.
- `npm audit --audit-level=high` exits non-zero (a new high or critical advisory appeared).
- A step's test count or the build differs from the plan and your files are identical to it (paste the failing test names and messages).
- `npm run build` fails on the Monaco imports in `src/monaco-setup.ts` (the monaco-editor 0.57 path layout differs from what this plan assumes).
- Making a test pass seems to need a change to the backend, its response shapes, or any Python file.
- The UI would need to send a filename, a path or any student identity to the backend.
- Anything would require reading `tests/corpus/heldout/`.

## Maintenance notes

- `web/src/types.ts` mirrors `src/cea/api.py` (plan 012). Change both together; `src/test/fixtures.ts` is a captured backend response and must be re-captured if record fields change.
- When F8 (milestone 4) verifies fixes, the backend's `verified: true` makes `FixDiff` show a "Verified" badge; unverified fixes keep the "Unverified preview" badge. The PRD's final rule is "never show unverified fixes", so milestone 4 should hide the diff when `verified` is false instead of labelling it; that is a one-line change in `FixDiff.tsx`.
- F5/F9 (verbosity and student profile, milestone 3+) will add UI state; keep it out of `/api` requests unless the contract says so (privacy).
- A reviewer should check: the panel always sends `compiled.source`, never the live editor text; no `dangerouslySetInnerHTML` anywhere (all model text is rendered as plain text); the `strictPort`/CORS pairing; the Monaco mock keeps tests free of Monaco and network.
- The production bundle is about 3 MB (mostly Monaco). Code-splitting is not worth it for a local demo.

## Open questions (advisor → owner)

1. **Ask box.** The contract lists Expand and Suggest fix; the plan also adds Explain (short, the PRD's default response) and a one-line Ask box (the PRD's "follow-up chat", backed by `/api/ask`). Drop either if you want the minimal contract UI.
2. **Bleeding-edge toolchain.** The pinned versions are the latest on 2026-10-11 (TypeScript 7.0, Vite 8.3, Vitest 5.0, React 19.3). All checks pass; if the course machines need older Node, pin the previous majors instead.
3. **DOMPurify advisories.** 2 low-severity advisories come with `monaco-editor` 0.57.0 (decision 8). Accept, or wait for a Monaco release that bumps DOMPurify.
4. **Showing unverified fixes.** Milestone 2 shows them labelled (owner decision 2026-10-10). The PRD's F8 acceptance ("no unverified fix is ever displayed as a fix") still applies from milestone 4.

## Viva notes (ask the executor to report)

End your report with a **Viva notes** list covering at least: how the UI realises F2 (one card per cluster, "+N related" collapsed), F3 (Explain short vs Expand, Ask with refusal shown, fix diff) and F4 (badges and the summary line); why fix diffs carry an "Unverified preview" badge and there is no Apply button; why the panel sends the compiled source (stateless backend); why Monaco is bundled locally and mocked in tests; how markers map severity and the inclusive span end; the Vite proxy and CORS/port pairing; the exact installed versions and the real test counts (15 after Step 2, 30 after Step 3).
