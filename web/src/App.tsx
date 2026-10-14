// The demo page: Monaco editor on the left, the F2 error panel on the right.
import { useEffect, useState, type CSSProperties } from "react";
import { compile, health } from "./api";
import { clusterViews, phaseSummary } from "./clusters";
import CodeEditor from "./components/CodeEditor";
import ErrorPanel from "./components/ErrorPanel";
import { SAMPLE_SOURCE } from "./sample";
import type { CompileResponse, Health, VerbosityChoice } from "./types";
import ProfilePage from "./components/ProfilePage";
import Splitter, { useSplit } from "./components/Splitter";

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
export type Route = "editor" | "profile";

export function routeFromHash(hash: string): Route {
  return hash.replace(/^#\/?/, "").split(/[/?]/)[0] === "profile" ? "profile" : "editor";
}

function useRoute(): [Route, (r: Route) => void] {
  const [route, setRoute] = useState<Route>(() => routeFromHash(window.location.hash));
  useEffect(() => {
    const onChange = () => setRoute(routeFromHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);
  return [route, (r) => { window.location.hash = r === "profile" ? "#/profile" : "#/"; }];
}

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
  const [route, goTo] = useRoute();
  const [verbosity, setVerbosity] = useState<VerbosityChoice>(loadVerbosity);

  function chooseVerbosity(v: VerbosityChoice) {
    setVerbosity(v);
    saveVerbosity(v);
  }

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

  const [split, setSplit] = useSplit();
  const views = compiled ? clusterViews(compiled.resp) : [];
  const stale = compiled !== null && compiled.source !== source;
  const count = compiled?.resp.records.length ?? 0;

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
        <button type="button" className="primary" onClick={onCompile} disabled={busy}>
          {busy ? "Compiling..." : "Compile"}
        </button>
        </>
        )}
        <button type="button" className="nav" onClick={() => goTo(route === "profile" ? "editor" : "profile")}>
          {route === "profile" ? "Back to editor" : "Profile"}
        </button>
      </header>
      {route === "profile" && <ProfilePage refreshKey={compiled?.run ?? 0} />}
      <main className="layout" hidden={route !== "editor"} style={{ "--split": `${split}%` } as CSSProperties}>
        <div className="editor-pane">
          <CodeEditor value={source} onChange={setSource} records={compiled?.resp.records ?? []} />
        </div>
        <Splitter split={split} onChange={setSplit} />
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
                <ErrorPanel key={compiled.run} views={views} source={compiled.source} verbosity={verbosity === "auto" ? undefined : verbosity} />
              )}
            </>
          )}
        </aside>
      </main>
    </div>
  );
}
