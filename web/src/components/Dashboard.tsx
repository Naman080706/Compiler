// Compile analytics dashboard: stat tiles, a daily bar chart, errors by phase, top mistakes and
// recent activity. Charts are plain inline SVG; only counts are shown, never source code.
import type { Analytics } from "../types";

const TREND_ARROW = { down: "↓", up: "↑", flat: "→" } as const;
const TREND_WORD = { down: "improving", up: "rising", flat: "steady" } as const;

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="tile">
      <div className="tile-label">{label}</div>
      <div className="tile-value">{value}</div>
      {sub && <div className="tile-sub">{sub}</div>}
    </div>
  );
}

function DailyChart({ daily }: { daily: Analytics["daily"] }) {
  const W = 600;
  const H = 120;
  const slot = W / daily.length;
  const max = Math.max(1, ...daily.map((d) => d.compiles));
  const h = (n: number) => (n / max) * H;
  return (
    <svg className="chart" viewBox={`0 0 ${W} ${H + 16}`} role="img" aria-label={`Compiles per day, last ${daily.length} days`}>
      <line x1="0" x2={W} y1={H + 0.5} y2={H + 0.5} className="axis" />
      {daily.map((d, i) => {
        const x = i * slot + slot * 0.15;
        const w = slot * 0.7;
        return (
          <g key={d.date}>
            <title>{`${d.date}: ${d.compiles} compiles, ${d.successful} successful`}</title>
            <rect x={x} y={H - h(d.compiles)} width={w} height={h(d.compiles)} className="bar-all" />
            <rect x={x} y={H - h(d.successful)} width={w} height={h(d.successful)} className="bar-ok" />
          </g>
        );
      })}
      <text x="0" y={H + 13} className="axis-text">{daily[0].date.slice(5)}</text>
      <text x={W} y={H + 13} textAnchor="end" className="axis-text">{daily[daily.length - 1].date.slice(5)}</text>
    </svg>
  );
}

function PhaseBars({ phases }: { phases: Analytics["phases"] }) {
  const max = Math.max(1, ...phases.map((p) => p.count));
  return (
    <svg className="chart" viewBox="0 0 300 78" role="img" aria-label="Errors by phase">
      {phases.map((p, i) => (
        <g key={p.phase} transform={`translate(0 ${i * 26})`}>
          <text x="0" y="15" className="axis-text">{p.phase}</text>
          <rect x="70" y="4" width={Math.max(p.count ? 2 : 0, (p.count / max) * 190)} height="14" className="bar-fatal" />
          <text x="276" y="15" textAnchor="end" className="count-text">{p.count}</text>
        </g>
      ))}
    </svg>
  );
}

function Ranked({ title, rows, mono }: { title: string; rows: { name: string; count: number }[]; mono?: boolean }) {
  return (
    <div>
      <h3 className="dash-sub">{title}</h3>
      {rows.length === 0 ? (
        <p className="note">None yet.</p>
      ) : (
        <ul className="ranked" aria-label={title}>
          {rows.map((r) => (
            <li key={r.name}>
              <span className={mono ? "code" : undefined}>{r.name}</span>
              <span className="count">{r.count}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function when(ts: string): string {
  const d = new Date(ts);
  return `${d.toISOString().slice(0, 10)} ${d.toISOString().slice(11, 16)} UTC`;
}

export default function Dashboard({ data }: { data: Analytics }) {
  const t = data.totals;
  if (t.compiles === 0 && data.streak === 0) {
    return <p className="note">No compiles yet. Compile a program in the editor and your progress will appear here.</p>;
  }
  const { trend } = data;
  return (
    <div className="dashboard">
      <div className="tiles">
        <Tile label="Compiles" value={String(t.compiles)} sub={`last ${data.days} days`} />
        <Tile label="Success rate" value={`${Math.round(t.success_rate * 100)}%`} sub={`${t.successful} compiled cleanly`} />
        <Tile label="Streak" value={`${data.streak} ${data.streak === 1 ? "day" : "days"}`} />
        <Tile
          label="Errors per compile"
          value={`${t.avg_errors.toFixed(1)} ${TREND_ARROW[trend.direction]}`}
          sub={TREND_WORD[trend.direction]}
        />
      </div>

      <h3 className="dash-sub">Compiles per day</h3>
      <DailyChart daily={data.daily} />
      <p className="legend">
        <span className="key key-ok" /> compiled cleanly <span className="key key-all" /> had errors
      </p>

      <div className="dash-cols">
        <div>
          <h3 className="dash-sub">Errors by phase</h3>
          <PhaseBars phases={data.phases} />
        </div>
        <Ranked title="Top mistakes" rows={data.top_codes.map((c) => ({ name: c.code, count: c.count }))} mono />
        <Ranked title="Top categories" rows={data.top_categories.map((c) => ({ name: c.category, count: c.count }))} />
      </div>

      <h3 className="dash-sub">Recent activity</h3>
      <ul className="recent" aria-label="Recent compiles">
        {data.recent.map((r, i) => (
          <li key={`${r.ts}-${i}`}>
            <span className={r.ok ? "status ok" : "status fail"}>{r.ok ? "Compiled" : "Failed"}</span>
            <span className="pos">{when(r.ts)}</span>
            <span className="note">
              {r.fatal} {r.fatal === 1 ? "error" : "errors"}, {r.warnings} {r.warnings === 1 ? "warning" : "warnings"}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
