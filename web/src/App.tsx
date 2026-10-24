// The demo page: Monaco editor on the left, the F2 error panel on the right.
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { compile, correct, health, run as runProgram } from "./api";
import { clusterViews, compilerOutput, phaseSummary, runOutput } from "./clusters";
import CodeEditor from "./components/CodeEditor";
import ErrorPanel from "./components/ErrorPanel";
import OutputTerminal from "./components/OutputTerminal";
import FileTabs from "./components/FileTabs";
import CorrectionDialog from "./components/CorrectionDialog";
import { SAMPLE_SOURCE } from "./sample";
import type { CompileResponse, Correction, Health, RunResult, VerbosityChoice } from "./types";
import ProfilePage from "./components/ProfilePage";
import PipelinePage from "./components/PipelinePage";
import PracticePage from "./components/PracticePage";
import PredictiveHint from "./components/PredictiveHint";
import Splitter, { useSplit, VSplitter, useTerminalHeight } from "./components/Splitter";

const VERBOSITY_KEY = "cea.verbosity";

// F5: the choice lasts for the browser session; the default "auto" lets the F9 profile pick the depth,
// and Beginner / Expert always override it. Storage can be blocked, so every access is guarded.
function loadVerbosity(): VerbosityChoice {
  try {
    const v = window.sessionStorage.getItem(VERBOSITY_KEY);
    return v === "expert" || v === "beginner" ? v : "auto";
  } catch {
    return "auto";
  }
}

function saveVerbosity(v: VerbosityChoice) {
  try {
    window.sessionStorage.setItem(VERBOSITY_KEY, v);
  } catch {
    // ignore: the toggle still works for this page load
  }
}

// Hash routing without a router library: "#/" is the editor, "#/profile" the student's own page.
export type Route = "editor" | "profile" | "pipeline" | "practice";

