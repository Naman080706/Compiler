// The "Correct" result (PRD F8, whole program): a modal showing the rewritten
// program as a unified diff, a list of what was corrected, and an Apply button.
// The assistant never edits the student's code on its own — applying is one click.
import { useEffect, useRef } from "react";
import type { Correction } from "../types";

// Colour one unified-diff line: + added, - removed, @@ hunk header, else context.
function diffClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---")) return "diff-file";
  if (line.startsWith("@@")) return "diff-hunk";
  if (line.startsWith("+")) return "diff-add";
  if (line.startsWith("-")) return "diff-del";
  return "diff-ctx";
}

interface Props {
  original: string;
  correction: Correction;
  onApply: () => void;
  onClose: () => void;
}

export default function CorrectionDialog({ original, correction, onApply, onClose }: Props) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const changed = correction.corrected_source !== original;

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const status = !changed
    ? { cls: "ok", label: "Already compiles" }
    : correction.verified
      ? { cls: "ok", label: "Now compiles" }
      : { cls: "warn", label: `${correction.remaining_fatal} ${correction.remaining_fatal === 1 ? "error" : "errors"} remain` };

  return (
    <div className="modal-backdrop" role="presentation" onClick={onClose}>
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label="Correct whole program"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h2 className="modal-title">Correct whole program</h2>
          <span className={`badge correction-${status.cls}`}>{status.label}</span>
          <span className="fix-note">
            {correction.before_summary} → {correction.after_summary}
          </span>
          <button ref={closeRef} type="button" className="modal-x" aria-label="Close dialog" onClick={onClose}>
            ×
          </button>
        </div>

        <div className="modal-body">
          {!changed ? (
            <p className="note">The program already compiles — there was nothing to correct.</p>
          ) : (
            <>
              <h3 className="dash-sub">What was corrected</h3>
              {correction.changes.length > 0 ? (
                <ul className="changes" aria-label="What was corrected">
                  {correction.changes.map((c, i) => (
                    <li key={i}>{c}</li>
                  ))}
                </ul>
              ) : (
                <p className="note">{correction.reason || "The program was rewritten to fix the errors."}</p>
              )}
              {!correction.verified && (
                <p className="note stale" role="status">
                  This rewrite still has {correction.remaining_fatal}{" "}
                  {correction.remaining_fatal === 1 ? "error" : "errors"}. Apply it and compile again, or fix the rest
                  yourself.
                </p>
              )}
              <h3 className="dash-sub">Changes</h3>
              {correction.diff ? (
                <pre className="diff-text" aria-label="Unified diff of the correction">
                  {correction.diff.replace(/\n$/, "").split("\n").map((line, i) => (
                    <span key={i} className={`diff-line ${diffClass(line)}`}>
                      {line === "" ? " " : line}
                      {"\n"}
                    </span>
                  ))}
                </pre>
              ) : (
                <p className="note">The whole program was rewritten.</p>
              )}
            </>
          )}
        </div>

        <div className="modal-foot">
          <button type="button" onClick={onClose}>
            Close
          </button>
          <button type="button" className="primary" disabled={!changed} onClick={onApply}>
            Apply to editor
          </button>
        </div>
      </div>
    </div>
  );
}
