// Practice page (#/practice): drill the error categories you get wrong most. Shows one buggy
// program at a time (your weakest category first), you fix it, and "Check" compiles it — solved
// when it compiles. Reuses /api/compile and the Monaco editor; the drills live in drills.ts.
import { useEffect, useState } from "react";
import { compile, getProfile } from "../api";
import { DRILLS, orderDrills, type Drill } from "../drills";
import type { ErrorRecord } from "../types";
import CodeEditor from "./CodeEditor";

export default function PracticePage() {
  const [queue, setQueue] = useState<Drill[]>(DRILLS);
  const [idx, setIdx] = useState(0);
  const [source, setSource] = useState(DRILLS[0].code);
  const [records, setRecords] = useState<ErrorRecord[]>([]);
  const [result, setResult] = useState<"solved" | "trying" | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Order drills by the student's most-missed categories (best-effort; falls back to the default order).
  useEffect(() => {
    getProfile()
      .then((p) => {
        const top = [...p.categories].sort((a, b) => b.hits - a.hits).map((c) => c.category);
        setQueue(orderDrills(top));
      })
      .catch(() => setQueue(DRILLS));
  }, []);

  const drill = queue[idx];
  // Load the current drill's code whenever the drill changes (new index, or the queue reorders).
  useEffect(() => {
    setSource(drill.code);
    setRecords([]);
    setResult(null);
    setError(null);
  }, [drill.code]);

  async function check() {
    setBusy(true);
    setError(null);
    try {
      const resp = await compile(source);
      setRecords(resp.records);
      setResult(resp.ok ? "solved" : "trying");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const fatal = records.filter((r) => r.severity === "fatal").length;

  return (
    <main className="profile-page" aria-label="Practice">
      <div className="profile-inner">
        <h2 className="page-title">Practice</h2>
        <p className="note">
          Drill {idx + 1} of {queue.length} · category <code>{drill.category}</code> · fix the bug until it compiles.
        </p>
        <p className="drill-prompt">{drill.prompt}</p>

        <div className="drill-editor">
          <CodeEditor value={source} onChange={setSource} records={records} />
        </div>

        <div className="drill-actions">
          <button type="button" className="primary" onClick={check} disabled={busy}>
            {busy ? "Checking..." : "Check"}
          </button>
          <button type="button" onClick={() => setIdx((i) => (i + 1) % queue.length)}>Next drill →</button>
          <button type="button" onClick={() => { setSource(drill.code); setRecords([]); setResult(null); }}>Reset</button>
        </div>

        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        {result === "solved" && (
          <p className="drill-result solved" role="status">
            ✓ Solved — the program compiles. Try the next drill.
          </p>
        )}
        {result === "trying" && (
          <p className="drill-result trying" role="status">
            Not yet — {fatal} {fatal === 1 ? "error" : "errors"} left. The editor underlines them; fix and Check again.
          </p>
        )}
      </div>
    </main>
  );
}
