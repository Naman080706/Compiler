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
