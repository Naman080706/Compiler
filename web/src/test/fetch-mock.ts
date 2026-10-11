// Replaces global fetch with a router keyed by "METHOD /path". Each handler gets
// the parsed JSON body and returns { status?, json }. Unknown routes give 500.
import { vi } from "vitest";

export interface Reply {
  status?: number;
  json: unknown;
}
export type Routes = Record<string, (body: Record<string, unknown>) => Reply>;

export function mockFetch(routes: Routes) {
  const fn = vi.fn(async (url: string, init?: RequestInit) => {
    const handler = routes[`${init?.method ?? "GET"} ${url}`];
    const body = init?.body ? (JSON.parse(String(init.body)) as Record<string, unknown>) : {};
    const { status = 200, json } = handler ? handler(body) : { status: 500, json: { detail: "no route" } };
    return new Response(JSON.stringify(json), { status, headers: { "Content-Type": "application/json" } });
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

/** The parsed JSON bodies of every call to `path`, in call order. */
export function bodiesFor(fn: ReturnType<typeof mockFetch>, path: string): Record<string, unknown>[] {
  return fn.mock.calls
    .filter(([url]) => url === path)
    .map(([, init]) => JSON.parse(String(init?.body)) as Record<string, unknown>);
}
