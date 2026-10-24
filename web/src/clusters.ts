// Pure helpers: turn the /api/compile response into the error-panel view (PRD F2:
// one root per cluster with a collapsed count of related symptoms) and into
// Monaco marker data (inline errors). No React, no Monaco import: unit-testable.
import type { CompileResponse, ErrorRecord, RunResult } from "./types";

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

/** One line of the terminal output panel, with a kind that selects its colour. */
export type OutKind = "cmd" | "fatal" | "warning" | "ok" | "note" | "plain";
export interface OutLine {
  text: string;
  kind: OutKind;
}

/**
 * The compiler's textual output, mirroring the `python -m cea <file>` CLI
 * (`cli.format_cluster`): one line per F2 root cause, a "+N related" count,
 * then the fatal/warning summary. Pure, so it is unit-tested.
 */
export function compilerOutput(resp: CompileResponse, filename = "program.c"): OutLine[] {
  const lines: OutLine[] = [{ text: `$ cea compile ${filename}`, kind: "cmd" }];
  const views = clusterViews(resp);
  if (views.length === 0) {
    lines.push({ text: `${filename}: no errors found.`, kind: "ok" });
  } else {
    for (const v of views) {
      const r = v.root;
      const related = v.symptoms.length > 0 ? ` (+${v.symptoms.length} related)` : "";
      lines.push({
        text: `${r.id} ${filename}:${r.line}:${r.column}: ${r.severity} [${r.code}] ${r.message}${related}`,
        kind: r.severity === "fatal" ? "fatal" : "warning",
      });
    }
  }
  lines.push({ text: "", kind: "plain" });
  lines.push({ text: resp.summary, kind: resp.ok ? "ok" : "fatal" });
  lines.push({ text: `exit status ${resp.ok ? 0 : 1}`, kind: "note" });
  return lines;
}

/** Body lines of captured output, dropping a single trailing newline so there is no blank last line. */
function outputBody(text: string): string[] {
  const trimmed = text.replace(/\n$/, "");
  return trimmed === "" ? [] : trimmed.split("\n");
}

/**
 * The OUTPUT panel's text for a Run: the program's actual stdout/stderr and its exit status —
 * or the gcc build error if it did not compile. Pure, so it is unit-tested.
 */
export function runOutput(r: RunResult, filename = "program.c"): OutLine[] {
  const prog = filename.replace(/\.[^.]+$/, "") || "program";
  const lines: OutLine[] = [{ text: `$ ./${prog}`, kind: "cmd" }];
  if (!r.gcc_available) {
    lines.push({ text: "gcc is not installed on this machine, so the program cannot be run.", kind: "note" });
    return lines;
  }
  if (!r.compiled) {
    lines.push({ text: "the program did not compile, so it was not run:", kind: "fatal" });
    for (const l of outputBody(r.compile_output)) lines.push({ text: l, kind: "plain" });
    return lines;
  }
  const out = outputBody(r.stdout);
  const err = outputBody(r.stderr);
  for (const l of out) lines.push({ text: l === "" ? " " : l, kind: "plain" });
  for (const l of err) lines.push({ text: l === "" ? " " : l, kind: "warning" });
  if (out.length === 0 && err.length === 0) lines.push({ text: "(the program produced no output)", kind: "note" });
  if (r.truncated) lines.push({ text: "...(output truncated)", kind: "note" });
  lines.push({ text: "", kind: "plain" });
  if (r.timed_out) {
    lines.push({ text: "[program stopped: it ran too long (over 5s) and was halted]", kind: "fatal" });
  } else {
    lines.push({ text: `[program exited with code ${r.exit_code}]`, kind: r.exit_code === 0 ? "ok" : "warning" });
  }
  return lines;
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
