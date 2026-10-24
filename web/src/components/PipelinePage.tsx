// The Pipeline view (#/pipeline): shows what our compiler's three phases built for the
// current program — the token stream (lexer), the parse tree (parser) and the declared
// symbols (semantic analyser). Possible only because we own the compiler. Read-only.
// Feature #7: an "Animate" control steps through all three phases live — tokens appear
// one-by-one (lexer scanning), then the parse-tree lines grow (parser), then the symbol
// rows fill in (semantic analyser). A speed slider controls the pace.
import { useEffect, useRef, useState, type ReactNode } from "react";
import { analyze } from "../api";
import type { PipelineView } from "../types";
import AstTree from "./AstTree";

const BASE_MS = 480; // step delay = BASE_MS / speed, so higher speed = faster

/** Split `line` into the text before, inside and after a token's span (1-based `col`). */
export function splitSpan(line: string, col: number, len: number): [string, string, string] {
  const start = Math.max(0, col - 1);
  const end = Math.min(line.length, start + Math.max(1, len));
  return [line.slice(0, start), line.slice(start, end), line.slice(end)];
}

export interface Reveal {
  tokens: number; // how many tokens are revealed
  treeLines: number; // how many parse-tree lines are revealed
  symbols: number; // how many symbol rows are revealed
  done: boolean; // every token, line and symbol shown
}

/** How much of each phase to show at animation `step`: tokens first, then tree, then symbols. */
export function revealAt(step: number, tokenCount: number, treeCount: number, symbolCount: number): Reveal {
  const tokens = Math.max(0, Math.min(step, tokenCount));
  const treeLines = Math.max(0, Math.min(step - tokenCount, treeCount));
  const symbols = Math.max(0, Math.min(step - tokenCount - treeCount, symbolCount));
  return { tokens, treeLines, symbols, done: step >= tokenCount + treeCount + symbolCount };
}

