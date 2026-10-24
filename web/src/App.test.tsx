import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import App from "./App";
import { sessionId, studentId } from "./api";
import { SAMPLE_SOURCE } from "./sample";
import { bodiesFor, mockFetch, type Routes } from "./test/fetch-mock";
import { SAMPLE_COMPILE } from "./test/fixtures";
import { monacoMock } from "./test/monaco-mock";

const PROFILE = {"student_id": "x", "threshold": 3, "categories": [{"category": "missing-semicolon", "hits": 3, "depth": "full"}, {"category": "undeclared-identifier", "hits": 1, "depth": "terse"}]};
const EMPTY_ANALYTICS = {
  days: 30,
  daily: Array.from({ length: 30 }, (_, i) => ({ date: `2026-09-${String(i + 1).padStart(2, "0")}`, compiles: 0, successful: 0, errors: 0 })),
  totals: { compiles: 0, successful: 0, success_rate: 0, errors: 0, avg_errors: 0 },
  streak: 0, phases: [], top_codes: [], top_categories: [],
  trend: { first_half: null, second_half: null, direction: "flat" }, recent: [],
};
const PATCHED = SAMPLE_SOURCE.replace("total)\n", "total);\n");

function routes(extra: Routes = {}): Routes {
  return {
    "GET /api/health": () => ({ json: { status: "ok", llm: "none" } }),
    "POST /api/compile": () => ({ json: SAMPLE_COMPILE }),
    "POST /api/explain": (b) => ({ json: { text: `${b.verbosity ?? "auto"} ${b.mode} text for ${b.record_id}`, rule_ref: "sem.declare_before_use", cited_rule: null, mode: b.mode, verbosity: b.verbosity ?? "beginner", citations: ["rule:sem.declare_before_use", "fix:SEM-UNDECLARED-VAR"] } }),
    "POST /api/fix": () => ({ json: { diff: "--- a\n+++ b\n", patched_source: PATCHED, verified: true, attempts: 1, reason: "verified" } }),
    [`GET /api/profile/${studentId()}`]: () => ({ json: PROFILE }),
    [`GET /api/profile/${studentId()}/analytics?days=30&tz=${-new Date().getTimezoneOffset()}`]: () => ({ json: EMPTY_ANALYTICS }),
    [`DELETE /api/profile/${studentId()}`]: () => ({ json: { student_id: studentId(), threshold: 3, categories: [] } }),
    "POST /api/ask": () => ({ json: { text: "I only answer questions about your compiler errors.", refused: true } }),
    "POST /api/analyze": () => ({ json: {
      tokens: [{ kind: "KEYWORD", text: "int", line: 1, col: 1 }],
      tree: "Program\n  FunctionDecl(name='main', ret_type='int')",
      treeNodes: { label: "Program", children: [{ label: "FunctionDecl(name='main', ret_type='int')", children: [] }] },
      symbols: [{ name: "main", type: "int", kind: "function", line: 1 }],
    } }),
    "POST /api/fold": () => ({ json: { folds: [{ line: 1, text: "2 * 3", value: "6" }] } }),
    "POST /api/format": () => ({ json: { ok: true, formatted: "int main(void) {\n    return 0;\n}\n", reason: "" } }),
    "POST /api/astdiff": () => ({ json: { rows: [{ tag: "same", text: "Program" }], changed: false } }),
    ...extra,
  };
}

async function compileSample(extra: Routes = {}) {
  const fetchFn = mockFetch(routes(extra));
  const user = userEvent.setup();
  render(<App />);
  await user.click(screen.getByRole("button", { name: "Compile" }));
  await screen.findByTestId("summary");
  return { fetchFn, user };
}

function card(code: string, line: number) {
  return screen.getByRole("listitem", { name: `${code} at line ${line}` });
}

