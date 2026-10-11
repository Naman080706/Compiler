// JSON shapes of the FastAPI backend (plan 012, plans/m2-architecture.md section 3).

export type Severity = "fatal" | "warning";

export interface ErrorRecord {
  id: string;
  phase: "lexical" | "syntax" | "semantic";
  code: string;
  severity: Severity;
  line: number;
  column: number;
  found: string;
  expected: string[];
  snippet: string;
  root_id: string;
  rule_ref: string;
  language: string;
  caused_by: string | null;
  span_end: { line: number; column: number };
  message: string;
}

export interface ClusterRef {
  root_id: string;
  symptom_ids: string[];
}

export interface CompileResponse {
  ok: boolean;
  summary: string;
  records: ErrorRecord[];
  clusters: ClusterRef[];
}

export type ExplainMode = "short" | "expand";

export interface Explanation {
  text: string;
  rule_ref: string;
  cited_rule: string | null;
  mode: ExplainMode;
}

export interface FixSuggestion {
  diff: string;
  patched_source: string;
  verified: boolean;
}

export interface Answer {
  text: string;
  refused: boolean;
}

export interface Health {
  status: string;
  llm: "primary" | "fallback" | "none";
}
