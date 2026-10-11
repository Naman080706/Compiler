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
