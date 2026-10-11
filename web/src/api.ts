// Typed calls to the backend. Every request goes to /api/*, which the Vite dev
// proxy forwards to FastAPI (plan 012). Only the source text and record ids are
// sent: never a filename or any student identity (PRD privacy note).
import type { Answer, ChatTurn, CompileResponse, Explanation, ExplainMode, FixSuggestion, Health, Verbosity } from "./types";

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

async function request<T>(path: string, body?: object): Promise<T> {
  const init: RequestInit = body === undefined
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

export const compile = (source: string) => request<CompileResponse>("/api/compile", { source });

export const explain = (source: string, recordId: string, mode: ExplainMode, verbosity: Verbosity = "beginner") =>
  request<Explanation>("/api/explain", { source, record_id: recordId, mode, verbosity });

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
