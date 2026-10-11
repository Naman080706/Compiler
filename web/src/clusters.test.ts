import { describe, expect, it } from "vitest";
import { clusterViews, groupByPhase, MarkerSeverity, phaseSummary, relatedLabel, toMarkers } from "./clusters";
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
