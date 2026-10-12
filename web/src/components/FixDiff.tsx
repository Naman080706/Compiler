// A suggested fix (PRD F8): shown ONLY when the server verified it (the patch was
// re-compiled: the error is gone and no new fatal error appeared). Otherwise the
// student sees a note and the explanation; an unverified diff is never displayed.
import { DiffEditor } from "@monaco-editor/react";
import type { FixSuggestion } from "../types";

interface Props {
  original: string;
  fix: FixSuggestion;
}

export const NO_VERIFIED_FIX = "No verified fix found; see explanation";

export default function FixDiff({ original, fix }: Props) {
  if (!fix.verified || fix.patched_source === original) {
    return <p className="note">{NO_VERIFIED_FIX}</p>;
  }
  return (
    <section className="fix" aria-label="Verified fix">
      <div className="fix-head">
        <span className="badge verified">Verified</span>
        <span className="fix-note">
          This fix was compiled and checked (attempt {fix.attempts}): the error is gone and no new error appears.
        </span>
      </div>
      <div className="diff">
        <DiffEditor
          height="240px"
          language="c"
          original={original}
          modified={fix.patched_source}
          theme="cea-dark"
          options={{ automaticLayout: true, readOnly: true, renderSideBySide: false, minimap: { enabled: false }, scrollBeyondLastLine: false }}
        />
      </div>
    </section>
  );
}