export default function PipelinePage({ source }: { source: string }) {
  const [view, setView] = useState<PipelineView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [step, setStep] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [animating, setAnimating] = useState(false); // false = static full view
  const [speed, setSpeed] = useState(3); // 1 (slow) .. 8 (fast)
  const [treeView, setTreeView] = useState<"diagram" | "text">("diagram");
  const [selTok, setSelTok] = useState<number | null>(null); // clicked token (feature #1)
  const [selLine, setSelLine] = useState<number | null>(null); // highlighted source line
  const timer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);

  useEffect(() => {
    let live = true;
    analyze(source)
      .then((v) => live && (setView(v), setError(null), setAnimating(false), setPlaying(false), setSelTok(null), setSelLine(null)))
      .catch((e) => live && setError(e instanceof Error ? e.message : String(e)));
    return () => {
      live = false;
    };
  }, [source]);

  const treeLines = view ? view.tree.split("\n") : [];
  const tokenCount = view?.tokens.length ?? 0;
  const symbolCount = view?.symbols.length ?? 0;
  const reveal = revealAt(step, tokenCount, treeLines.length, symbolCount);

  useEffect(() => {
    if (!playing) return;
    timer.current = setInterval(() => setStep((s) => s + 1), BASE_MS / speed);
    return () => clearInterval(timer.current);
  }, [playing, speed]);

  useEffect(() => {
    if (reveal.done) setPlaying(false); // stop at the end
  }, [reveal.done]);

  function play() {
    if (!animating || reveal.done) setStep(0); // (re)start from the beginning
    setAnimating(true);
    setPlaying(true);
  }

  // When not animating, everything is revealed; "active" indices are only meaningful mid-run.
  const shown = animating ? reveal : { tokens: tokenCount, treeLines: treeLines.length, symbols: symbolCount, done: true };
  const lexing = shown.tokens < tokenCount;
  const parsing = !lexing && shown.treeLines < treeLines.length;
  const analysing = !lexing && !parsing && shown.symbols < symbolCount;
  const live = animating && playing;
  const activeTok = live && lexing ? shown.tokens - 1 : -1;
  const activeLine = live && parsing ? shown.treeLines - 1 : -1;
  const activeSym = live && analysing ? shown.symbols - 1 : -1;

  return (
    <main className="profile-page" aria-label="Compiler pipeline">
      <div className="profile-inner">
        <h2 className="page-title">Compiler pipeline</h2>
        <p className="note">
          How our compiler sees this program, phase by phase. Edit the code and come back to see it change.
        </p>
        {view && (
          <div className="phase-controls">
            <button type="button" className="primary" onClick={playing ? () => setPlaying(false) : play}>
              {playing ? "⏸ Pause" : animating && !reveal.done ? "▶ Resume" : reveal.done && animating ? "↻ Replay" : "▶ Animate"}
            </button>
            {animating && (
              <button type="button" onClick={() => (setAnimating(false), setPlaying(false))}>
                Show all
              </button>
            )}
            <label className="phase-speed">
              Speed
              <input
                type="range"
                min={1}
                max={8}
                step={1}
                value={speed}
                onChange={(e) => setSpeed(Number(e.target.value))}
                aria-label="Animation speed"
              />
            </label>
            {animating && (
              <span className="note phase-status">
                {lexing
                  ? `Lexing — token ${shown.tokens}/${tokenCount}`
                  : parsing
                    ? `Parsing — line ${shown.treeLines}/${treeLines.length}`
                    : analysing
                      ? `Analysing — symbol ${shown.symbols}/${symbolCount}`
                      : "Done"}
              </span>
            )}
          </div>
        )}
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {!view && !error && <p className="note">Analysing...</p>}
        {view && (
          <>
            <h3 className="phase-heading">Source</h3>
            <p className="note">Click a token below to light up the exact text it came from — or click a line to pick out its tokens.</p>
            <div className="source-view" aria-label="Source code">
              {source.split("\n").map((line, i) => {
                const lineNo = i + 1;
                const sel = lineNo === selLine;
                const tok = selTok != null ? view.tokens[selTok] : null;
                let body: ReactNode = line || " ";
                if (sel && tok && tok.line === lineNo) {
                  const [a, b, c] = splitSpan(line, tok.col, tok.text.length);
                  body = (
                    <>
                      {a}
                      <mark className="src-span">{b}</mark>
                      {c}
                    </>
                  );
                }
                return (
                  <div
                    key={i}
                    className={`src-line${sel ? " src-line-sel" : ""}`}
                    onClick={() => (setSelLine(lineNo), setSelTok(null))}
                  >
                    <span className="src-ln">{lineNo}</span>
                    <span className="src-code">{body}</span>
                  </div>
                );
              })}
            </div>

            <h3 className="phase-heading">1 · Lexer — tokens ({view.tokens.length})</h3>
            <div className="tokens" aria-label="Token stream">
              {view.tokens.map((t, i) => (
                <span
                  key={i}
                  className={`tok tok-click${i >= shown.tokens ? " tok-dim" : ""}${i === activeTok ? " tok-active" : ""}${t.line === selLine ? " tok-sel" : ""}${i === selTok ? " tok-pick" : ""}`}
                  title={`${t.kind} at line ${t.line}, col ${t.col}`}
                  onClick={() => (setSelTok(i), setSelLine(t.line))}
                >
                  <span className="tok-kind">{t.kind}</span>
                  <span className="tok-text">{t.text}</span>
                </span>
              ))}
            </div>

            <h3 className="phase-heading">2 · Parser — parse tree</h3>
            <div className="verbosity tree-toggle" role="group" aria-label="Parse-tree view">
              <button type="button" aria-pressed={treeView === "diagram"} onClick={() => setTreeView("diagram")}>
                Diagram
              </button>
              <button type="button" aria-pressed={treeView === "text"} onClick={() => setTreeView("text")}>
                Indented
              </button>
            </div>
            {treeView === "diagram" && view.treeNodes ? (
              <AstTree root={view.treeNodes} revealCount={shown.treeLines} />
            ) : (
              <pre className="tree-text" aria-label="Parse tree">
                {treeLines.map((line, i) => (
                  <div
                    key={i}
                    className={`tree-line${i >= shown.treeLines ? " tree-pending" : ""}${i === activeLine ? " tree-active" : ""}`}
                  >
                    {line || " "}
                  </div>
                ))}
              </pre>
            )}

            <h3 className="phase-heading">3 · Semantic — symbol table</h3>
            {view.symbols.length === 0 ? (
              <p className="note">No symbols declared.</p>
            ) : (
              <table aria-label="Symbol table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Type</th>
                    <th>Kind</th>
                    <th>Line</th>
                  </tr>
                </thead>
                <tbody>
                  {view.symbols.map((s, i) => (
                    <tr
                      key={i}
                      className={`${i >= shown.symbols ? "tree-pending" : ""}${i === activeSym ? " sym-active" : ""}`}
                    >
                      <td>
                        <code>{s.name}</code>
                      </td>
                      <td>{s.type}</td>
                      <td>{s.kind}</td>
                      <td>{s.line}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>
    </main>
  );
}
