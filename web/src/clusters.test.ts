import { describe, expect, it } from "vitest";
import { clusterViews, compilerOutput, groupByPhase, MarkerSeverity, phaseSummary, relatedLabel, runOutput, toMarkers } from "./clusters";
import { SAMPLE_COMPILE } from "./test/fixtures";

describe("clusterViews", () => {
  it("gives one view per cluster, in backend order, with symptoms", () => {
    const views = clusterViews(SAMPLE_COMPILE);
    expect(views.map((v) => [v.root.id, v.symptoms.map((s) => s.id)])).toEqual([
      ["E-0007", []],
      ["E-0002", ["E-0003", "E-0004", "E-0005", "E-0006"]],
      ["E-0001", []],
    ]);
  });

  it("skips ids that are not in the records", () => {
    const resp = { ...SAMPLE_COMPILE, clusters: [{ root_id: "E-0099", symptom_ids: [] }, { root_id: "E-0002", symptom_ids: ["E-0003", "E-0098"] }] };
    expect(clusterViews(resp).map((v) => [v.root.id, v.symptoms.length])).toEqual([["E-0002", 1]]);
  });

  it("is empty for a clean program", () => {
    expect(clusterViews({ ok: true, summary: "0 fatal, 0 warnings", records: [], clusters: [] })).toEqual([]);
  });
});

describe("relatedLabel", () => {
  it.each([
    [0, ""],
    [1, "+1 related"],
    [4, "+4 related"],
  ])("%i symptoms -> %j", (n, label) => {
    expect(relatedLabel(n)).toBe(label);
  });
});

describe("toMarkers", () => {
  const markers = toMarkers(SAMPLE_COMPILE.records);

  it("makes one marker per record", () => {
    expect(markers).toHaveLength(7);
  });

  it("marks fatal roots as errors, warning roots as warnings and symptoms as info", () => {
    expect(markers.map((m) => [m.code, m.severity])).toEqual([
      ["SYN-MISSING-SEMICOLON", MarkerSeverity.Error],
      ["SEM-UNDECLARED-VAR", MarkerSeverity.Error],
      ["SEM-UNDECLARED-VAR", MarkerSeverity.Info],
      ["SEM-UNDECLARED-VAR", MarkerSeverity.Info],
      ["SEM-UNDECLARED-VAR", MarkerSeverity.Info],
      ["SEM-UNDECLARED-VAR", MarkerSeverity.Info],
      ["WRN-UNUSED-VAR", MarkerSeverity.Warning],
    ]);
  });

  it("converts the inclusive span end to Monaco's exclusive end column", () => {
    expect(markers[6]).toMatchObject({ startLineNumber: 5, startColumn: 9, endLineNumber: 5, endColumn: 15, source: "cea" });
  });

  it("points symptoms at their root", () => {
    expect(markers[2].message).toBe("Variable 'i' is used before it is declared (related to E-0002)");
    expect(markers[1].message).toBe("Variable 'i' is used before it is declared");
  });
});

describe("compilerOutput", () => {
  const out = compilerOutput(SAMPLE_COMPILE);

  it("starts with the command and ends with the summary and exit status", () => {
    expect(out[0]).toEqual({ text: "$ cea compile program.c", kind: "cmd" });
    expect(out.at(-2)).toEqual({ text: SAMPLE_COMPILE.summary, kind: "fatal" });
    expect(out.at(-1)).toEqual({ text: "exit status 1", kind: "note" });
  });

  it("prints one line per root cause, coloured by severity, with the +N related count", () => {
    const bodies = out.slice(1, -2).filter((l) => l.text !== "");
    expect(bodies.map((l) => l.kind)).toEqual(["warning", "fatal", "fatal"]);
    expect(bodies[1].text).toContain("E-0002 program.c:6:10: fatal [SEM-UNDECLARED-VAR]");
    expect(bodies[1].text).toContain("(+4 related)");
  });

  it("reports a clean program and exit status 0", () => {
    const clean = compilerOutput({ ok: true, summary: "0 fatal, 0 warnings", records: [], clusters: [] });
    expect(clean[1]).toEqual({ text: "program.c: no errors found.", kind: "ok" });
    expect(clean.at(-1)).toEqual({ text: "exit status 0", kind: "note" });
  });
});

describe("runOutput", () => {
  const base = { gcc_available: true, compiled: true, compile_output: "", stdout: "", stderr: "", exit_code: 0, timed_out: false, truncated: false };

  it("shows the program's stdout and exit code", () => {
    const out = runOutput({ ...base, stdout: "sum = 15\n" }, "factorial.c");
    expect(out[0]).toEqual({ text: "$ ./factorial", kind: "cmd" });
    expect(out.some((l) => l.text === "sum = 15" && l.kind === "plain")).toBe(true);
    expect(out.at(-1)).toEqual({ text: "[program exited with code 0]", kind: "ok" });
  });

  it("marks a non-zero exit code as a warning", () => {
    expect(runOutput({ ...base, exit_code: 7 }).at(-1)).toEqual({ text: "[program exited with code 7]", kind: "warning" });
  });

  it("reports a build failure instead of output", () => {
    const out = runOutput({ ...base, compiled: false, compile_output: "input.c:2: error: 'x' undeclared" });
    expect(out[1]).toEqual({ text: "the program did not compile, so it was not run:", kind: "fatal" });
    expect(out.some((l) => l.text.includes("undeclared"))).toBe(true);
  });

  it("reports an infinite loop that was halted", () => {
    expect(runOutput({ ...base, timed_out: true, exit_code: null }).at(-1)).toEqual({
      text: "[program stopped: it ran too long (over 5s) and was halted]", kind: "fatal",
    });
  });

  it("says when gcc is missing", () => {
    const out = runOutput({ ...base, gcc_available: false });
    expect(out[1].text).toContain("gcc is not installed");
  });
});

describe("groupByPhase / phaseSummary", () => {
  it("orders groups lexical, syntax, semantic and omits empty ones", () => {
    const groups = groupByPhase(clusterViews(SAMPLE_COMPILE));
    expect(groups.map((g) => [g.phase, g.views.length])).toEqual([["syntax", 1], ["semantic", 2]]);
  });

  it("counts records per phase", () => {
    expect(phaseSummary(SAMPLE_COMPILE.records)).toBe("Syntax 1 · Semantic 6");
    expect(phaseSummary([])).toBe("");
  });
});
