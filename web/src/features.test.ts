import { describe, expect, it } from "vitest";
import { DRILLS, orderDrills } from "./drills";
import { imbalance } from "./components/PredictiveHint";
import { revealAt, splitSpan } from "./components/PipelinePage";
import { layout } from "./components/AstTree";
import type { TreeNode } from "./types";

describe("orderDrills", () => {
  it("puts the student's most-missed categories first", () => {
    const ordered = orderDrills(["type-mismatch", "missing-semicolon"]);
    expect(ordered[0].category).toBe("type-mismatch");
    expect(ordered[1].category).toBe("missing-semicolon");
    expect(ordered).toHaveLength(DRILLS.length); // no drill lost
  });

  it("keeps the default order when the profile is empty", () => {
    expect(orderDrills([]).map((d) => d.category)).toEqual(DRILLS.map((d) => d.category));
  });
});

describe("imbalance", () => {
  it("counts a missing closing brace", () => {
    expect(imbalance("int main(void) {\n  if (1) {\n}\n", "{", "}")).toBe(1);
  });
  it("is zero for balanced code", () => {
    expect(imbalance("int main(void) { return 0; }\n", "{", "}")).toBe(0);
    expect(imbalance("f(a, g(b));", "(", ")")).toBe(0);
  });
  it("ignores braces inside strings, chars and comments", () => {
    expect(imbalance('printf("{");  // }\n', "{", "}")).toBe(0);
    expect(imbalance("char c = '{';", "{", "}")).toBe(0);
  });
});

describe("revealAt", () => {
  it("reveals tokens, then parse-tree lines, then symbols", () => {
    expect(revealAt(0, 3, 2, 2)).toEqual({ tokens: 0, treeLines: 0, symbols: 0, done: false });
    expect(revealAt(2, 3, 2, 2)).toEqual({ tokens: 2, treeLines: 0, symbols: 0, done: false }); // lexing
    expect(revealAt(4, 3, 2, 2)).toEqual({ tokens: 3, treeLines: 1, symbols: 0, done: false }); // parsing
    expect(revealAt(6, 3, 2, 2)).toEqual({ tokens: 3, treeLines: 2, symbols: 1, done: false }); // semantic
    expect(revealAt(7, 3, 2, 2)).toEqual({ tokens: 3, treeLines: 2, symbols: 2, done: true }); // done
    expect(revealAt(99, 3, 2, 2)).toEqual({ tokens: 3, treeLines: 2, symbols: 2, done: true }); // clamped
  });
});

describe("splitSpan", () => {
  it("isolates a token's text by 1-based column and length", () => {
    expect(splitSpan("int x = 1;", 5, 1)).toEqual(["int ", "x", " = 1;"]);
    expect(splitSpan("int x = 1;", 1, 3)).toEqual(["", "int", " x = 1;"]);
  });
  it("clamps to the line bounds", () => {
    expect(splitSpan("ab", 2, 9)).toEqual(["a", "b", ""]);
  });
});

describe("layout", () => {
  const tree: TreeNode = {
    label: "Program",
    children: [
      { label: "A", children: [{ label: "A1", children: [] }, { label: "A2", children: [] }] },
      { label: "B", children: [] },
    ],
  };
  it("places every node and an edge per parent-child", () => {
    const { nodes, edges } = layout(tree, new Set());
    expect(nodes).toHaveLength(5); // Program, A, A1, A2, B
    expect(edges).toHaveLength(4);
  });
  it("hides a collapsed node's subtree", () => {
    const { nodes } = layout(tree, new Set([1])); // collapse "A" (pre-order id 1)
    expect(nodes.map((n) => n.label).sort()).toEqual(["A", "B", "Program"]); // A1/A2 gone
    expect(nodes.find((n) => n.label === "A")?.collapsed).toBe(true);
  });
});
