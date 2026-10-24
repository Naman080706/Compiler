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

// The result of gcc-building and running the program (POST /api/run) — the OUTPUT panel's
// "Run" shows this: the program's actual stdout/stderr, not the compiler's diagnostics.
export interface RunResult {
  gcc_available: boolean;
  compiled: boolean;
  compile_output: string; // gcc's message when the build failed
  stdout: string;
  stderr: string;
  exit_code: number | null;
  timed_out: boolean;
  truncated: boolean;
}

// One node of the parse tree (for the diagram view); pre-order matches the indented `tree` text.
export interface TreeNode {
  label: string;
  children: TreeNode[];
}

// Pipeline view (POST /api/analyze): what the three phases built for one program.
export interface PipelineView {
  tokens: { kind: string; text: string; line: number; col: number }[];
  tree: string; // the parse tree as indented text
  treeNodes?: TreeNode; // the same tree, nested, for the SVG diagram (absent on older responses)
  symbols: { name: string; type: string; kind: string; line: number }[];
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

// F8 whole-program: the "Correct" button rewrites the entire file and re-compiles it.
// `verified` is true only when the rewrite has no fatal error; a partial rewrite that merely
// reduces the errors is still returned (verified false, remaining_fatal > 0).
export interface Correction {
  corrected_source: string;
  diff: string;
  changes: string[]; // one short sentence per fix (the explanation of what was corrected)
  verified: boolean;
  before_summary: string;
  after_summary: string;
  remaining_fatal: number;
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

// Compile analytics (GET /api/profile/{id}/analytics).
export interface DailyPoint {
  date: string; // YYYY-MM-DD (UTC)
  compiles: number;
  successful: number;
  errors: number;
}

export interface Analytics {
  days: number;
  daily: DailyPoint[];
  totals: { compiles: number; successful: number; success_rate: number; errors: number; avg_errors: number };
  streak: number;
  corrections?: number; // times the "Correct whole program" button was used (F8 whole-file)
  phases: { phase: string; count: number }[];
  top_codes: { code: string; count: number }[];
  top_categories: { category: string; count: number }[];
  trend: { first_half: number | null; second_half: number | null; direction: "up" | "down" | "flat" };
  recent: CompileEntry[];
  today?: DaySummary;
  yesterday?: DaySummary;
}

export interface CompileEntry {
  ts: string;
  ok: boolean;
  fatal: number;
  warnings: number;
}

export interface DaySummary {
  date: string;
  compiles: number;
  successful: number;
  errors: number;
  warnings: number;
  top_code: { code: string; count: number } | null;
  compiles_list: CompileEntry[];
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
