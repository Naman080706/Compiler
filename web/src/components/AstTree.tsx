// AST diagram (feature #2): the parse tree as a real node-link graph in SVG, with
// collapsible nodes. Possible only because /api/analyze hands us the nested tree we own.
// The layout is a simple tidy-tree: leaves take successive columns, a parent sits centred
// over its visible children. No layout library — it is a few lines over the tree we already have.
import { useState } from "react";
import type { TreeNode } from "../types";

const COL_W = 148; // horizontal spacing between leaves
const ROW_H = 62; // vertical spacing between depths
const PAD = 18;

export interface PlacedNode {
  id: number; // pre-order index over the FULL tree (matches the indented-text line / reveal count)
  label: string;
  x: number;
  y: number;
  hasChildren: boolean;
  collapsed: boolean;
}
export interface Edge {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
}
export interface Layout {
  nodes: PlacedNode[];
  edges: Edge[];
  width: number;
  height: number;
}

/** Position every visible node (a node under a collapsed ancestor is omitted). Pure. */
export function layout(root: TreeNode, collapsed: ReadonlySet<number>): Layout {
  const nodes: PlacedNode[] = [];
  const edges: Edge[] = [];
  let nextCol = 0;
  let maxDepth = 0;
  let id = -1; // incremented on entry so ids follow full-tree pre-order

  function place(node: TreeNode, depth: number): PlacedNode {
    const myId = ++id;
    maxDepth = Math.max(maxDepth, depth);
    const isCollapsed = collapsed.has(myId);
    const kids = isCollapsed ? [] : node.children;
    const placed = kids.map((c) => place(c, depth + 1));
    // Children already consumed their ids (and columns); position this node over them.
    const col = placed.length ? (placed[0].x + placed[placed.length - 1].x) / 2 : nextCol++;
    const me: PlacedNode = {
      id: myId,
      label: node.label,
      x: col,
      y: depth,
      hasChildren: node.children.length > 0,
      collapsed: isCollapsed,
    };
    nodes.push(me);
    for (const c of placed) edges.push({ x1: col, y1: depth, x2: c.x, y2: c.y });
    return me;
  }
  place(root, 0);

  const toX = (c: number) => PAD + c * COL_W + COL_W / 2;
  const toY = (d: number) => PAD + d * ROW_H + 16;
  for (const n of nodes) {
    n.x = toX(n.x);
    n.y = toY(n.y);
  }
  for (const e of edges) {
    e.x1 = toX(e.x1);
    e.y1 = toY(e.y1);
    e.x2 = toX(e.x2);
    e.y2 = toY(e.y2);
  }
  return { nodes, edges, width: nextCol * COL_W + 2 * PAD, height: (maxDepth + 1) * ROW_H + 2 * PAD };
}

function short(label: string): string {
  return label.length > 22 ? label.slice(0, 21) + "…" : label;
}

/** `revealed` nodes (id < revealCount) are solid; the rest are dimmed, matching the text view. */
export default function AstTree({ root, revealCount }: { root: TreeNode; revealCount: number }) {
  const [collapsed, setCollapsed] = useState<ReadonlySet<number>>(new Set());
  const { nodes, edges, width, height } = layout(root, collapsed);

  function toggle(nodeId: number) {
    setCollapsed((prev) => {
      const next = new Set(prev);
      next.has(nodeId) ? next.delete(nodeId) : next.add(nodeId);
      return next;
    });
  }

  return (
    <div className="ast-wrap">
      <svg className="ast-svg" width={width} height={height} viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Abstract syntax tree">
        {edges.map((e, i) => (
          <line key={i} className="ast-edge" x1={e.x1} y1={e.y1} x2={e.x2} y2={e.y2} />
        ))}
        {nodes.map((n) => {
          const w = Math.max(44, short(n.label).length * 7 + 16);
          const dim = n.id >= revealCount;
          return (
            <g
              key={n.id}
              className={`ast-node${dim ? " ast-dim" : ""}${n.collapsed ? " ast-collapsed" : ""}`}
              transform={`translate(${n.x}, ${n.y})`}
              onClick={() => n.hasChildren && toggle(n.id)}
              style={{ cursor: n.hasChildren ? "pointer" : "default" }}
            >
              <rect x={-w / 2} y={-13} width={w} height={26} rx={5} />
              <text x={0} y={4} textAnchor="middle">
                {short(n.label)}
              </text>
              {n.collapsed && (
                <text className="ast-plus" x={w / 2 - 7} y={4} textAnchor="middle">
                  +
                </text>
              )}
              <title>{n.label}</title>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
