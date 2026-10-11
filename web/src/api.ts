// Typed calls to the backend. Every request goes to /api/*, which the Vite dev
// proxy forwards to FastAPI (plan 012). Only the source text and record ids are
// sent: never a filename or a real identity (PRD privacy note). F9 adds one
// pseudonymous student id: a random token made here, kept in localStorage, sent
// only to /api/compile, /api/explain and /api/profile (the server never passes it to the LLM).
import type {
  Answer,
  ChatTurn,
  CompileResponse,
  Explanation,
  ExplainMode,
  FixSuggestion,
  Health,
  ProfileView,
  Verbosity,
} from "./types";

const STUDENT_KEY = "cea.student_id";
const SESSION_KEY = "cea.session_id";
const memory: Record<string, string> = {}; // fallback when storage is blocked: lasts for this page load

function randomToken(prefix: string): string {
  const bytes = new Uint8Array(12);
  crypto.getRandomValues(bytes);
  return prefix + Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
}

function stored(store: "local" | "session", key: string, prefix: string): string {
  try {
    const area = store === "local" ? window.localStorage : window.sessionStorage;
    let value = area.getItem(key);
    if (!value) {
      value = randomToken(prefix);
      area.setItem(key, value);
    }
    return value;
  } catch {
    return (memory[key] ??= randomToken(prefix));
  }
}

/** The pseudonymous student id: random, created in this browser, kept in localStorage (F9). */
export const studentId = () => stored("local", STUDENT_KEY, "stu_");
/** One id per browser session; the server counts a given error at most once per session (F9). */
export const sessionId = () => stored("session", SESSION_KEY, "ses_");

// The server uses only the last few turns; the client sends no more than this many (F6 history cap).
export const MAX_HISTORY = 6;

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, body?: object, method?: "DELETE"): Promise<T> {
  const init: RequestInit = method === "DELETE"
    ? { method: "DELETE" }
    : body === undefined
      ? { method: "GET" }
      : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const resp = await fetch(path, init);
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`.trim();
    try {
      const data = await resp.json();
      if (typeof data?.detail === "string") detail = data.detail;
    } catch {
      // not JSON: keep the status line
    }
    throw new ApiError(resp.status, detail);
  }
  return (await resp.json()) as T;
}

export const compile = (source: string) =>
  request<CompileResponse>("/api/compile", { source, student_id: studentId(), session_id: sessionId() });

// verbosity undefined = automatic: the F9 profile picks the depth. An explicit value is the F5 toggle and always wins.
export const explain = (source: string, recordId: string, mode: ExplainMode, verbosity?: Verbosity) =>
  request<Explanation>("/api/explain", {
    source,
    record_id: recordId,
    mode,
    ...(verbosity ? { verbosity } : {}),
    student_id: studentId(),
  });

export const getProfile = () => request<ProfileView>(`/api/profile/${studentId()}`);

export const resetProfile = () => request<ProfileView>(`/api/profile/${studentId()}`, undefined, "DELETE");

export const suggestFix = (source: string, recordId: string) =>
  request<FixSuggestion>("/api/fix", { source, record_id: recordId });

export const ask = (source: string, recordId: string, question: string, history: ChatTurn[] = []) =>
  request<Answer>("/api/ask", {
    source,
    record_id: recordId,
    question,
    history: history
      .filter((t) => !t.refused)
      .slice(-MAX_HISTORY)
      .map((t) => ({ question: t.question, answer: t.answer })),
  });

export const health = () => request<Health>("/api/health");
