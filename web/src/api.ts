// Typed calls to the backend. Every request goes to /api/*, which the Vite dev
// proxy forwards to FastAPI (plan 012). Only the source text and record ids are
// sent: never a filename or any student identity (PRD privacy note).
import type { Answer, CompileResponse, Explanation, ExplainMode, FixSuggestion, Health } from "./types";

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

export const explain = (source: string, recordId: string, mode: ExplainMode) =>
  request<Explanation>("/api/explain", { source, record_id: recordId, mode });

export const suggestFix = (source: string, recordId: string) =>
  request<FixSuggestion>("/api/fix", { source, record_id: recordId });

export const ask = (source: string, recordId: string, question: string) =>
  request<Answer>("/api/ask", { source, record_id: recordId, question });

export const health = () => request<Health>("/api/health");
