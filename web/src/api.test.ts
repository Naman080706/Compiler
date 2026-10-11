import { describe, expect, it, vi } from "vitest";
import { ApiError, ask, compile, explain, getProfile, health, resetProfile, sessionId, studentId, suggestFix } from "./api";
import { bodiesFor, mockFetch } from "./test/fetch-mock";

const SRC = "int main(void) {\n    return 0;\n}\n";

describe("api", () => {
  it("posts the source and the pseudonymous ids to /api/compile", async () => {
    const fetchFn = mockFetch({ "POST /api/compile": () => ({ json: { ok: true, summary: "0 fatal, 0 warnings", records: [], clusters: [] } }) });
    const resp = await compile(SRC);
    expect(resp.summary).toBe("0 fatal, 0 warnings");
    expect(bodiesFor(fetchFn, "/api/compile")).toEqual([{ source: SRC, student_id: studentId(), session_id: sessionId() }]);
    expect(fetchFn.mock.calls[0][1]?.headers).toEqual({ "Content-Type": "application/json" });
  });

  it("sends exactly the contract fields to explain, fix and ask", async () => {
    const fetchFn = mockFetch({
      "POST /api/explain": () => ({ json: { text: "t", rule_ref: "r", cited_rule: null, mode: "expand", verbosity: "expert", citations: [] } }),
      "POST /api/fix": () => ({ json: { diff: "", patched_source: SRC, verified: false, attempts: 3, reason: "x" } }),
      "POST /api/ask": () => ({ json: { text: "a", refused: false } }),
    });
    await explain(SRC, "E-0001", "expand", "expert");
    await suggestFix(SRC, "E-0001");
    await ask(SRC, "E-0001", "why?");
    expect(bodiesFor(fetchFn, "/api/explain")).toEqual([
      { source: SRC, record_id: "E-0001", mode: "expand", verbosity: "expert", student_id: studentId() },
    ]);
    expect(bodiesFor(fetchFn, "/api/fix")).toEqual([{ source: SRC, record_id: "E-0001" }]);
    expect(bodiesFor(fetchFn, "/api/ask")).toEqual([{ source: SRC, record_id: "E-0001", question: "why?", history: [] }]);
  });

  it("omits verbosity when the choice is automatic", async () => {
    const fetchFn = mockFetch({
      "POST /api/explain": () => ({ json: { text: "t", rule_ref: "r", cited_rule: null, mode: "short", verbosity: "beginner", citations: [] } }),
    });
    await explain(SRC, "E-0001", "short");
    expect(bodiesFor(fetchFn, "/api/explain")).toEqual([{ source: SRC, record_id: "E-0001", mode: "short", student_id: studentId() }]);
  });

  it("reads and resets the profile with GET and DELETE", async () => {
    const view = { student_id: studentId(), threshold: 3, categories: [] };
    const fetchFn = mockFetch({
      [`GET /api/profile/${studentId()}`]: () => ({ json: view }),
      [`DELETE /api/profile/${studentId()}`]: () => ({ json: view }),
    });
    expect(await getProfile()).toEqual(view);
    expect(await resetProfile()).toEqual(view);
    expect(fetchFn.mock.calls.map(([, init]) => init?.method)).toEqual(["GET", "DELETE"]);
  });

  it("reads /api/health with GET", async () => {
    const fetchFn = mockFetch({ "GET /api/health": () => ({ json: { status: "ok", llm: "fallback" } }) });
    expect(await health()).toEqual({ status: "ok", llm: "fallback" });
    expect(fetchFn.mock.calls[0][1]).toEqual({ method: "GET" });
  });

  it("throws ApiError with the server's detail", async () => {
    mockFetch({ "POST /api/compile": () => ({ status: 413, json: { detail: "Source is larger than 65536 bytes." } }) });
    const err = await compile("x").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 413, message: "Source is larger than 65536 bytes." });
  });

  it("falls back to the status line when the error body is not JSON", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>bad gateway</html>", { status: 502, statusText: "Bad Gateway" })));
    await expect(compile("x")).rejects.toMatchObject({ status: 502, message: "502 Bad Gateway" });
  });
});
