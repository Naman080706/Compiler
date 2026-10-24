// A terminal-styled output panel shown below the editor. It mirrors what the
// `python -m cea <file>` CLI prints: one line per root cause, "+N related"
// counts and the fatal/warning summary. Height is controlled by the parent
// (VSplitter); this component only renders the body at that height.
import { useEffect, useRef } from "react";
import type { OutLine } from "../clusters";

interface Props {
  lines: OutLine[] | null; // null until the first compile
  busy: boolean;
  running: boolean; // gcc build + execute in progress
  stale: boolean;
  error: string | null; // a backend/transport failure, shown in red
  height: number; // px, from useTerminalHeight
  filename?: string; // the active file's name, shown in the prompt
}

export default function OutputTerminal({ lines, busy, running, stale, error, height, filename = "program.c" }: Props) {
  const bodyRef = useRef<HTMLDivElement>(null);

  // Keep the newest output in view, the way a real terminal scrolls.
  useEffect(() => {
    const el = bodyRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines, busy, running, error]);

  return (
    <section className="terminal" style={{ height }} aria-label="Compiler output">
      <div className="terminal-head">
        <span className="terminal-dots" aria-hidden="true">
          <i style={{ background: "#F07167" }} />
          <i style={{ background: "#E0B88A" }} />
          <i style={{ background: "#8FBF8A" }} />
        </span>
        <span className="terminal-title">Output</span>
        {stale && !busy && (
          <span className="terminal-flag" role="status">
            stale — compile again
          </span>
        )}
      </div>
      <div className="terminal-body" ref={bodyRef} role="log" aria-live="polite">
        {running ? (
          <p className="term-line term-note">$ ./{filename.replace(/\.[^.]+$/, "")} — building and running…</p>
        ) : busy ? (
          <p className="term-line term-note">$ cea compile {filename} — compiling…</p>
        ) : error ? (
          <>
            <p className="term-line term-cmd">$ cea compile {filename}</p>
            <p className="term-line term-fatal">error: {error}</p>
          </>
        ) : lines ? (
          lines.map((l, i) => (
            <p key={i} className={`term-line term-${l.kind}`}>
              {l.text === "" ? " " : l.text}
            </p>
          ))
        ) : (
          <p className="term-line term-note">
            Press <strong>Compile</strong> to run the compiler and see its output here.
          </p>
        )}
      </div>
    </section>
  );
}
