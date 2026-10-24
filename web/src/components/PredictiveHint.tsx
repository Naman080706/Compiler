// Predictive personal hint (feature #1): a proactive, dismissible banner above the editor.
// It combines the student's own history (their most-repeated error category, from the F9 profile)
// with a cheap structural check (unbalanced { } or ( )), so it nudges before they even compile.
// shortcut: text-only heuristic (strips comments/strings, but is not a real lexer) and only the
// brace/paren categories are detected live; upgrade to a server pre-check if more categories are wanted.
import { useEffect, useState } from "react";
import { getProfile } from "../api";

const THRESHOLD = 3; // match the profile's "repeated mistake" threshold

/** Net open-minus-close count of two delimiters, ignoring comments and string/char literals. */
export function imbalance(source: string, open: string, close: string): number {
  const code = source
    .replace(/\/\/.*$/gm, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/"(\\.|[^"\\])*"/g, '""')
    .replace(/'(\\.|[^'\\])*'/g, "''");
  let n = 0;
  for (const ch of code) {
    if (ch === open) n++;
    else if (ch === close) n--;
  }
  return n;
}

export default function PredictiveHint({ source }: { source: string }) {
  const [topCategory, setTopCategory] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState("");

  useEffect(() => {
    getProfile()
      .then((p) => {
        const top = [...p.categories].filter((c) => c.hits >= THRESHOLD).sort((a, b) => b.hits - a.hits)[0];
        setTopCategory(top?.category ?? null);
      })
      .catch(() => setTopCategory(null));
  }, []);

  const hints: string[] = [];
  const braces = imbalance(source, "{", "}");
  const parens = imbalance(source, "(", ")");
  if (braces !== 0) hints.push(`${Math.abs(braces)} ${braces > 0 ? "unclosed" : "extra"} '${braces > 0 ? "{" : "}"}' — check your braces.`);
  if (parens !== 0) hints.push(`${Math.abs(parens)} ${parens > 0 ? "unclosed" : "extra"} '${parens > 0 ? "(" : ")"}' — check your parentheses.`);
  if (topCategory) hints.push(`Your most common mistake is ${topCategory} — watch for it as you type.`);

  const text = hints.join(" ");
  if (!text || text === dismissed) return null;

  return (
    <div className="hint-banner" role="status">
      <span className="hint-text">💡 {text}</span>
      <button type="button" className="hint-x" aria-label="Dismiss hint" onClick={() => setDismissed(text)}>
        ×
      </button>
    </div>
  );
}