describe("App", () => {
  it("starts with the sample program and a hint", async () => {
    mockFetch(routes());
    render(<App />);
    expect(screen.getByTestId("editor")).toHaveValue(SAMPLE_SOURCE);
    expect(screen.getByText("Press Compile to check your program.")).toBeInTheDocument();
    expect(await screen.findByText("AI: none")).toBeInTheDocument();
  });

  it("shows the backend as offline when /api/health fails", async () => {
    mockFetch(routes({ "GET /api/health": () => ({ status: 500, json: {} }) }));
    render(<App />);
    expect(await screen.findByText("AI: offline")).toBeInTheDocument();
  });

  it("compiles the editor text and shows the F4 summary line", async () => {
    const { fetchFn } = await compileSample();
    expect(screen.getByTestId("summary")).toHaveTextContent("6 fatal, 1 warning");
    expect(screen.getByText("Does not compile")).toBeInTheDocument();
    expect(screen.getByText("3 root causes shown for 7 errors")).toBeInTheDocument();
    expect(bodiesFor(fetchFn, "/api/compile")).toEqual([
      { source: SAMPLE_SOURCE, student_id: studentId(), session_id: sessionId() },
    ]);
  });

  it("shows one card per root cause, grouped by phase", async () => {
    await compileSample();
    const cards = screen.getAllByRole("listitem").filter((c) => /at line \d+$/.test(c.getAttribute("aria-label") ?? ""));
    expect(cards.map((c) => c.getAttribute("aria-label"))).toEqual([
      "SYN-MISSING-SEMICOLON at line 9",
      "WRN-UNUSED-VAR at line 5",
      "SEM-UNDECLARED-VAR at line 6",
    ]);
  });

  it("has phase headings with counts, no empty groups, and a phase summary", async () => {
    await compileSample();
    expect(screen.getByRole("heading", { name: "Syntax errors — 1 root cause" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Semantic errors — 2 root causes" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Lexical/ })).toBeNull();
    expect(screen.getByTestId("phase-summary")).toHaveTextContent("Syntax 1 · Semantic 6");
  });

  it("shows a phase badge on each card and a gcc tag only for engine gcc", async () => {
    const records = SAMPLE_COMPILE.records.map((r) => (r.id === "E-0001" ? { ...r, engine: "gcc" as const } : r));
    await compileSample({ "POST /api/compile": () => ({ json: { ...SAMPLE_COMPILE, records } }) });
    const syn = screen.getByRole("listitem", { name: "SYN-MISSING-SEMICOLON at line 9" });
    expect(within(syn).getByText("syntax", { selector: ".badge.phase" })).toBeInTheDocument();
    expect(within(syn).getByText("via gcc")).toBeInTheDocument();
    const sem = screen.getByRole("listitem", { name: "SEM-UNDECLARED-VAR at line 6" });
    expect(within(sem).getByText("semantic", { selector: ".badge.phase" })).toBeInTheDocument();
    expect(within(sem).queryByText("via gcc")).toBeNull();
  });

  it("labels each root fatal or warning", async () => {
    await compileSample();
    expect(within(card("WRN-UNUSED-VAR", 5)).getByText("warning")).toHaveClass("badge", "warning");
    expect(within(card("SEM-UNDECLARED-VAR", 6)).getByText("fatal")).toHaveClass("badge", "fatal");
    expect(within(card("SYN-MISSING-SEMICOLON", 9)).getByText("fatal")).toHaveClass("badge", "fatal");
  });

  it("collapses symptoms behind +N related and expands them on click", async () => {
    const { user } = await compileSample();
    const root = card("SEM-UNDECLARED-VAR", 6);
    const toggle = within(root).getByRole("button", { name: "+4 related" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("list", { name: "Errors related to E-0002" })).toBeNull();
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const symptoms = within(screen.getByRole("list", { name: "Errors related to E-0002" })).getAllByRole("listitem");
    expect(symptoms).toHaveLength(4);
    expect(symptoms[0]).toHaveTextContent("SEM-UNDECLARED-VAR line 6, col 17");
    expect(within(card("SYN-MISSING-SEMICOLON", 9)).queryByRole("button", { name: /related/ })).toBeNull();
  });

  it("sets inline markers for every record", async () => {
    await compileSample();
    await waitFor(() => expect(monacoMock.setModelMarkers).toHaveBeenLastCalledWith(monacoMock.model, "cea", expect.any(Array)));
    const markers = monacoMock.setModelMarkers.mock.lastCall?.[2] as { code: string; severity: number }[];
    expect(markers).toHaveLength(7);
    expect(markers.filter((m) => m.severity === 8).map((m) => m.code)).toEqual(["SYN-MISSING-SEMICOLON", "SEM-UNDECLARED-VAR"]);
  });

  it("Explain asks for the short explanation and Expand for the full one", async () => {
    const { fetchFn, user } = await compileSample();
    const root = card("SEM-UNDECLARED-VAR", 6);
    await user.click(within(root).getByRole("button", { name: "Explain" }));
    expect(await within(root).findByText("auto short text for E-0002")).toBeInTheDocument();
    await user.click(within(root).getByRole("button", { name: "Expand" }));
    expect(await within(root).findByText("auto expand text for E-0002")).toBeInTheDocument();
    expect(within(root).getByText("sem.declare_before_use")).toBeInTheDocument();
    expect(bodiesFor(fetchFn, "/api/explain")).toEqual([
      { source: SAMPLE_SOURCE, record_id: "E-0002", mode: "short", student_id: studentId() },
      { source: SAMPLE_SOURCE, record_id: "E-0002", mode: "expand", student_id: studentId() },
    ]);
  });

  it("Suggest fix shows the diff with a Verified badge", async () => {
    const { fetchFn, user } = await compileSample();
    const root = card("SYN-MISSING-SEMICOLON", 9);
    await user.click(within(root).getByRole("button", { name: "Suggest fix" }));
    const fix = await within(root).findByRole("region", { name: "Verified fix" });
    expect(within(fix).getByText("Verified")).toHaveClass("badge", "verified");
    expect(within(fix).queryByText(/Unverified/)).toBeNull();
    const diff = within(fix).getByTestId("diff-editor");
    expect(diff).toHaveAttribute("data-original", SAMPLE_SOURCE);
    expect(diff.textContent).toBe(PATCHED);
    expect(bodiesFor(fetchFn, "/api/fix")).toEqual([{ source: SAMPLE_SOURCE, record_id: "E-0001" }]);
  });

  it("shows no diff, only a note, when there is no verified fix", async () => {
    const { user } = await compileSample({
      "POST /api/fix": () => ({ json: { diff: "", patched_source: SAMPLE_SOURCE, verified: false, attempts: 3, reason: "the original error is still there" } }),
    });
    const root = card("SYN-MISSING-SEMICOLON", 9);
    await user.click(within(root).getByRole("button", { name: "Suggest fix" }));
    expect(await within(root).findByText("No verified fix found; see explanation")).toBeInTheDocument();
    expect(within(root).queryByTestId("diff-editor")).toBeNull();
    expect(within(root).queryByText("Verified")).toBeNull();
  });

  it("never displays an unverified diff even if the server sent one", async () => {
    const { user } = await compileSample({
      "POST /api/fix": () => ({ json: { diff: "--- a\n+++ b\n", patched_source: PATCHED, verified: false, attempts: 3, reason: "x" } }),
    });
    const root = card("SYN-MISSING-SEMICOLON", 9);
    await user.click(within(root).getByRole("button", { name: "Suggest fix" }));
    expect(await within(root).findByText("No verified fix found; see explanation")).toBeInTheDocument();
    expect(within(root).queryByTestId("diff-editor")).toBeNull();
  });

  it("Ask shows a refused answer as out of scope", async () => {
    const { fetchFn, user } = await compileSample();
    const root = card("SEM-UNDECLARED-VAR", 6);
    const askButton = within(root).getByRole("button", { name: "Ask" });
    expect(askButton).toBeDisabled();
    await user.type(within(root).getByRole("textbox", { name: "Question about E-0002" }), "  What is the capital of France?  ");
    await user.click(askButton);
    expect(await within(root).findByText("Out of scope:")).toBeInTheDocument();
    expect(bodiesFor(fetchFn, "/api/ask")).toEqual([
      { source: SAMPLE_SOURCE, record_id: "E-0002", question: "What is the capital of France?", history: [] },
    ]);
  });

  it("shows a backend error from compile", async () => {
    mockFetch(routes({ "POST /api/compile": () => ({ status: 413, json: { detail: "Source is larger than 65536 bytes." } }) }));
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Compile" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Source is larger than 65536 bytes.");
  });

  it("shows an assistant error inside the card", async () => {
    const { user } = await compileSample({
      "POST /api/explain": () => ({ status: 503, json: { detail: "The AI assistant is not configured. See .env.example." } }),
    });
    const root = card("SEM-UNDECLARED-VAR", 6);
    await user.click(within(root).getByRole("button", { name: "Explain" }));
    expect(await within(root).findByRole("alert")).toHaveTextContent("The AI assistant is not configured.");
  });

  it("reports a clean program", async () => {
    await compileSample({
      "POST /api/compile": () => ({ json: { ok: true, summary: "0 fatal, 0 warnings", records: [], clusters: [] } }),
    });
    expect(screen.getByText("Compiles")).toBeInTheDocument();
    expect(screen.getByText("No errors. The program compiles.")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /errors \(/ })).toBeNull();
  });

  it("after an edit, warns that results are stale and still sends the compiled source", async () => {
    const { fetchFn, user } = await compileSample();
    await user.type(screen.getByTestId("editor"), "// edited");
    expect(screen.getByText("The code changed since the last compile. Compile again to update.")).toBeInTheDocument();
    await user.click(within(card("SEM-UNDECLARED-VAR", 6)).getByRole("button", { name: "Explain" }));
    await screen.findByText("auto short text for E-0002");
    expect(bodiesFor(fetchFn, "/api/explain")[0].source).toBe(SAMPLE_SOURCE);
  });

  // ---- milestone 3: F5 verbosity, F6 per-error threads, F7 cited rule
  it("shows the retrieved chunks an explanation is grounded in", async () => {
    const { user } = await compileSample();
    const root = card("SEM-UNDECLARED-VAR", 6);
    await user.click(within(root).getByRole("button", { name: "Explain" }));
    const cited = await within(root).findByLabelText("Cited sources");
    expect(cited).toHaveTextContent("Grounded in: rule:sem.declare_before_use, fix:SEM-UNDECLARED-VAR");
  });

  it("the verbosity toggle re-renders an existing explanation in the same mode", async () => {
    const { fetchFn, user } = await compileSample();
    const root = card("SEM-UNDECLARED-VAR", 6);
    expect(screen.getByRole("button", { name: "Auto" })).toHaveAttribute("aria-pressed", "true");
    await user.click(within(root).getByRole("button", { name: "Expand" }));
    await within(root).findByText("auto expand text for E-0002");
    await user.click(screen.getByRole("button", { name: "Expert" }));
    expect(await within(root).findByText("expert expand text for E-0002")).toBeInTheDocument();
    expect(within(root).queryByText("auto expand text for E-0002")).toBeNull();
    expect(bodiesFor(fetchFn, "/api/explain").map((b) => [b.mode, b.verbosity])).toEqual([
      ["expand", undefined],
      ["expand", "expert"],
    ]);
    // a card with no explanation yet makes no request on toggle; its next Explain uses the new style
    const other = card("SYN-MISSING-SEMICOLON", 9);
    await user.click(within(other).getByRole("button", { name: "Explain" }));
    expect(await within(other).findByText("expert short text for E-0001")).toBeInTheDocument();
  });

  it("the verbosity choice persists for the session", async () => {
    const first = await compileSample();
    await first.user.click(screen.getByRole("button", { name: "Expert" }));
    cleanupRender();
    mockFetch(routes());
    render(<App />);
    expect(screen.getByRole("button", { name: "Expert" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Auto" })).toHaveAttribute("aria-pressed", "false");
  });

  it("each error card has its own chat thread and sends only its own history", async () => {
    const answers: Record<string, string> = { "q one": "a one", "q two": "a two", "q other": "a other" };
    const { fetchFn, user } = await compileSample({
      "POST /api/ask": (b) => ({ json: { text: answers[b.question as string], refused: false } }),
    });
    const a = card("SEM-UNDECLARED-VAR", 6);
    const b = card("SYN-MISSING-SEMICOLON", 9);
    for (const q of ["q one", "q two"]) {
      await user.type(within(a).getByRole("textbox", { name: "Question about E-0002" }), q);
      await user.click(within(a).getByRole("button", { name: "Ask" }));
      await within(a).findByText(answers[q]);
    }
    await user.type(within(b).getByRole("textbox", { name: /Question about/ }), "q other");
    await user.click(within(b).getByRole("button", { name: "Ask" }));
    await within(b).findByText("a other");
    const thread = within(a).getByRole("list", { name: "Conversation about E-0002" });
    expect(within(thread).getAllByRole("listitem")).toHaveLength(2);
    expect(within(b).getByRole("list", { name: /Conversation about/ })).not.toBe(thread);
    expect(within(b).queryByText("a one")).toBeNull();
    const bodies = bodiesFor(fetchFn, "/api/ask");
    expect(bodies[0].history).toEqual([]);
    expect(bodies[1].history).toEqual([{ question: "q one", answer: "a one" }]);
    expect(bodies[2].history).toEqual([]);
  });

  it("caps the history it sends and leaves refused turns out of it", async () => {
    let n = 0;
    const { fetchFn, user } = await compileSample({
      "POST /api/ask": () => {
        n += 1;
        return { json: { text: `answer ${n}`, refused: n === 2 } };
      },
    });
    const root = card("SEM-UNDECLARED-VAR", 6);
    for (let i = 1; i <= 10; i++) {
      await user.type(within(root).getByRole("textbox", { name: "Question about E-0002" }), `question ${i}`);
      await user.click(within(root).getByRole("button", { name: "Ask" }));
      await within(root).findByText(`answer ${i}`);
    }
    const last = bodiesFor(fetchFn, "/api/ask")[9].history as { question: string }[];
    expect(last).toHaveLength(6);
    expect(last[0].question).toBe("question 4");
    expect(last.map((t) => t.question)).not.toContain("question 2");
  });
});

describe("multiple files", () => {
  it("opens a blank tab with New and keeps each file's own text", async () => {
    mockFetch(routes());
    const user = userEvent.setup();
    render(<App />);
    expect(screen.getByTestId("editor")).toHaveValue(SAMPLE_SOURCE);
    await user.click(screen.getByRole("button", { name: "+ New" }));
    expect(screen.getByTestId("editor")).toHaveValue("");
    await user.type(screen.getByTestId("editor"), "int x;");
    await user.click(screen.getByRole("tab", { name: /program\.c/ }));
    expect(screen.getByTestId("editor")).toHaveValue(SAMPLE_SOURCE);
    await user.click(screen.getByRole("tab", { name: /untitled-1\.c/ }));
    expect(screen.getByTestId("editor")).toHaveValue("int x;");
  });

  it("opens a .c file from the computer and makes it the active tab", async () => {
    mockFetch(routes());
    const user = userEvent.setup();
    const { container } = render(<App />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    await user.upload(input, new File(["int main(void){ return 0; }\n"], "factorial.c", { type: "text/plain" }));
    expect(await screen.findByRole("tab", { name: /factorial\.c/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByTestId("editor")).toHaveValue("int main(void){ return 0; }\n");
  });

  it("renames a tab by double-clicking its name", async () => {
    mockFetch(routes());
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "+ New" }));
    await user.dblClick(screen.getByText("untitled-1.c"));
    const box = screen.getByRole("textbox", { name: "Rename untitled-1.c" });
    await user.clear(box);
    await user.type(box, "factorial.c{Enter}");
    expect(screen.getByRole("tab", { name: /factorial\.c/ })).toBeInTheDocument();
    expect(screen.queryByText("untitled-1.c")).toBeNull();
  });

  it("keeps the old name when a rename is cancelled with Escape", async () => {
    mockFetch(routes());
    const user = userEvent.setup();
    render(<App />);
    await user.dblClick(screen.getByText("program.c"));
    const box = screen.getByRole("textbox", { name: "Rename program.c" });
    await user.clear(box);
    await user.type(box, "nope.c{Escape}");
    expect(screen.getByRole("tab", { name: /program\.c/ })).toBeInTheDocument();
    expect(screen.queryByText("nope.c")).toBeNull();
  });

  it("closing the active tab falls back to a neighbour", async () => {
    mockFetch(routes());
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "+ New" }));
    expect(screen.getByTestId("editor")).toHaveValue("");
    await user.click(screen.getByRole("button", { name: "Close untitled-1.c" }));
    expect(screen.getByTestId("editor")).toHaveValue(SAMPLE_SOURCE);
    expect(screen.queryByRole("tab", { name: /untitled-1\.c/ })).toBeNull();
  });

  it("compiles the active file only, and switching tabs swaps the result", async () => {
    const { user } = await compileSample();
    expect(screen.getByTestId("summary")).toHaveTextContent("6 fatal, 1 warning");
    await user.click(screen.getByRole("button", { name: "+ New" }));
    // the blank file has no result yet
    expect(screen.getByText("Press Compile to check your program.")).toBeInTheDocument();
    // going back to program.c restores its compiled result
    await user.click(screen.getByRole("tab", { name: /program\.c/ }));
    expect(screen.getByTestId("summary")).toHaveTextContent("6 fatal, 1 warning");
  });
});

describe("Pipeline and Practice pages", () => {
  it("Pipeline shows the tokens, parse tree and symbols for the current program", async () => {
    mockFetch(routes());
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Pipeline" }));
    expect(await screen.findByRole("heading", { name: /Lexer — tokens/ })).toBeInTheDocument();
    const symbols = screen.getByRole("table", { name: "Symbol table" });
    expect(within(symbols).getByText("main")).toBeInTheDocument();
    expect(screen.getByLabelText("Abstract syntax tree")).toHaveTextContent("FunctionDecl"); // SVG diagram (default)
    await user.click(screen.getByRole("button", { name: "Indented" }));
    expect(screen.getByLabelText("Parse tree")).toHaveTextContent("FunctionDecl"); // text view
  });

  it("Lab lists constant folds and formats the program", async () => {
    mockFetch(routes());
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Lab" }));
    expect(await screen.findByText("2 * 3")).toBeInTheDocument(); // fold table (loads on mount)
    await user.click(screen.getByRole("button", { name: "Format program" }));
    expect(await screen.findByLabelText("Formatted code")).toHaveTextContent("return 0");
  });

  it("Practice shows a drill and marks it solved when it compiles", async () => {
    mockFetch(routes({ "POST /api/compile": () => ({ json: { ok: true, summary: "0 fatal, 0 warnings", records: [], clusters: [] } }) }));
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "Practice" }));
    expect(await screen.findByRole("heading", { name: "Practice" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Check" }));
    expect(await screen.findByText(/Solved/)).toBeInTheDocument();
  });
});

describe("Run the program", () => {
  const RUN_OK = { gcc_available: true, compiled: true, compile_output: "", stdout: "sum = 15\n", stderr: "", exit_code: 0, timed_out: false, truncated: false };

  it("runs the program and shows its actual output in the OUTPUT panel", async () => {
    const fetchFn = mockFetch(routes({ "POST /api/run": () => ({ json: RUN_OK }) }));
    const user = userEvent.setup();
    render(<App />);
    await user.click(screen.getByRole("button", { name: "▶ Run" }));
    const term = await screen.findByLabelText("Compiler output");
    expect(await within(term).findByText("sum = 15")).toBeInTheDocument();
    expect(within(term).getByText("[program exited with code 0]")).toBeInTheDocument();
    expect(bodiesFor(fetchFn, "/api/run")).toEqual([{ source: SAMPLE_SOURCE }]); // no id sent
  });

  it("shows the build error when the program does not compile", async () => {
    const failed = { ...RUN_OK, compiled: false, stdout: "", compile_output: "input.c:9: error: expected ';'" };
    const user = userEvent.setup();
    mockFetch(routes({ "POST /api/run": () => ({ json: failed }) }));
    render(<App />);
    await user.click(screen.getByRole("button", { name: "▶ Run" }));
    const term = await screen.findByLabelText("Compiler output");
    expect(await within(term).findByText("the program did not compile, so it was not run:")).toBeInTheDocument();
    expect(within(term).getByText(/expected ';'/)).toBeInTheDocument();
  });
});

describe("Correct whole program (F8)", () => {
  const CORRECTED = SAMPLE_SOURCE.replace("total)\n", "total);\n");
  const verified = {
    corrected_source: CORRECTED,
    diff: "--- original\n+++ suggested\n",
    changes: ["Added the missing semicolon after the printf call on line 9."],
    verified: true,
    before_summary: "6 fatal, 1 warning",
    after_summary: "0 fatal, 1 warning",
    remaining_fatal: 0,
    attempts: 1,
    reason: "all errors fixed: the program now compiles",
  };
  const correctRoute = (body: object = verified): Routes => ({ "POST /api/correct": () => ({ json: body }) });

  it("corrects the whole program and applies the rewrite to the editor", async () => {
    const { fetchFn, user } = await compileSample(correctRoute());
    await user.click(screen.getByRole("button", { name: "Correct whole program" }));
    const dialog = await screen.findByRole("dialog", { name: "Correct whole program" });
    expect(within(dialog).getByText("Now compiles")).toBeInTheDocument();
    expect(within(dialog).getByText(/Added the missing semicolon/)).toBeInTheDocument();
    expect(within(dialog).getByText("6 fatal, 1 warning → 0 fatal, 1 warning")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Unified diff of the correction")).toBeInTheDocument();
    await user.click(within(dialog).getByRole("button", { name: "Apply to editor" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByTestId("editor")).toHaveValue(CORRECTED);
    expect(bodiesFor(fetchFn, "/api/correct")).toEqual([
      { source: SAMPLE_SOURCE, student_id: studentId(), session_id: sessionId() },
    ]);
  });

  it("shows a partial rewrite that still has errors, without claiming it compiles", async () => {
    const partial = { ...verified, verified: false, after_summary: "1 fatal, 0 warnings", remaining_fatal: 1,
      reason: "reduced the errors from 6 to 1" };
    const { user } = await compileSample(correctRoute(partial));
    await user.click(screen.getByRole("button", { name: "Correct whole program" }));
    const dialog = await screen.findByRole("dialog", { name: "Correct whole program" });
    expect(within(dialog).getByText("1 error remain")).toBeInTheDocument();
    expect(within(dialog).queryByText("Now compiles")).toBeNull();
    await user.click(within(dialog).getByRole("button", { name: "Close" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByTestId("editor")).toHaveValue(SAMPLE_SOURCE); // close does not apply
  });
});

describe("F9 profile view", () => {
  it("shows the stored category counts and resets them", async () => {
    let deleted = false;
    const { fetchFn, user } = await compileSample({
      [`GET /api/profile/${studentId()}`]: () => ({ json: deleted ? { ...PROFILE, categories: [] } : PROFILE }),
      [`DELETE /api/profile/${studentId()}`]: () => {
        deleted = true;
        return { json: { ...PROFILE, categories: [] } };
      },
    });
    await user.click(screen.getByRole("button", { name: "Profile" }));
    const table = await screen.findByRole("table", { name: "Error categories" });
    expect(within(table).getByText("missing-semicolon")).toBeInTheDocument();
    expect(within(table).getByText("Fuller, with a worked example")).toBeInTheDocument();
    expect(within(table).getByText("undeclared-identifier")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Reset my profile" }));
    expect(await screen.findByText("No errors recorded yet.")).toBeInTheDocument();
    const calls = fetchFn.mock.calls.map(([url, init]) => `${init?.method} ${url}`);
    expect(calls).toContain(`DELETE /api/profile/${studentId()}`);
  });

  it("the student id is a random token kept in localStorage and sent to compile, explain and profile only", async () => {
    window.localStorage.clear();
    const id = studentId();
    expect(id).toMatch(/^stu_[0-9a-f]{24}$/);
    expect(studentId()).toBe(id);
    expect(window.localStorage.getItem("cea.student_id")).toBe(id);
    const { fetchFn, user } = await compileSample();
    const root = card("SEM-UNDECLARED-VAR", 6);
    await user.click(within(root).getByRole("button", { name: "Explain" }));
    await user.click(within(root).getByRole("button", { name: "Suggest fix" }));
    await user.type(within(root).getByRole("textbox", { name: "Question about E-0002" }), "why?");
    await user.click(within(root).getByRole("button", { name: "Ask" }));
    await within(root).findByText(/only answer questions/);
    for (const [url, init] of fetchFn.mock.calls) {
      const carries = String(init?.body ?? "").includes(id) || String(url).includes(id);
      expect(carries).toBe(["/api/compile", "/api/explain"].includes(String(url)) || String(url).startsWith("/api/profile/"));
    }
  });

  it("shows how many times Correct was used in the dashboard", async () => {
    const analytics = {
      ...EMPTY_ANALYTICS, corrections: 3, streak: 1,
      totals: { compiles: 2, successful: 1, success_rate: 0.5, errors: 4, avg_errors: 2 },
    };
    const { user } = await compileSample({
      [`GET /api/profile/${studentId()}/analytics?days=30&tz=${-new Date().getTimezoneOffset()}`]: () => ({ json: analytics }),
    });
    await user.click(screen.getByRole("button", { name: "Profile" }));
    const label = await screen.findByText("Corrections used");
    expect(within(label.closest(".tile") as HTMLElement).getByText("3")).toBeInTheDocument();
  });

  it("shows a note when the profile earned a fuller explanation", async () => {
    const { user } = await compileSample({
      "POST /api/explain": () => ({
        json: { text: "long text", rule_ref: "r", cited_rule: null, mode: "short", verbosity: "beginner", citations: [],
                personalised: { category: "undeclared-identifier", hits: 4, depth: "full", override: false } },
      }),
    });
    const root = card("SEM-UNDECLARED-VAR", 6);
    await user.click(within(root).getByRole("button", { name: "Explain" }));
    expect(await within(root).findByTestId("depth-note")).toHaveTextContent("hit this kind of error (undeclared-identifier) 4 times");
  });
});

function cleanupRender() {
  document.body.innerHTML = "";
}
