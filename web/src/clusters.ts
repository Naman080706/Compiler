// Pure helpers: turn the /api/compile response into the error-panel view (PRD F2:
// one root per cluster with a collapsed count of related symptoms) and into
// Monaco marker data (inline errors). No React, no Monaco import: unit-testable.
import type { CompileResponse, ErrorRecord } from "./types";

export interface ClusterView {
  root: ErrorRecord;
  symptoms: ErrorRecord[];
}

/** One entry per cluster, in the backend's order (roots by line, column). */
export function clusterViews(resp: CompileResponse): ClusterView[] {
  const byId = new Map(resp.records.map((r) => [r.id, r]));
  const views: ClusterView[] = [];
  for (const c of resp.clusters) {
    const root = byId.get(c.root_id);
    if (!root) continue;
    const symptoms = c.symptom_ids.map((id) => byId.get(id)).filter((r): r is ErrorRecord => r !== undefined);
    views.push({ root, symptoms });
  }
  return views;
}

export type Phase = ErrorRecord["phase"];
export const PHASES: Phase[] = ["lexical", "syntax", "semantic"];
export const PHASE_TITLES: Record<Phase, string> = { lexical: "Lexical", syntax: "Syntax", semantic: "Semantic" };

/** PRD F1: root causes grouped by the phase that caught them, in compiler order; empty groups are omitted. */
export function groupByPhase(views: ClusterView[]): { phase: Phase; views: ClusterView[] }[] {
  return PHASES.map((phase) => ({ phase, views: views.filter((v) => v.root.phase === phase) })).filter((g) => g.views.length > 0);
}

/** "Lexical 1 · Syntax 2 · Semantic 1": records per phase; phases with none are left out. */
export function phaseSummary(records: ErrorRecord[]): string {
  return PHASES.map((p) => [p, records.filter((r) => r.phase === p).length] as const)
    .filter(([, n]) => n > 0)
    .map(([p, n]) => `${PHASE_TITLES[p]} ${n}`)
    .join(" · ");
}

/** "+N related" for a cluster with N symptoms; "" for none. */
export function relatedLabel(count: number): string {
  return count > 0 ? `+${count} related` : "";
}

/** Monaco's MarkerSeverity values (monaco.MarkerSeverity), duplicated so this file needs no Monaco import. */
export const MarkerSeverity = { Hint: 1, Info: 2, Warning: 4, Error: 8 } as const;

export interface MarkerData {
  startLineNumber: number;
  startColumn: number;
  endLineNumber: number;
  endColumn: number;
  severity: number;
  message: string;
  code: string;
  source: string;
}

/** Inline markers: roots as Error (fatal) or Warning; symptoms as Info, pointing at their root. */
export function toMarkers(records: ErrorRecord[]): MarkerData[] {
  return records.map((r) => {
    const isRoot = r.root_id === r.id;
    const severity = !isRoot ? MarkerSeverity.Info : r.severity === "fatal" ? MarkerSeverity.Error : MarkerSeverity.Warning;
    return {
      startLineNumber: r.line,
      startColumn: r.column,
      endLineNumber: r.span_end.line,
      endColumn: r.span_end.column + 1, // span_end is inclusive; Monaco's end column is exclusive
      severity,
      message: isRoot ? r.message : `${r.message} (related to ${r.root_id})`,
      code: r.code,
      source: "cea",
    };
  });
}
