"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import * as d3 from "d3";
import type { GraphResponse, GraphNode, GraphEdge } from "@/lib/api-client";
import {
  FORCE_CONFIG,
  entityColor,
  edgeStroke,
  edgeWidth,
  edgeDash,
  edgeOpacity,
  ENTITY_COLORS,
  RELATIONSHIP_COLORS,
} from "@/lib/d3-config";

/* ── Types ── */
interface Props {
  data: GraphResponse;
}

interface SimNode extends Omit<GraphNode, "x" | "y">, d3.SimulationNodeDatum {}

/* ── Card dimensions ── */
const CARD_W = 220;
const CARD_H_COLLAPSED = 80;
const CARD_H_EXPANDED = 260;
const CARD_RX = 14;
const TRUNCATE_LEN = 100;

function truncate(text: string, len: number) {
  if (text.length <= len) return text;
  return text.slice(0, len) + "…";
}

/* helper: light-to-dark gradient stops for an entity colour */
function gradientStops(hex: string) {
  return { start: hex + "30", mid: hex + "18", end: hex + "08" };
}

/* ── Component ── */
export default function ForceGraph({ data }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [legendOpen, setLegendOpen] = useState(true);
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set());

  const handleDeselect = useCallback(() => setSelected(null), []);
  const toggleExpand = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  useEffect(() => {
    if (!svgRef.current || !data.nodes.length) return;
    const cleanup = render(
      svgRef.current,
      tooltipRef.current!,
      data,
      setSelected,
      toggleExpand,
      expandedIds,
    );
    return cleanup;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, expandedIds]);

  // Collect unique entity types & relationship types in data
  const entityTypes = [
    ...new Set(data.nodes.map((n) => n.entity_type ?? "Custom")),
  ];
  const relTypes = [
    ...new Set(data.edges.map((e) => e.relationship_type).filter(Boolean)),
  ];

  return (
    <div className="relative w-full h-full overflow-hidden bg-[#09090b]">
      {/* ── SVG canvas ── */}
      <svg ref={svgRef} className="w-full h-full" />

      {/* ── Floating tooltip ── */}
      <div
        ref={tooltipRef}
        className="pointer-events-none absolute z-40 hidden rounded-xl bg-surface/95 border border-[var(--border)] px-3 py-2 text-xs shadow-lg backdrop-blur-sm max-w-[260px]"
      />

      {/* ── Legend panel ── */}
      <div className="absolute top-3 left-3 z-20">
        <button
          onClick={() => setLegendOpen(!legendOpen)}
          className="text-[10px] font-medium px-2.5 py-1.5 rounded-lg bg-surface/90 border border-[var(--border)] text-[var(--text-muted)] hover:text-white backdrop-blur-sm transition"
        >
          {legendOpen ? "Hide" : "Legend"}
        </button>
        {legendOpen && (
          <div className="mt-2 bg-surface/95 backdrop-blur-sm border border-[var(--border)] rounded-xl p-3 space-y-3 animate-in w-44">
            <div>
              <p className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5">
                Entities
              </p>
              <div className="space-y-1">
                {entityTypes.map((et) => (
                  <div key={et} className="flex items-center gap-2">
                    <span
                      className="w-2.5 h-2.5 rounded-full shrink-0"
                      style={{ background: entityColor(et) }}
                    />
                    <span className="text-[11px] text-[var(--text-secondary)]">
                      {et}
                    </span>
                  </div>
                ))}
              </div>
            </div>
            {relTypes.length > 0 && (
              <div>
                <p className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5">
                  Relationships
                </p>
                <div className="space-y-1">
                  {relTypes.map((rt) => (
                    <div key={rt} className="flex items-center gap-2">
                      <span
                        className="w-4 h-[2px] rounded shrink-0"
                        style={{
                          background:
                            RELATIONSHIP_COLORS[rt] ??
                            RELATIONSHIP_COLORS.default,
                        }}
                      />
                      <span className="text-[11px] text-[var(--text-secondary)]">
                        {rt.replace(/_/g, " ")}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Node detail panel (selected) ── */}
      {selected && (
        <div className="absolute top-3 right-3 z-20 w-72 bg-surface/95 backdrop-blur-sm border border-[var(--border)] rounded-2xl p-4 space-y-3 animate-in shadow-lg max-h-[80vh] overflow-y-auto">
          <div className="flex items-start justify-between">
            <div className="space-y-1 min-w-0">
              <h4 className="font-semibold text-sm text-white">
                {selected.label}
              </h4>
              <span
                className="inline-block text-[10px] font-medium px-2 py-0.5 rounded-full"
                style={{
                  background: entityColor(selected.entity_type) + "22",
                  color: entityColor(selected.entity_type),
                }}
              >
                {selected.entity_type ?? "Custom"}
              </span>
            </div>
            <button
              onClick={handleDeselect}
              className="text-[var(--text-muted)] hover:text-white transition text-sm leading-none p-1"
            >
              ✕
            </button>
          </div>
          {/* Full content */}
          {selected.content && (
            <div className="border-t border-[var(--border)] pt-2">
              <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap">
                {selected.content}
              </p>
            </div>
          )}
          {selected.metadata && Object.keys(selected.metadata).length > 0 && (
            <div className="space-y-1 border-t border-[var(--border)] pt-2">
              {Object.entries(selected.metadata).map(([k, v]) => (
                <div key={k} className="flex gap-2 text-[11px]">
                  <span className="text-[var(--text-muted)] shrink-0">{k}:</span>
                  <span className="text-[var(--text-secondary)] truncate">
                    {String(v)}
                  </span>
                </div>
              ))}
            </div>
          )}
          {(() => {
            const connected = data.edges.filter(
              (e) => e.source === selected.id || e.target === selected.id,
            );
            if (!connected.length) return null;
            return (
              <div className="space-y-1 border-t border-[var(--border)] pt-2">
                <p className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider">
                  Relationships ({connected.length})
                </p>
                <div className="max-h-40 overflow-y-auto space-y-1">
                  {connected.slice(0, 15).map((e, i) => {
                    const other =
                      e.source === selected.id ? e.target : e.source;
                    const otherNode = data.nodes.find((n) => n.id === other);
                    return (
                      <div
                        key={i}
                        className="flex items-center gap-1.5 text-[11px]"
                      >
                        <span
                          className="w-1.5 h-1.5 rounded-full shrink-0"
                          style={{
                            background: entityColor(otherNode?.entity_type),
                          }}
                        />
                        <span className="text-[var(--text-secondary)] truncate">
                          {otherNode?.label ?? other.slice(0, 8)}
                        </span>
                        <span className="text-[var(--text-muted)] ml-auto shrink-0 text-[10px]">
                          {e.relationship_type?.replace(/_/g, " ") ?? e.edge_type}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })()}
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════
//  D3 render — card-based nodes with gradient backgrounds
// ═══════════════════════════════════════════════════════

function render(
  svg: SVGSVGElement,
  tooltip: HTMLDivElement,
  data: GraphResponse,
  onSelect: (n: GraphNode | null) => void,
  onToggleExpand: (id: string) => void,
  expandedIds: Set<string>,
): () => void {
  const { width, height } = svg.getBoundingClientRect();
  const root = d3.select(svg);
  root.selectAll("*").remove();

  // Clone data for D3 mutation
  const nodes: SimNode[] = data.nodes.map(({ x, y, ...rest }) => ({
    ...rest,
    x: x ?? undefined,
    y: y ?? undefined,
  }));
  const edges: (GraphEdge & { source: any; target: any })[] = data.edges.map(
    (e) => ({ ...e }),
  );

  // ── Defs: gradients + arrow markers ──
  const defs = root.append("defs");

  // Per-entity-type gradient
  const usedTypes = [...new Set(nodes.map((n) => n.entity_type ?? "Custom"))];
  usedTypes.forEach((et) => {
    const color = entityColor(et);
    const s = gradientStops(color);
    const grad = defs
      .append("linearGradient")
      .attr("id", `grad-${et}`)
      .attr("x1", "0%").attr("y1", "0%")
      .attr("x2", "100%").attr("y2", "100%");
    grad.append("stop").attr("offset", "0%").attr("stop-color", s.start);
    grad.append("stop").attr("offset", "50%").attr("stop-color", s.mid);
    grad.append("stop").attr("offset", "100%").attr("stop-color", s.end);
  });

  // Arrow markers per relationship type
  const markerTypes = [
    ...new Set(edges.map((e) => e.relationship_type ?? e.edge_type)),
  ];
  markerTypes.forEach((mt) => {
    defs
      .append("marker")
      .attr("id", `arrow-${mt}`)
      .attr("viewBox", "0 -4 8 8")
      .attr("refX", 14)
      .attr("refY", 0)
      .attr("markerWidth", 5)
      .attr("markerHeight", 5)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-4L8,0L0,4")
      .attr("fill", edgeStroke({ relationship_type: mt, edge_type: mt } as any));
  });

  // Drop shadow for cards
  const shadow = defs.append("filter").attr("id", "card-shadow")
    .attr("x", "-20%").attr("y", "-20%").attr("width", "140%").attr("height", "140%");
  shadow.append("feDropShadow")
    .attr("dx", "0").attr("dy", "2").attr("stdDeviation", "4")
    .attr("flood-color", "rgba(0,0,0,0.5)").attr("flood-opacity", "0.5");

  // ── Simulation — wider spacing for card nodes ──
  const simulation = d3
    .forceSimulation(nodes)
    .force(
      "link",
      d3
        .forceLink<SimNode, any>(edges)
        .id((d: any) => d.id)
        .distance((d: any) => {
          const base = FORCE_CONFIG.linkDistance(d);
          return Math.max(base, 250);
        }),
    )
    .force("charge", d3.forceManyBody().strength(-600))
    .force(
      "center",
      d3
        .forceCenter(width / 2, height / 2)
        .strength(FORCE_CONFIG.centerStrength),
    )
    .force("collision", d3.forceCollide(CARD_W * 0.65));

  // ── Zoom ──
  const g = root.append("g");
  root.call(
    d3.zoom<SVGSVGElement, unknown>().scaleExtent([0.08, 4]).on("zoom", (e) => {
      g.attr("transform", e.transform);
    }) as any,
  );

  // ── Edges ──
  const linkGroup = g.append("g").attr("class", "edges");
  const link = linkGroup
    .selectAll("line")
    .data(edges)
    .join("line")
    .attr("stroke", (d) => edgeStroke(d))
    .attr("stroke-width", (d) => edgeWidth(d))
    .attr("stroke-dasharray", (d) => edgeDash(d))
    .attr("opacity", (d) => edgeOpacity(d))
    .attr("marker-end", (d) => `url(#arrow-${d.relationship_type ?? d.edge_type})`);

  // ── Edge labels ──
  const edgeLabelGroup = g.append("g").attr("class", "edge-labels");
  const edgeLabel = edgeLabelGroup
    .selectAll("text")
    .data(edges.filter((e) => e.relationship_type))
    .join("text")
    .text((d) => d.relationship_type?.replace(/_/g, " ") ?? "")
    .attr("text-anchor", "middle")
    .attr("fill", (d) => edgeStroke(d))
    .attr("font-size", 8)
    .attr("font-weight", 500)
    .attr("opacity", 0.6)
    .attr("dy", -4);

  // ── Hyperedge hulls ──
  if (data.hyperedges && data.hyperedges.length > 0) {
    const hullGroup = g.insert("g", ":first-child").attr("class", "hyperedges");
    const hullColors = [
      "rgba(99,102,241,0.08)", "rgba(34,211,238,0.08)",
      "rgba(251,191,36,0.08)", "rgba(248,113,113,0.08)", "rgba(52,211,153,0.08)",
    ];
    const hulls = data.hyperedges.map((he, idx) => ({
      id: he.id, label: he.label,
      memberIds: new Set(he.member_ids ?? []),
      color: hullColors[idx % hullColors.length],
    }));
    function updateHulls() {
      hullGroup.selectAll("path").remove();
      hulls.forEach((h) => {
        const pts: [number, number][] = [];
        nodes.forEach((n) => {
          if (h.memberIds.has(n.id) && n.x != null && n.y != null) pts.push([n.x, n.y]);
        });
        if (pts.length < 3) return;
        const hull = d3.polygonHull(pts);
        if (!hull) return;
        const cx = d3.mean(hull, (p) => p[0])!;
        const cy = d3.mean(hull, (p) => p[1])!;
        const expanded = hull.map(([px, py]) => {
          const dx = px - cx, dy = py - cy;
          const dist = Math.sqrt(dx * dx + dy * dy);
          return [(px + (dx / dist) * 40), (py + (dy / dist) * 40)] as [number, number];
        });
        hullGroup.append("path").datum(expanded)
          .attr("d", (d) => `M${d.map((p) => p.join(",")).join("L")}Z`)
          .attr("fill", h.color)
          .attr("stroke", h.color.replace("0.08", "0.2"))
          .attr("stroke-width", 1);
      });
    }
    simulation.on("tick.hulls", updateHulls);
  }

  // ── Card Nodes ──
  const nodeGroup = g.append("g").attr("class", "nodes");
  const node = nodeGroup
    .selectAll<SVGGElement, SimNode>("g")
    .data(nodes)
    .join("g")
    .attr("cursor", "pointer")
    .call(drag(simulation) as any);

  // Card background rect with gradient + rounded corners
  node.append("rect")
    .attr("x", -CARD_W / 2)
    .attr("y", (d) => -(expandedIds.has(d.id) ? CARD_H_EXPANDED : CARD_H_COLLAPSED) / 2)
    .attr("width", CARD_W)
    .attr("height", (d) => expandedIds.has(d.id) ? CARD_H_EXPANDED : CARD_H_COLLAPSED)
    .attr("rx", CARD_RX)
    .attr("ry", CARD_RX)
    .attr("fill", (d) => `url(#grad-${d.entity_type ?? "Custom"})`)
    .attr("stroke", (d) => entityColor(d.entity_type) + "55")
    .attr("stroke-width", 1.2)
    .attr("filter", "url(#card-shadow)");

  // Accent bar at top
  node.append("rect")
    .attr("x", -CARD_W / 2)
    .attr("y", (d) => -(expandedIds.has(d.id) ? CARD_H_EXPANDED : CARD_H_COLLAPSED) / 2)
    .attr("width", CARD_W)
    .attr("height", 3)
    .attr("rx", CARD_RX)
    .attr("fill", (d) => entityColor(d.entity_type));

  // Entity type badge
  node.append("foreignObject")
    .attr("x", -CARD_W / 2 + 8)
    .attr("y", (d) => -(expandedIds.has(d.id) ? CARD_H_EXPANDED : CARD_H_COLLAPSED) / 2 + 8)
    .attr("width", CARD_W - 16)
    .attr("height", 18)
    .append("xhtml:div")
    .style("display", "flex")
    .style("align-items", "center")
    .style("gap", "6px")
    .html((d: SimNode) => {
      const color = entityColor(d.entity_type);
      return `<span style="display:inline-block;width:6px;height:6px;border-radius:50%;background:${color};flex-shrink:0"></span>
        <span style="font-size:9px;font-weight:600;color:${color};text-transform:uppercase;letter-spacing:0.5px;font-family:Inter,sans-serif">${d.entity_type ?? "Custom"}</span>`;
    });

  // Content text — truncated or full
  node.append("foreignObject")
    .attr("x", -CARD_W / 2 + 10)
    .attr("y", (d) => -(expandedIds.has(d.id) ? CARD_H_EXPANDED : CARD_H_COLLAPSED) / 2 + 28)
    .attr("width", CARD_W - 20)
    .attr("height", (d) => (expandedIds.has(d.id) ? CARD_H_EXPANDED - 44 : CARD_H_COLLAPSED - 44))
    .append("xhtml:div")
    .style("font-size", "11px")
    .style("line-height", "1.45")
    .style("color", "#e2e8f0")
    .style("font-family", "Inter, sans-serif")
    .style("overflow", "hidden")
    .style("word-break", "break-word")
    .html((d: SimNode) => {
      const fullText = d.content || d.label;
      const isExpanded = expandedIds.has(d.id);
      if (isExpanded) {
        return `<div style="max-height:${CARD_H_EXPANDED - 48}px;overflow-y:auto;padding-right:4px">${escapeHtml(fullText)}</div>`;
      }
      const shown = truncate(fullText, TRUNCATE_LEN);
      const hasMore = fullText.length > TRUNCATE_LEN;
      return `<div>${escapeHtml(shown)}${hasMore ? '<span style="color:#818cf8;font-size:10px;margin-left:3px;cursor:pointer" class="expand-hint"> ▾ more</span>' : ''}</div>`;
    });

  // ── Interactions ──
  const tt = d3.select(tooltip);

  node
    .on("mouseover", function (event, d: SimNode) {
      const connectedIds = new Set<string>();
      edges.forEach((e) => {
        if (e.source.id === d.id) connectedIds.add(e.target.id);
        if (e.target.id === d.id) connectedIds.add(e.source.id);
      });
      node.attr("opacity", (n: SimNode) =>
        n.id === d.id || connectedIds.has(n.id) ? 1 : 0.2,
      );
      link.attr("opacity", (e: any) =>
        e.source.id === d.id || e.target.id === d.id ? 0.9 : 0.05,
      );
      edgeLabel.attr("opacity", (e: any) =>
        e.source.id === d.id || e.target.id === d.id ? 1 : 0.05,
      );
    })
    .on("mouseout", function () {
      node.attr("opacity", 1);
      link.attr("opacity", (d: any) => edgeOpacity(d));
      edgeLabel.attr("opacity", 0.6);
      tt.classed("hidden", true);
    })
    .on("click", function (event, d: SimNode) {
      event.stopPropagation();
      // Double-click expands card, single-click selects in detail panel
      onToggleExpand(d.id);
      onSelect(d as unknown as GraphNode);
    });

  // Click background to deselect
  root.on("click", () => onSelect(null));

  // ── Tick ──
  simulation.on("tick", () => {
    link
      .attr("x1", (d: any) => d.source.x)
      .attr("y1", (d: any) => d.source.y)
      .attr("x2", (d: any) => d.target.x)
      .attr("y2", (d: any) => d.target.y);

    edgeLabel
      .attr("x", (d: any) => (d.source.x + d.target.x) / 2)
      .attr("y", (d: any) => (d.source.y + d.target.y) / 2);

    node.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
  });

  return () => {
    simulation.stop();
  };
}

// ═══════════════════════════════════════════════════════
//  Drag behaviour
// ═══════════════════════════════════════════════════════

function drag(simulation: d3.Simulation<SimNode, undefined>) {
  return d3
    .drag<SVGGElement, SimNode>()
    .on("start", (event, d) => {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x;
      d.fy = d.y;
    })
    .on("drag", (event, d) => {
      d.fx = event.x;
      d.fy = event.y;
    })
    .on("end", (event, d) => {
      if (!event.active) simulation.alphaTarget(0);
      d.fx = null;
      d.fy = null;
    });
}

// ── HTML escape helper ──
function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/\n/g, "<br/>");
}
