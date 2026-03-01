/**
 * D3 force-simulation configuration — shared constants & factory.
 * Aligned with entity-type knowledge graph (no clusters).
 */

import type { GraphNode, GraphEdge } from "./api-client";

// ═══════════════════════════════════════════════════════
//  Entity-type colour palette
// ═══════════════════════════════════════════════════════

export const ENTITY_COLORS: Record<string, string> = {
  Goal: "#34d399",
  KPI: "#60a5fa",
  OKR: "#a78bfa",
  Risk: "#f87171",
  Action: "#fbbf24",
  Owner: "#fb923c",
  Metric: "#38bdf8",
  Custom: "#71717a",
};

export function entityColor(entityType?: string | null): string {
  if (!entityType) return ENTITY_COLORS.Custom;
  return ENTITY_COLORS[entityType] ?? ENTITY_COLORS.Custom;
}

// ═══════════════════════════════════════════════════════
//  Relationship-type colour palette
// ═══════════════════════════════════════════════════════

export const RELATIONSHIP_COLORS: Record<string, string> = {
  achieved_by: "#34d399",
  measured_by: "#60a5fa",
  depends_on: "#a78bfa",
  mitigates: "#fbbf24",
  owns: "#fb923c",
  supports: "#818cf8",
  contradicts: "#f87171",
  threatens: "#ef4444",
  related_to: "#38bdf8",
  similarity: "#475569",
  bridge: "#f59e0b",
  default: "#475569",
};

export function relationshipColor(relType?: string): string {
  if (!relType) return RELATIONSHIP_COLORS.default;
  return RELATIONSHIP_COLORS[relType] ?? RELATIONSHIP_COLORS.default;
}

// ═══════════════════════════════════════════════════════
//  Node sizing
// ═══════════════════════════════════════════════════════

export function nodeRadius(node: GraphNode): number {
  // Base size with slight randomness from metadata count
  const base = 12;
  const metaCount = node.metadata ? Object.keys(node.metadata).length : 0;
  const extra = Math.min(metaCount * 2, 8);
  return base + extra;
}

// ═══════════════════════════════════════════════════════
//  Force parameters
// ═══════════════════════════════════════════════════════

export const FORCE_CONFIG = {
  chargeStrength: -600,
  linkDistance: (edge: GraphEdge) => {
    if (edge.edge_type === "bridge") return 380;
    // Scale by weight — higher weight = shorter link
    return 180 + (1 - Math.min(edge.weight, 1)) * 140;
  },
  centerStrength: 0.04,
  collisionRadius: 140,
} as const;

// ═══════════════════════════════════════════════════════
//  Edge styling
// ═══════════════════════════════════════════════════════

export function edgeStroke(edge: GraphEdge): string {
  if (edge.edge_type === "bridge") return RELATIONSHIP_COLORS.bridge;
  return relationshipColor(edge.relationship_type);
}

export function edgeWidth(edge: GraphEdge): number {
  if (edge.edge_type === "bridge") return 2.5;
  return Math.max(1, Math.min(edge.weight * 4, 4));
}

export function edgeDash(edge: GraphEdge): string {
  if (edge.edge_type === "bridge") return "6 3";
  if (edge.relationship_type === "contradicts") return "4 2";
  return "none";
}

export function edgeOpacity(edge: GraphEdge): number {
  return Math.max(0.3, Math.min(edge.weight, 0.85));
}

