/**
 * D3 force-simulation configuration — shared constants & factory.
 */

import type { GraphNode, GraphEdge } from "./api-client";

// ═══════════════════════════════════════════════════════
//  Colour palette
// ═══════════════════════════════════════════════════════

const CLUSTER_COLORS = [
  "#6366f1", "#22d3ee", "#f59e0b", "#10b981",
  "#ef4444", "#a855f7", "#ec4899", "#14b8a6",
  "#f97316", "#3b82f6",
];

export function clusterColor(index: number): string {
  return CLUSTER_COLORS[index % CLUSTER_COLORS.length];
}

// ═══════════════════════════════════════════════════════
//  Node sizing
// ═══════════════════════════════════════════════════════

export function nodeRadius(node: GraphNode): number {
  return node.type === "cluster" ? 28 : 10;
}

// ═══════════════════════════════════════════════════════
//  Force parameters
// ═══════════════════════════════════════════════════════

export const FORCE_CONFIG = {
  chargeStrength: -120,
  linkDistance: (edge: GraphEdge) => {
    switch (edge.edge_type) {
      case "hierarchy":
        return 60;
      case "similarity":
        return 100 / (edge.weight + 0.01);
      case "bridge":
        return 200;
      default:
        return 100;
    }
  },
  centerStrength: 0.05,
  collisionRadius: 14,
} as const;

// ═══════════════════════════════════════════════════════
//  Edge styling
// ═══════════════════════════════════════════════════════

export function edgeStroke(edge: GraphEdge): string {
  switch (edge.edge_type) {
    case "hierarchy":
      return "#6366f1";
    case "similarity":
      return "#475569";
    case "bridge":
      return "#f59e0b";
    default:
      return "#475569";
  }
}

export function edgeWidth(edge: GraphEdge): number {
  return edge.edge_type === "bridge" ? 2 : Math.max(0.5, edge.weight * 3);
}

export function edgeDash(edge: GraphEdge): string {
  return edge.edge_type === "bridge" ? "6 3" : "none";
}
