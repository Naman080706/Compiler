// The error panel (PRD F2/F3/F4): one card per root cause, a fatal/warning
// badge, a collapsed "+N related" list of symptoms, and the per-root
// Explain / Expand / Suggest fix / Ask actions.
import { useState, type FormEvent } from "react";
import { ask, explain, suggestFix } from "../api";
import { relatedLabel, type ClusterView } from "../clusters";
import type { Answer, Explanation, FixSuggestion } from "../types";
import FixDiff from "./FixDiff";

interface PanelProps {
  views: ClusterView[];
  source: string; // the source these records came from (the server is stateless)
}

export default function ErrorPanel({ views, source }: PanelProps) {
  return (
    <ol className="clusters" aria-label="Root causes">
      {views.map((v) => (
        <RootCard key={v.root.id} view={v} source={source} />
      ))}
    </ol>
  );
}

interface CardProps {
  view: ClusterView;
  source: string;
}

export function RootCard({ view, source }: CardProps) {
  const { root, symptoms } = view;
  const [open, setOpen] = useState(false);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [fix, setFix] = useState<FixSuggestion | null>(null);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run<T>(call: () => Promise<T>, done: (value: T) => void) {
    setBusy(true);
    setError(null);
    try {
      done(await call());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function onAsk(e: FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (q) void run(() => ask(source, root.id, q), setAnswer);
  }

  return (
    <li className={`card ${root.severity}`} aria-label={`${root.code} at line ${root.line}`}>
      <div className="card-head">
        <span className={`badge ${root.severity}`}>{root.severity}</span>
        <code className="code">{root.code}</code>
        <span className="pos">
          line {root.line}, col {root.column}
        </span>
      </div>
      <p className="message">{root.message}</p>
      {symptoms.length > 0 && (
        <button type="button" className="related" aria-expanded={open} onClick={() => setOpen(!open)}>
          {relatedLabel(symptoms.length)}
        </button>
      )}
      {open && (
        <ul className="symptoms" aria-label={`Errors related to ${root.id}`}>
          {symptoms.map((s) => (
            <li key={s.id}>
              <code>{s.code}</code> line {s.line}, col {s.column}: {s.message}
            </li>
          ))}
        </ul>
      )}
      <div className="actions">
        <button type="button" disabled={busy} onClick={() => run(() => explain(source, root.id, "short"), setExplanation)}>
          Explain
        </button>
        <button type="button" disabled={busy} onClick={() => run(() => explain(source, root.id, "expand"), setExplanation)}>
          Expand
        </button>
        <button type="button" disabled={busy} onClick={() => run(() => suggestFix(source, root.id), setFix)}>
          Suggest fix
        </button>
      </div>
      {busy && (
        <p className="note" role="status">
          Asking the assistant...
        </p>
      )}
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {explanation && (
        <div className="explanation" data-mode={explanation.mode}>
          <p>{explanation.text}</p>
          <p className="rule">
            Rule: <code>{explanation.rule_ref}</code>
          </p>
        </div>
      )}
      {fix && <FixDiff original={source} fix={fix} />}
      <form className="ask" onSubmit={onAsk}>
        <input
          aria-label={`Question about ${root.id}`}
          placeholder="Ask about this error"
          maxLength={1000}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button type="submit" disabled={busy || question.trim() === ""}>
          Ask
        </button>
      </form>
      {answer && (
        <p className={answer.refused ? "answer refused" : "answer"}>
          {answer.refused && <strong>Out of scope: </strong>}
          {answer.text}
        </p>
      )}
    </li>
  );
}
