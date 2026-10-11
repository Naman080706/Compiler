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
  engine?: "cea" | "gcc"; // which front end produced the record (may be absent)
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
export type Verbosity = "beginner" | "expert";
export type VerbosityChoice = Verbosity | "auto"; // F5 toggle; "auto" lets the F9 profile choose the depth

export interface Explanation {
  text: string;
  rule_ref: string;
  cited_rule: string | null;
  mode: ExplainMode;
  verbosity: Verbosity;
  citations: string[]; // ids of the retrieved rule / fix-pattern chunks the explanation is grounded in (F7)
  personalised?: Personalised;
}

// F8: the server sends a diff only when the patch was re-compiled and verified; otherwise diff is "".
export interface FixSuggestion {
  diff: string;
  patched_source: string;
  verified: boolean;
  attempts: number;
  reason: string;
}

// F9: how the student's profile shaped one explanation (only present when a student id was sent).
export interface Personalised {
  category: string | null;
  hits: number;
  depth: "terse" | "full";
  override: boolean; // true when the manual F5 toggle chose the style
}

export interface ProfileCategory {
  category: string;
  hits: number;
  depth: "terse" | "full";
}

export interface ProfileView {
  student_id: string;
  threshold: number;
  categories: ProfileCategory[];
}

export interface Answer {
  text: string;
  refused: boolean;
}

// One question/answer exchange in a card's own thread (F6); kept per error on the client.
export interface ChatTurn {
  question: string;
  answer: string;
  refused: boolean;
}

export interface Health {
  status: string;
  llm: "primary" | "fallback" | "none";
}
