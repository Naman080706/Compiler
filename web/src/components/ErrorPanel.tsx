// The error panel (PRD F2/F3/F4): one card per root cause, a fatal/warning
// badge, a collapsed "+N related" list of symptoms, and the per-root
// Explain / Expand / Suggest fix / Ask actions.
import { useEffect, useState, type FormEvent } from "react";
import { ask, explain, suggestFix } from "../api";
import { groupByPhase, PHASE_TITLES, relatedLabel, type ClusterView } from "../clusters";
import type { ChatTurn, Explanation, FixSuggestion, Verbosity } from "../types";
import FixDiff from "./FixDiff";

interface PanelProps {
  views: ClusterView[];
  source: string; // the source these records came from (the server is stateless)
  verbosity?: Verbosity; // F5 manual choice; undefined = automatic (F9 profile)
}

export default function ErrorPanel({ views, source, verbosity }: PanelProps) {
  return (
    <div>
      {groupByPhase(views).map((g) => (
        <section key={g.phase} className="phase-group" aria-label={`${PHASE_TITLES[g.phase]} errors`}>
          <h3 className="phase-heading">
            {PHASE_TITLES[g.phase]} errors ({g.views.length})
          </h3>
          <ol className="clusters" aria-label={`${PHASE_TITLES[g.phase]} root causes`}>
            {g.views.map((v) => (
              <RootCard key={v.root.id} view={v} source={source} verbosity={verbosity} />
            ))}
          </ol>
        </section>
      ))}
    </div>
  );
}

interface CardProps {
  view: ClusterView;
  source: string;
  verbosity?: Verbosity;
}

export function RootCard({ view, source, verbosity }: CardProps) {
  const { root, symptoms } = view;
  const [open, setOpen] = useState(false);
  const [explanation, setExplanation] = useState<Explanation | null>(null);
  const [fix, setFix] = useState<FixSuggestion | null>(null);
  const [thread, setThread] = useState<ChatTurn[]>([]); // F6: this error's own chat history
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

  // F5: switching the toggle re-renders an explanation already on screen in the new style (same mode).
  useEffect(() => {
    if (explanation) {
      void run(() => explain(source, root.id, explanation.mode, verbosity), setExplanation);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verbosity]);

  function onAsk(e: FormEvent) {
    e.preventDefault();
    const q = question.trim();
    if (!q) return;
    void run(
      () => ask(source, root.id, q, thread),
      (a) => {
        setThread((t) => [...t, { question: q, answer: a.text, refused: a.refused }]);
        setQuestion("");
      },
    );
  }

  return (
    <li className={`card ${root.severity}`} aria-label={`${root.code} at line ${root.line}`}>
      <div className="card-head">
        <span className={`badge ${root.severity}`}>{root.severity}</span>
        <span className={`badge phase ${root.phase}`}>{root.phase}</span>
        {root.engine === "gcc" && <span className="badge engine">via gcc</span>}
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
        <button type="button" disabled={busy} onClick={() => run(() => explain(source, root.id, "short", verbosity), setExplanation)}>
          Explain
        </button>
        <button type="button" disabled={busy} onClick={() => run(() => explain(source, root.id, "expand", verbosity), setExplanation)}>
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
        <div className="explanation" data-mode={explanation.mode} data-verbosity={explanation.verbosity}>
          <p>{explanation.text}</p>
          <p className="rule">
            Rule: <code>{explanation.rule_ref}</code>
          </p>
          {explanation.personalised?.depth === "full" && !explanation.personalised.override && (
            <p className="note" data-testid="depth-note">
              Fuller explanation: you have hit this kind of error ({explanation.personalised.category}){" "}
              {explanation.personalised.hits} times.
            </p>
          )}
          {explanation.citations && explanation.citations.length > 0 && (
            <p className="citations" aria-label="Cited sources">
              Grounded in:{" "}
              {explanation.citations.map((id, i) => (
                <span key={id}>
                  {i > 0 && ", "}
                  <code>{id}</code>
                </span>
              ))}
            </p>
          )}
        </div>
      )}
      {fix && <FixDiff original={source} fix={fix} />}
      {thread.length > 0 && (
        <ol className="thread" aria-label={`Conversation about ${root.id}`}>
          {thread.map((t, i) => (
            <li key={i}>
              <p className="q">
                <strong>You: </strong>
                {t.question}
              </p>
              <p className={t.refused ? "answer refused" : "answer"}>
                {t.refused && <strong>Out of scope: </strong>}
                {t.answer}
              </p>
            </li>
          ))}
        </ol>
      )}
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
    </li>
  );
}