export function routeFromHash(hash: string): Route {
  const first = hash.replace(/^#\/?/, "").split(/[/?]/)[0];
  return first === "profile" || first === "pipeline" || first === "practice" ? first : "editor";
}

function useRoute(): [Route, (r: Route) => void] {
  const [route, setRoute] = useState<Route>(() => routeFromHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(routeFromHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return [route, (r) => { window.location.hash = r === "editor" ? "#/" : `#/${r}`; }];
}

interface Compiled {
  source: string;
  resp: CompileResponse;
  run: number; // remounts the panel so per-root state never outlives its compile
}

// One open file (tab). Each keeps its own source and its own last compile, so
// switching tabs switches the error panel and terminal with it.
interface RunState {
  result: RunResult;
  source: string; // the source that produced this output; shown only while it still matches
}

interface OpenFile {
  id: string;
  name: string;
  source: string;
  compiled: Compiled | null;
  run: RunState | null; // last Run's output for this file (the program's actual stdout)
  error: string | null;
}

let seq = 0;
const uid = () => `f${++seq}-${Math.random().toString(16).slice(2, 8)}`;
const makeFile = (name: string, source: string): OpenFile => ({ id: uid(), name, source, compiled: null, run: null, error: null });

export default function App() {
  const [files, setFiles] = useState<OpenFile[]>(() => [makeFile("program.c", SAMPLE_SOURCE)]);
  const [activeId, setActiveId] = useState<string>(() => files[0].id);
  const [busy, setBusy] = useState(false);
  const [llm, setLlm] = useState<Health["llm"] | "offline" | null>(null);
  const [route, goTo] = useRoute();
  const [verbosity, setVerbosity] = useState<VerbosityChoice>(loadVerbosity);
  const runSeq = useRef(0);
  const untitled = useRef(0);
  const [compiles, setCompiles] = useState(0); // bumps the profile dashboard after each compile/correction
  // F8 whole-program "Correct": the result opens in a modal; applying it replaces the active file's source.
  const [correction, setCorrection] = useState<Correction | null>(null);
  const [correcting, setCorrecting] = useState(false);
  const [running, setRunning] = useState(false); // gcc build + execute in progress

  const active = files.find((f) => f.id === activeId) ?? files[0];

  const patchFile = useCallback(
    (id: string, partial: Partial<OpenFile>) => setFiles((prev) => prev.map((f) => (f.id === id ? { ...f, ...partial } : f))),
    [],
  );

  function chooseVerbosity(v: VerbosityChoice) {
    setVerbosity(v);
    saveVerbosity(v);
  }

  useEffect(() => {
    health()
      .then((h) => setLlm(h.llm))
      .catch(() => setLlm("offline"));
  }, []);

  function setSource(src: string) {
    patchFile(activeId, { source: src });
  }

  async function onCompile() {
    const id = activeId;
    const src = files.find((f) => f.id === id)?.source ?? "";
    setBusy(true);
    patchFile(id, { error: null });
    try {
      const resp = await compile(src);
      runSeq.current += 1;
      patchFile(id, { compiled: { source: src, resp, run: runSeq.current }, run: null });
      setCompiles((n) => n + 1);
    } catch (e) {
      patchFile(id, { error: e instanceof Error ? e.message : String(e) });
    } finally {
      setBusy(false);
    }
  }

  async function onRun() {
    const id = activeId;
    const src = files.find((f) => f.id === id)?.source ?? "";
    setRunning(true);
    patchFile(id, { error: null });
    try {
      const result = await runProgram(src);
      patchFile(id, { run: { result, source: src } });
    } catch (e) {
      patchFile(id, { error: e instanceof Error ? e.message : String(e) });
    } finally {
      setRunning(false);
    }
  }

  async function onCorrect() {
    const id = activeId;
    const src = files.find((f) => f.id === id)?.source ?? "";
    setCorrecting(true);
    patchFile(id, { error: null });
    try {
      const result = await correct(src);
      setCorrection(result);
      setCompiles((n) => n + 1); // the click was counted server-side; refresh the profile dashboard
    } catch (e) {
      patchFile(id, { error: e instanceof Error ? e.message : String(e) });
    } finally {
      setCorrecting(false);
    }
  }

  function applyCorrection() {
    if (correction) setSource(correction.corrected_source);
    setCorrection(null);
  }

  function newFile() {
    untitled.current += 1;
    const f = makeFile(`untitled-${untitled.current}.c`, "");
    setFiles((prev) => [...prev, f]);
    setActiveId(f.id);
  }

  async function openFiles(list: FileList) {
    const added: OpenFile[] = [];
    for (const file of Array.from(list)) {
      try {
        added.push(makeFile(file.name || "untitled.c", await file.text()));
      } catch {
        // skip a file the browser could not read; the others still open
      }
    }
    if (added.length === 0) return;
    setFiles((prev) => [...prev, ...added]);
    setActiveId(added[added.length - 1].id);
  }

  function renameFile(id: string, name: string) {
    const trimmed = name.trim();
    if (trimmed) patchFile(id, { name: trimmed });
  }

  function closeFile(id: string) {
    setFiles((prev) => {
      const idx = prev.findIndex((f) => f.id === id);
      if (idx === -1) return prev;
      const next = prev.filter((f) => f.id !== id);
      if (next.length === 0) {
        const fresh = makeFile("program.c", SAMPLE_SOURCE);
        setActiveId(fresh.id);
        return [fresh];
      }
      if (id === activeId) setActiveId(next[Math.min(idx, next.length - 1)].id);
      return next;
    });
  }

  const [split, setSplit] = useSplit();
  const [termHeight, setTermHeight] = useTerminalHeight();
  const compiled = active.compiled;
  const error = active.error;
  const views = compiled ? clusterViews(compiled.resp) : [];
  const stale = compiled !== null && compiled.source !== active.source;
  const count = compiled?.resp.records.length ?? 0;
  // The OUTPUT panel shows the program's actual output after Run, or the compiler diagnostics after Compile.
  const liveRun = active.run && active.run.source === active.source ? active.run.result : null;
  const outLines = liveRun ? runOutput(liveRun, active.name) : compiled ? compilerOutput(compiled.resp, active.name) : null;
  const tabs = files.map((f) => ({ id: f.id, name: f.name, dirty: f.compiled === null || f.compiled.source !== f.source }));

  return (
    <div className="app">
      <header className="top">
        <h1>Compiler Error Assistant</h1>
        <span className="llm">AI: {llm ?? "..."}</span>
        {route === "editor" && (
        <>
        <div className="verbosity" role="group" aria-label="Explanation style">
          {(["auto", "beginner", "expert"] as const).map((v) => (
            <button key={v} type="button" aria-pressed={verbosity === v} onClick={() => chooseVerbosity(v)}>
              {v === "auto" ? "Auto" : v === "beginner" ? "Beginner" : "Expert"}
            </button>
          ))}
        </div>
        <button type="button" className="primary" onClick={onCompile} disabled={busy || correcting || running}>
          {busy ? "Compiling..." : "Compile"}
        </button>
        <button type="button" className="run-btn" onClick={onRun} disabled={busy || correcting || running || active.source.trim() === ""}
          title="Compile with gcc and run the program; its output appears in the OUTPUT panel">
          {running ? "Running..." : "▶ Run"}
        </button>
        </>
        )}
        {route === "editor" ? (
          <>
            <button type="button" className="nav" onClick={() => goTo("pipeline")}>Pipeline</button>
            <button type="button" className="nav" onClick={() => goTo("practice")}>Practice</button>
            <button type="button" className="nav" onClick={() => goTo("profile")}>Profile</button>
          </>
        ) : (
          <button type="button" className="nav" onClick={() => goTo("editor")}>Back to editor</button>
        )}
      </header>
      {route === "profile" && <ProfilePage refreshKey={compiles} />}
      {route === "pipeline" && <PipelinePage source={active.source} />}
      {route === "practice" && <PracticePage />}
      <main className="layout" hidden={route !== "editor"} style={{ "--split": `${split}%` } as CSSProperties}>
        <div className="editor-pane">
          <FileTabs files={tabs} activeId={activeId} onSelect={setActiveId} onClose={closeFile} onNew={newFile} onOpen={openFiles} onRename={renameFile} />
          <PredictiveHint source={active.source} />
          <div className="editor-wrap">
            <CodeEditor value={active.source} onChange={setSource} records={compiled?.resp.records ?? []} />
          </div>
          <VSplitter height={termHeight} onChange={setTermHeight} />
          <OutputTerminal lines={outLines} busy={busy} running={running} stale={stale} error={error} height={termHeight} filename={active.name} />
        </div>
        <Splitter split={split} onChange={setSplit} />
        <aside className="panel" aria-label="Errors">
          <div className="panel-scroll">
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
              {count > 0 && (
                <p className="note" data-testid="phase-summary">
                  {phaseSummary(compiled.resp.records)}
                </p>
              )}
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
                <ErrorPanel key={`${active.id}:${compiled.run}`} views={views} source={compiled.source} verbosity={verbosity === "auto" ? undefined : verbosity} />
              )}
            </>
          )}
          </div>
          {compiled && views.length > 0 && (
            <div className="panel-foot">
              <button type="button" className="primary" onClick={onCorrect} disabled={busy || correcting}
                title="Rewrite the whole program so it compiles, with a summary of the changes">
                {correcting ? "Correcting..." : "Correct whole program"}
              </button>
            </div>
          )}
        </aside>
      </main>
      {correction && (
        <CorrectionDialog
          original={active.source}
          correction={correction}
          onApply={applyCorrection}
          onClose={() => setCorrection(null)}
        />
      )}
    </div>
  );
}
