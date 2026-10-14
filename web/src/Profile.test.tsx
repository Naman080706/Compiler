import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import App, { routeFromHash } from "./App";
import { studentId } from "./api";
import { mockFetch, type Routes } from "./test/fetch-mock";

const PROFILE = { student_id: "x", threshold: 3, categories: [{ category: "missing-semicolon", hits: 3, depth: "full" }] };
const DAILY = Array.from({ length: 30 }, (_, i) => ({
  date: `2026-09-${String(i + 1).padStart(2, "0")}`,
  compiles: i === 29 ? 4 : 0,
  successful: i === 29 ? 1 : 0,
  errors: i === 29 ? 5 : 0,
}));
const DATA = {
  days: 30,
  daily: DAILY,
  totals: { compiles: 4, successful: 1, success_rate: 0.25, errors: 5, avg_errors: 1.25 },
  streak: 3,
  phases: [{ phase: "lexical", count: 0 }, { phase: "syntax", count: 4 }, { phase: "semantic", count: 1 }],
  top_codes: [{ code: "SYN-MISSING-SEMICOLON", count: 3 }],
  top_categories: [{ category: "missing-semicolon", count: 3 }],
  trend: { first_half: 2, second_half: 1, direction: "down" },
  recent: [{ ts: "2026-09-30T10:15:00+00:00", ok: false, fatal: 2, warnings: 0 }],
};

function routes(analytics: unknown): Routes {
  return {
    "GET /api/health": () => ({ json: { status: "ok", llm: "none" } }),
    [`GET /api/profile/${studentId()}`]: () => ({ json: PROFILE }),
    [`GET /api/profile/${studentId()}/analytics?days=30&tz=${-new Date().getTimezoneOffset()}`]: () => ({ json: analytics }),
  };
}

describe("hash routing", () => {
  it("maps hashes to routes", () => {
    expect(routeFromHash("")).toBe("editor");
    expect(routeFromHash("#/")).toBe("editor");
    expect(routeFromHash("#/profile")).toBe("profile");
    expect(routeFromHash("#/nonsense")).toBe("editor");
  });

  it("starts on the profile page for #/profile and navigates with the header button", async () => {
    window.location.hash = "#/profile";
    const fetchFn = mockFetch(routes(DATA));
    const user = userEvent.setup();
    render(<App />);
    expect(await screen.findByRole("heading", { name: "My profile" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Compile" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Back to editor" }));
    expect(window.location.hash).toBe("#/");
    expect(await screen.findByRole("button", { name: "Compile" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "My profile" })).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Profile" }));
    expect(window.location.hash).toBe("#/profile");
    expect(fetchFn).toHaveBeenCalled();
  });
});

describe("analytics dashboard", () => {
  it("renders tiles, charts, top mistakes and recent activity", async () => {
    window.location.hash = "#/profile";
    mockFetch(routes(DATA));
    render(<App />);
    await screen.findByText("25%");
    expect(screen.getByText("3 days")).toBeInTheDocument();
    expect(screen.getByText(/1\.3 ↓|1\.2 ↓/)).toBeInTheDocument();
    const daily = screen.getByRole("img", { name: /Compiles per day/ });
    expect(daily.querySelectorAll("rect.bar-ok")).toHaveLength(30);
    expect(screen.getByRole("img", { name: "Errors by phase" })).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Top mistakes" })).getByText("SYN-MISSING-SEMICOLON")).toBeInTheDocument();
    expect(within(screen.getByRole("list", { name: "Recent compiles" })).getByText("Failed")).toBeInTheDocument();
  });

  it("shows the empty state when nothing was compiled", async () => {
    window.location.hash = "#/profile";
    mockFetch(routes({ ...DATA, daily: DAILY.map((d) => ({ ...d, compiles: 0, successful: 0, errors: 0 })), totals: { compiles: 0, successful: 0, success_rate: 0, errors: 0, avg_errors: 0 }, streak: 0, recent: [], top_codes: [], top_categories: [] }));
    render(<App />);
    expect(await screen.findByText(/No compiles yet/)).toBeInTheDocument();
    expect(screen.queryByRole("img", { name: /Compiles per day/ })).not.toBeInTheDocument();
  });
});
