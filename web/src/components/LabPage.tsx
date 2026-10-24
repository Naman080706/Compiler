// The Lab (#/lab): three tools built on the parse tree our compiler produces —
//   Format   (#1): pretty-print the program back to tidy C (our own unparser)
//   Fold     (#5): the constant sub-expressions the compiler can pre-compute
//   Compare  (#2): a *structural* diff of two programs (formatting-only edits show nothing)
// All read-only on the backend; Format can write its result back to the active editor file.
import { useEffect, useState } from "react";
import { astdiff, fold, formatCode } from "../api";
import type { AstDiffResult, Fold, FormatResult } from "../types";

export default function LabPage({ source, onApply }: { source: string; onApply: (s: string) => void }) {
  const [fmt, setFmt] = useState<FormatResult | null>(null);
  const [fmtBusy, setFmtBusy] = useState(false);
  const [folds, setFolds] = useState<Fold[] | null>(null);
  const [other, setOther] = useState(source); // the "B" program to compare against
  const [diff, setDiff] = useState<AstDiffResult | null>(null);
  const [diffBusy, setDiffBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    fold(source)
      .then((r) => live && setFolds(r.folds))
      .catch((e) => live && setErr(e instanceof Error ? e.message : String(e)));
    setFmt(null); // the current format result is stale once the source changes
    return () => {
      live = false;
    };
  }, [source]);

  async function runFormat() {
    setFmtBusy(true);
    setErr(null);
    try {
      setFmt(await formatCode(source));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setFmtBusy(false);
    }
  }

  async function runDiff() {
    setDiffBusy(true);
    setErr(null);
    try {
      setDiff(await astdiff(source, other));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setDiffBusy(false);
    }
  }

  return (
    <main className="profile-page" aria-label="Lab">
      <div className="profile-inner">
        <h2 className="page-title">Lab</h2>
        <p className="note">Three tools that work on the parse tree our compiler builds — not on the text.</p>
        {err && (
          <p className="error" role="alert">
            {err}
          </p>
        )}

        <h3 className="phase-heading">Format</h3>
        <p className="note">Pretty-print the current program back to tidy, consistently-indented C.</p>
        <div className="phase-controls">
          <button type="button" className="primary" onClick={runFormat} disabled={fmtBusy}>
            {fmtBusy ? "Formatting…" : "Format program"}
          </button>
          {fmt?.ok && (
            <>
              <button type="button" onClick={() => onApply(fmt.formatted)}>
                Apply to editor
              </button>
              <button type="button" onClick={() => navigator.clipboard?.writeText(fmt.formatted)}>
                Copy
              </button>
            </>
          )}
        </div>
        {fmt && !fmt.ok && (
          <p className="note" role="status">
            {fmt.reason}
          </p>
        )}
        {fmt?.ok && (
          <pre className="tree-text" aria-label="Formatted code">
            {fmt.formatted}
          </pre>
        )}

        <h3 className="phase-heading">Constant folding</h3>
        <p className="note">Sub-expressions whose value the compiler can compute at compile time.</p>
        {folds === null ? (
          <p className="note">Analysing…</p>
        ) : folds.length === 0 ? (
          <p className="note">No constant expressions to fold in this program.</p>
        ) : (
          <table aria-label="Constant folds">
            <thead>
              <tr>
                <th>Expression</th>
                <th>Value</th>
                <th>Line</th>
              </tr>
            </thead>
            <tbody>
              {folds.map((f, i) => (
                <tr key={i}>
                  <td>
                    <code>{f.text}</code>
                  </td>
                  <td>
                    <code>{f.value}</code>
                  </td>
                  <td>{f.line}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        <h3 className="phase-heading">Compare (structural diff)</h3>
        <p className="note">
          Diffs the parse trees of the current program (A) and the one below (B), so reformatting, comments and
          whitespace don&apos;t count — only real structural changes show.
        </p>
        <textarea
          className="lab-textarea"
          aria-label="Program B"
          value={other}
          onChange={(e) => setOther(e.target.value)}
          spellCheck={false}
        />
        <div className="phase-controls">
          <button type="button" className="primary" onClick={runDiff} disabled={diffBusy}>
            {diffBusy ? "Comparing…" : "Compare A vs B"}
          </button>
          {diff && <span className="note">{diff.changed ? "Structural changes found" : "No structural change"}</span>}
        </div>
        {diff && (
          <pre className="tree-text diff-view" aria-label="Structural diff">
            {diff.rows.map((r, i) => (
              <div key={i} className={`diff-row diff-${r.tag}`}>
                {r.tag === "add" ? "+ " : r.tag === "remove" ? "- " : "  "}
                {r.text}
              </div>
            ))}
          </pre>
        )}
      </div>
    </main>
  );
}
