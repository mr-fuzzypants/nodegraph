/**
 * Dagre-based layout for React Flow nodes (top-left positions).
 */
import dagre from 'dagre';
import type { Edge as FlowEdge, Node as FlowNode } from '@xyflow/react';
import type { NodeData } from '../types/uiTypes';

export type DagreRankDirection = 'LR' | 'TB';

/** Conservative boxes so Dagre keeps enough Y gap between nodes in LR mode (nodesep = within-rank). */
const DEFAULT_NODE_SIZE = { width: 340, height: 200 };

const NODE_TYPE_SIZE: Record<string, { width: number; height: number }> = {
  functionNode: { width: 400, height: 240 },
  networkNode: { width: 368, height: 220 },
  tunnelInputNode: { width: 384, height: 188 },
  tunnelOutputNode: { width: 384, height: 188 },
  tunnelNode: { width: 384, height: 188 },
};

export function estimateNodeDimensions(node: FlowNode<NodeData>): { width: number; height: number } {
  const t = node.type ?? 'functionNode';
  return NODE_TYPE_SIZE[t] ?? DEFAULT_NODE_SIZE;
}

function nodeBox(node: FlowNode<NodeData>): { width: number; height: number } {
  return estimateNodeDimensions(node);
}

function hasPath(adj: Map<string, string[]>, start: string, goal: string): boolean {
  const seen = new Set<string>();
  const stack = [start];
  while (stack.length) {
    const u = stack.pop()!;
    if (u === goal) return true;
    if (seen.has(u)) continue;
    seen.add(u);
    for (const v of adj.get(u) ?? []) stack.push(v);
  }
  return false;
}

/** Keep a maximal acyclic subset of edges (edges that would complete a cycle are dropped). */
export function filterAcyclicEdges(nodeIds: Set<string>, edges: FlowEdge[]): FlowEdge[] {
  const adj = new Map<string, string[]>();
  for (const id of nodeIds) adj.set(id, []);
  const kept: FlowEdge[] = [];
  for (const e of edges) {
    if (!nodeIds.has(e.source) || !nodeIds.has(e.target)) continue;
    if (hasPath(adj, e.target, e.source)) continue;
    adj.get(e.source)!.push(e.target);
    kept.push(e);
  }
  return kept;
}

/**
 * Returns new top-left positions for each node id in `layoutNodes`.
 */
export function layoutWithDagre(
  layoutNodes: FlowNode<NodeData>[],
  edges: FlowEdge[],
  rankdir: DagreRankDirection,
): Map<string, { x: number; y: number }> {
  const ids = new Set(layoutNodes.map((n) => n.id));
  const dagreEdges = filterAcyclicEdges(ids, edges);

  const g = new dagre.graphlib.Graph({ compound: false, multigraph: false });
  g.setGraph({
    rankdir,
    // LR: nodesep = vertical gap between nodes sharing a rank; ranksep = horizontal gap between ranks
    nodesep: 84,
    ranksep: 96,
    marginx: 32,
    marginy: 36,
    edgesep: 28,
  });
  g.setDefaultEdgeLabel(() => ({}));

  for (const node of layoutNodes) {
    const { width, height } = nodeBox(node);
    g.setNode(node.id, { width, height });
  }
  for (const e of dagreEdges) {
    g.setEdge(e.source, e.target);
  }

  dagre.layout(g);

  const out = new Map<string, { x: number; y: number }>();
  for (const node of layoutNodes) {
    const d = g.node(node.id);
    if (!d) continue;
    const { width, height } = nodeBox(node);
    out.set(node.id, {
      x: d.x - width / 2,
      y: d.y - height / 2,
    });
  }
  return out;
}

/**
 * Top-left positions on a near-square grid (√N columns), anchored at the
 * selection's current top-left so the group does not jump to the canvas origin.
 */
export function layoutAsGrid(layoutNodes: FlowNode<NodeData>[]): Map<string, { x: number; y: number }> {
  const n = layoutNodes.length;
  const cols = Math.max(1, Math.ceil(Math.sqrt(n)));
  const gapX = 56;
  const gapY = 56;

  let anchorX = Infinity;
  let anchorY = Infinity;
  for (const node of layoutNodes) {
    anchorX = Math.min(anchorX, node.position.x);
    anchorY = Math.min(anchorY, node.position.y);
  }
  if (!Number.isFinite(anchorX)) anchorX = 0;
  if (!Number.isFinite(anchorY)) anchorY = 0;

  const boxes = layoutNodes.map((node) => estimateNodeDimensions(node));
  const maxW = Math.max(...boxes.map((b) => b.width), 280);
  const maxH = Math.max(...boxes.map((b) => b.height), 160);
  const cellW = maxW + gapX;
  const cellH = maxH + gapY;

  const sorted = [...layoutNodes].sort((a, b) => a.id.localeCompare(b.id));
  const out = new Map<string, { x: number; y: number }>();
  sorted.forEach((node, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    const { width, height } = estimateNodeDimensions(node);
    const x = anchorX + col * cellW + (maxW - width) / 2;
    const y = anchorY + row * cellH + (maxH - height) / 2;
    out.set(node.id, { x, y });
  });
  return out;
}
