import { describe, expect, it, vi } from "vitest";
import { ApiError, ask, compile, explain, health, suggestFix } from "./api";
import { bodiesFor, mockFetch } from "./test/fetch-mock";

const SRC = "int main(void) {\n    return 0;\n}\n";

describe("api", () => {
  it("posts only the source to /api/compile", async () => {
    const fetchFn = mockFetch({ "POST /api/compile": () => ({ json: { ok: true, summary: "0 fatal, 0 warnings", records: [], clusters: [] } }) });
    const resp = await compile(SRC);
    expect(resp.summary).toBe("0 fatal, 0 warnings");
    expect(bodiesFor(fetchFn, "/api/compile")).toEqual([{ source: SRC }]);
    expect(fetchFn.mock.calls[0][1]?.headers).toEqual({ "Content-Type": "application/json" });
  });

  it("sends exactly the contract fields to explain, fix and ask", async () => {
    const fetchFn = mockFetch({
      "POST /api/explain": () => ({ json: { text: "t", rule_ref: "r", cited_rule: null, mode: "expand" } }),
      "POST /api/fix": () => ({ json: { diff: "", patched_source: SRC, verified: false } }),
      "POST /api/ask": () => ({ json: { text: "a", refused: false } }),
    });
    await explain(SRC, "E-0001", "expand");
    await suggestFix(SRC, "E-0001");
    await ask(SRC, "E-0001", "why?");
    expect(bodiesFor(fetchFn, "/api/explain")).toEqual([{ source: SRC, record_id: "E-0001", mode: "expand" }]);
    expect(bodiesFor(fetchFn, "/api/fix")).toEqual([{ source: SRC, record_id: "E-0001" }]);
    expect(bodiesFor(fetchFn, "/api/ask")).toEqual([{ source: SRC, record_id: "E-0001", question: "why?" }]);
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
