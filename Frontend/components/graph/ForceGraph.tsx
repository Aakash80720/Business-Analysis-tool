"use client";

import { useEffect, useRef, useState, useCallback, useMemo } from "react";
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
const CARD_W = 240;
const CARD_H_COLLAPSED = 110;
const CARD_H_EXPANDED = 340;
const CARD_RX = 14;
const TRUNCATE_LEN = 80;

function truncate(text: string, len: number) {
  if (text.length <= len) return text;
  return text.slice(0, len) + "…";
}

function gradientStops(hex: string) {
  return { start: hex + "30", mid: hex + "18", end: hex + "08" };
}

/* ── Component ── */
export default function ForceGraph({ data }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [legendOpen, setLegendOpen] = useState(true);

  // Track expanded cards in a ref so D3 handlers can read/write without
  // triggering a React re-render + full graph rebuild.
  const expandedRef = useRef<Set<string>>(new Set());
  // Ref to the D3 node selection so click handlers can update cards in-place
  const nodeSelRef = useRef<d3.Selection<SVGGElement, SimNode, SVGGElement, unknown> | null>(null);
  // Track the currently-active (selected) node so highlight persists after mouseout
  const activeIdRef = useRef<string | null>(null);
  // Expose a highlight function so React can trigger highlights from the detail panel
  const highlightRef = useRef<((nodeId: string | null) => void) | null>(null);
  // Expose a center-on-node function so React can smoothly pan to any node
  const centerFnRef = useRef<((nodeId: string) => void) | null>(null);
  // Expose a search-highlight function that dims everything except matching IDs
  const searchHighlightRef = useRef<((matchIds: Set<string> | null) => void) | null>(null);

  // ── Search state ──
  const [searchQuery, setSearchQuery] = useState("");
  const [searchFocused, setSearchFocused] = useState(false);

  // Build a searchable index: for each node, combine label + content + entity_type + properties + connected relationship types
  const searchResults = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return [];
    const words = q.split(/\s+/);

    // Pre-compute connected relationship types per node
    const nodeRels = new Map<string, string[]>();
    data.edges.forEach((e) => {
      const rt = (e.relationship_type ?? e.edge_type ?? "").toLowerCase().replace(/_/g, " ");
      if (!nodeRels.has(e.source)) nodeRels.set(e.source, []);
      if (!nodeRels.has(e.target)) nodeRels.set(e.target, []);
      nodeRels.get(e.source)!.push(rt);
      nodeRels.get(e.target)!.push(rt);
    });

    return data.nodes
      .map((n) => {
        const fields: string[] = [
          n.label ?? "",
          n.content ?? "",
          n.entity_type ?? "",
          ...(nodeRels.get(n.id) ?? []),
        ];
        if (n.properties) {
          Object.entries(n.properties).forEach(([k, v]) => {
            fields.push(k.replace(/_/g, " "));
            fields.push(String(v));
          });
        }
        if (n.metadata) {
          Object.values(n.metadata).forEach((v) => fields.push(String(v)));
        }
        const blob = fields.join(" ").toLowerCase();
        const score = words.filter((w) => blob.includes(w)).length;
        return { node: n, score };
      })
      .filter((r) => r.score > 0)
      .sort((a, b) => b.score - a.score)
      .slice(0, 12);
  }, [searchQuery, data.nodes, data.edges]);

  // When search results change, highlight matching nodes in the graph
  useEffect(() => {
    if (!searchQuery.trim()) {
      searchHighlightRef.current?.(null);
      return;
    }
    const ids = new Set(searchResults.map((r) => r.node.id));
    searchHighlightRef.current?.(ids.size > 0 ? ids : null);
  }, [searchResults, searchQuery]);

  const handleDeselect = useCallback(() => {
    setSelected(null);
    activeIdRef.current = null;
    highlightRef.current?.(null);
  }, []);

  // Navigate to a connected node from the detail panel
  const navigateToNode = useCallback((nodeId: string) => {
    const targetNode = data.nodes.find((n) => n.id === nodeId);
    if (!targetNode) return;
    setSelected(targetNode);
    activeIdRef.current = nodeId;
    highlightRef.current?.(nodeId);
    centerFnRef.current?.(nodeId);
  }, [data.nodes]);

  useEffect(() => {
    if (!svgRef.current || !data.nodes.length) return;
    expandedRef.current = new Set(); // reset on new data
    const cleanup = render(
      svgRef.current,
      tooltipRef.current!,
      data,
      setSelected,
      expandedRef,
      nodeSelRef,
      activeIdRef,
      highlightRef,
      centerFnRef,
      searchHighlightRef,
    );
    return cleanup;
  }, [data]);

  const entityTypes = [
    ...new Set(data.nodes.map((n) => n.entity_type ?? "Custom")),
  ];
  const relTypes = [
    ...new Set(data.edges.map((e) => e.relationship_type).filter(Boolean)),
  ];

  return (
    <div className="relative w-full h-full overflow-hidden bg-[#09090b]">
      <svg ref={svgRef} className="w-full h-full" />

      <div
        ref={tooltipRef}
        className="pointer-events-none absolute z-40 hidden rounded-xl bg-surface/95 border border-[var(--border)] px-3 py-2 text-xs shadow-lg backdrop-blur-sm max-w-[260px]"
      />

      {/* ── Gradient Toolbar ── */}
      <div className="absolute inset-x-0 top-0 z-30 pointer-events-none"
           style={{ background: "linear-gradient(to bottom, #09090b 0%, rgba(9,9,11,0.85) 40%, rgba(9,9,11,0.45) 70%, transparent 100%)" }}>
        <div className="pointer-events-auto flex items-center gap-3 px-4 py-3">
          {/* Legend toggle */}
          <div className="relative">
            <button
              onClick={() => setLegendOpen(!legendOpen)}
              className="flex items-center gap-1.5 text-[10px] font-medium px-2.5 py-1.5 rounded-lg bg-white/[0.06] border border-white/10 text-[var(--text-muted)] hover:text-white hover:bg-white/10 transition"
            >
              <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path d="M4 6h16M4 12h10M4 18h6" strokeLinecap="round" />
              </svg>
              Legend
            </button>
            {legendOpen && (
              <div className="absolute top-full left-0 mt-2 bg-surface/95 backdrop-blur-sm border border-[var(--border)] rounded-xl p-3 space-y-3 animate-in w-44 shadow-xl">
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

          {/* Divider */}
          <div className="w-px h-5 bg-white/10" />

          {/* Search field */}
          <div className="relative flex-1 max-w-sm">
            <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[var(--text-muted)]" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" strokeLinecap="round" />
            </svg>
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              onFocus={() => setSearchFocused(true)}
              onBlur={() => setTimeout(() => setSearchFocused(false), 200)}
              placeholder="Search nodes… label, type, property, relation"
              className="w-full pl-9 pr-8 py-1.5 rounded-lg bg-white/[0.06] border border-white/10 focus:border-primary focus:bg-white/[0.09] outline-none text-xs text-white placeholder:text-[var(--text-muted)] transition"
            />
            {searchQuery && (
              <button
                onMouseDown={(e) => { e.preventDefault(); setSearchQuery(""); }}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-white transition text-xs"
              >
                ✕
              </button>
            )}

            {/* Search results dropdown */}
            {searchFocused && searchQuery.trim() && (
              <div className="absolute top-full left-0 right-0 mt-1.5 bg-surface/95 backdrop-blur-sm border border-[var(--border)] rounded-xl overflow-hidden shadow-xl animate-in max-h-72 overflow-y-auto">
                {searchResults.length === 0 ? (
                  <div className="px-3 py-4 text-center text-[11px] text-[var(--text-muted)]">
                    No matching nodes
                  </div>
                ) : (
                  searchResults.map((r) => {
                    const n = r.node;
                    const rels = data.edges
                      .filter((e) => e.source === n.id || e.target === n.id)
                      .map((e) => e.relationship_type?.replace(/_/g, " "))
                      .filter(Boolean);
                    const uniqueRels = [...new Set(rels)].slice(0, 3);
                    return (
                      <button
                        key={n.id}
                        onMouseDown={(e) => {
                          e.preventDefault();
                          navigateToNode(n.id);
                          setSearchQuery("");
                        }}
                        className="flex items-start gap-2.5 w-full text-left px-3 py-2.5 hover:bg-white/5 transition-colors border-b border-[var(--border)] last:border-b-0 group"
                      >
                        <span
                          className="w-2 h-2 rounded-full mt-1 shrink-0"
                          style={{ background: entityColor(n.entity_type) }}
                        />
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2">
                            <span className="text-[11px] font-semibold text-white truncate group-hover:text-primary transition">
                              {n.label}
                            </span>
                            <span
                              className="text-[9px] font-medium px-1.5 py-0.5 rounded-full shrink-0"
                              style={{
                                background: entityColor(n.entity_type) + "22",
                                color: entityColor(n.entity_type),
                              }}
                            >
                              {n.entity_type ?? "Custom"}
                            </span>
                          </div>
                          {n.content && (
                            <p className="text-[10px] text-[var(--text-muted)] truncate mt-0.5">
                              {n.content.slice(0, 80)}
                            </p>
                          )}
                          {uniqueRels.length > 0 && (
                            <div className="flex gap-1 mt-1 flex-wrap">
                              {uniqueRels.map((rel) => (
                                <span key={rel} className="text-[9px] text-[var(--text-muted)] bg-white/5 px-1.5 py-0.5 rounded">
                                  {rel}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                        <span className="text-[var(--text-muted)] opacity-0 group-hover:opacity-100 transition-opacity text-[9px] mt-1 shrink-0">→</span>
                      </button>
                    );
                  })
                )}
              </div>
            )}
          </div>

          {/* Spacer — future tools go here */}
          <div className="flex-1" />

          {/* Node count badge */}
          <span className="text-[10px] text-[var(--text-muted)] tabular-nums">
            {data.nodes.length} nodes · {data.edges.length} edges
          </span>
        </div>
      </div>

      {/* Detail panel */}
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
          {selected.content && (
            <div className="border-t border-[var(--border)] pt-2">
              <p className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1">Content</p>
              <p className="text-[11px] text-[var(--text-secondary)] leading-relaxed whitespace-pre-wrap">
                {selected.content}
              </p>
            </div>
          )}
          {selected.properties && Object.keys(selected.properties).length > 0 && (
            <div className="space-y-1 border-t border-[var(--border)] pt-2">
              <p className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1">Properties</p>
              {Object.entries(selected.properties).map(([k, v]) => (
                <div key={k} className="flex gap-2 text-[11px]">
                  <span className="text-[var(--text-muted)] shrink-0 font-medium">{k.replace(/_/g, " ")}:</span>
                  <span className="text-[var(--text-secondary)]">{String(v)}</span>
                </div>
              ))}
            </div>
          )}
          {selected.metadata && Object.keys(selected.metadata).length > 0 && (
            <div className="space-y-1 border-t border-[var(--border)] pt-2">
              {Object.entries(selected.metadata).map(([k, v]) => (
                <div key={k} className="flex gap-2 text-[11px]">
                  <span className="text-[var(--text-muted)] shrink-0">{k}:</span>
                  <span className="text-[var(--text-secondary)] truncate">{String(v)}</span>
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
                    const other = e.source === selected.id ? e.target : e.source;
                    const otherNode = data.nodes.find((n) => n.id === other);
                    return (
                      <button
                        key={i}
                        onClick={() => otherNode && navigateToNode(otherNode.id)}
                        className="flex items-center gap-1.5 text-[11px] w-full text-left rounded-md px-1.5 py-1 -mx-1.5 hover:bg-white/5 transition-colors group cursor-pointer"
                      >
                        <span className="w-1.5 h-1.5 rounded-full shrink-0"
                          style={{ background: entityColor(otherNode?.entity_type) }} />
                        <span className="text-[var(--text-secondary)] truncate group-hover:text-white transition-colors underline decoration-dotted decoration-[var(--text-muted)] underline-offset-2">
                          {otherNode?.label ?? other.slice(0, 8)}
                        </span>
                        <span className="text-[var(--text-muted)] ml-auto shrink-0 text-[10px]">
                          {e.relationship_type?.replace(/_/g, " ") ?? e.edge_type}
                        </span>
                        <span className="text-[var(--text-muted)] opacity-0 group-hover:opacity-100 transition-opacity text-[9px]">→</span>
                      </button>
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
//  Build card HTML for a node
// ═══════════════════════════════════════════════════════
function cardHtml(d: SimNode, isExpanded: boolean): string {
  const color = entityColor(d.entity_type);
  const fullText = d.content || d.label;
  const props = (d as any).properties ?? {};
  const propEntries = Object.entries(props).slice(0, 6);

  let html = `<div style="font-size:12px;font-weight:700;color:#f1f5f9;line-height:1.3;margin-bottom:4px;word-break:break-word">${escapeHtml(d.label)}</div>`;
  html += `<div style="margin-bottom:5px"><span style="display:inline-flex;align-items:center;gap:4px;font-size:9px;font-weight:600;color:${color};text-transform:uppercase;letter-spacing:0.5px;background:${color}22;padding:1px 6px;border-radius:9999px"><span style="display:inline-block;width:5px;height:5px;border-radius:50%;background:${color}"></span>${d.entity_type ?? "Custom"}</span></div>`;

  if (propEntries.length > 0) {
    html += `<div style="margin-bottom:4px">`;
    for (const [k, v] of propEntries) {
      html += `<div style="font-size:9px;line-height:1.5;color:#94a3b8"><span style="color:#64748b;font-weight:500">${escapeHtml(k.replace(/_/g, " "))}:</span> <span style="color:#cbd5e1">${escapeHtml(String(v))}</span></div>`;
    }
    html += `</div>`;
  }

  if (isExpanded) {
    html += `<div style="border-top:1px solid rgba(148,163,184,0.15);padding-top:4px;margin-top:2px"><div style="font-size:10px;color:#94a3b8;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:3px">Content</div><div style="font-size:10px;line-height:1.5;color:#e2e8f0;max-height:${CARD_H_EXPANDED - 140}px;overflow-y:auto;word-break:break-word">${escapeHtml(fullText)}</div></div>`;
  } else {
    const shown = truncate(fullText, TRUNCATE_LEN);
    const hasMore = fullText.length > TRUNCATE_LEN;
    html += `<div style="font-size:10px;line-height:1.4;color:#94a3b8;word-break:break-word">${escapeHtml(shown)}${hasMore ? '<span style="color:#818cf8;font-size:9px;margin-left:2px;cursor:pointer"> ▾</span>' : ""}</div>`;
  }
  return html;
}

// ═══════════════════════════════════════════════════════
//  Smoothly toggle a card between collapsed/expanded
// ═══════════════════════════════════════════════════════
function toggleCard(
  nodeG: SVGGElement,
  d: SimNode,
  isExpanded: boolean,
) {
  const sel = d3.select<SVGGElement, SimNode>(nodeG);
  const h = isExpanded ? CARD_H_EXPANDED : CARD_H_COLLAPSED;
  const dur = 280;

  // Animate background rect
  sel.select<SVGRectElement>("rect.card-bg")
    .transition().duration(dur).ease(d3.easeCubicOut)
    .attr("y", -h / 2)
    .attr("height", h);

  // Animate accent bar
  sel.select<SVGRectElement>("rect.card-accent")
    .transition().duration(dur).ease(d3.easeCubicOut)
    .attr("y", -h / 2);

  // Update foreignObject size + content
  sel.select<SVGForeignObjectElement>("foreignObject")
    .transition().duration(dur).ease(d3.easeCubicOut)
    .attr("y", -h / 2 + 6)
    .attr("height", h - 16);

  // Re-render HTML content immediately (it'll be clipped by the transitioning height)
  sel.select<SVGForeignObjectElement>("foreignObject")
    .select("div")
    .html(cardHtml(d, isExpanded));
}

// ═══════════════════════════════════════════════════════
//  D3 render — runs ONCE per data change
// ═══════════════════════════════════════════════════════
function render(
  svg: SVGSVGElement,
  tooltip: HTMLDivElement,
  data: GraphResponse,
  onSelect: (n: GraphNode | null) => void,
  expandedRef: React.MutableRefObject<Set<string>>,
  nodeSelRef: React.MutableRefObject<d3.Selection<SVGGElement, SimNode, SVGGElement, unknown> | null>,
  activeIdRef: React.MutableRefObject<string | null>,
  highlightRef: React.MutableRefObject<((nodeId: string | null) => void) | null>,
  centerFnRef: React.MutableRefObject<((nodeId: string) => void) | null>,
  searchHighlightRef: React.MutableRefObject<((matchIds: Set<string> | null) => void) | null>,
): () => void {
  const { width, height } = svg.getBoundingClientRect();
  const root = d3.select(svg);
  root.selectAll("*").remove();

  const nodes: SimNode[] = data.nodes.map(({ x, y, ...rest }) => ({
    ...rest,
    x: x ?? undefined,
    y: y ?? undefined,
  }));
  const edges: (GraphEdge & { source: any; target: any })[] = data.edges.map(
    (e) => ({ ...e }),
  );

  // ── Defs ──
  const defs = root.append("defs");

  const usedTypes = [...new Set(nodes.map((n) => n.entity_type ?? "Custom"))];
  usedTypes.forEach((et) => {
    const color = entityColor(et);
    const s = gradientStops(color);
    const grad = defs.append("linearGradient")
      .attr("id", `grad-${et}`)
      .attr("x1", "0%").attr("y1", "0%")
      .attr("x2", "100%").attr("y2", "100%");
    grad.append("stop").attr("offset", "0%").attr("stop-color", s.start);
    grad.append("stop").attr("offset", "50%").attr("stop-color", s.mid);
    grad.append("stop").attr("offset", "100%").attr("stop-color", s.end);
  });

  const markerTypes = [...new Set(edges.map((e) => e.relationship_type ?? e.edge_type))];
  markerTypes.forEach((mt) => {
    defs.append("marker")
      .attr("id", `arrow-${mt}`)
      .attr("viewBox", "0 -4 8 8")
      .attr("refX", 8).attr("refY", 0)
      .attr("markerWidth", 5).attr("markerHeight", 5)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-4L8,0L0,4")
      .attr("fill", edgeStroke({ relationship_type: mt, edge_type: mt } as any));
  });

  const shadow = defs.append("filter").attr("id", "card-shadow")
    .attr("x", "-20%").attr("y", "-20%").attr("width", "140%").attr("height", "140%");
  shadow.append("feDropShadow")
    .attr("dx", "0").attr("dy", "2").attr("stdDeviation", "4")
    .attr("flood-color", "rgba(0,0,0,0.5)").attr("flood-opacity", "0.5");

  // ── Simulation ──
  const simulation = d3.forceSimulation(nodes)
    .force("link",
      d3.forceLink<SimNode, any>(edges)
        .id((d: any) => d.id)
        .distance((d: any) => Math.max(FORCE_CONFIG.linkDistance(d), 250)),
    )
    .force("charge", d3.forceManyBody().strength(-600))
    .force("center", d3.forceCenter(width / 2, height / 2).strength(FORCE_CONFIG.centerStrength))
    .force("collision", d3.forceCollide(CARD_W * 0.65))
    .alphaDecay(0.02); // slightly slower cool-down for smoother settle

  // ── Zoom ──
  const g = root.append("g");
  const zoomBehavior = d3.zoom<SVGSVGElement, unknown>()
    .scaleExtent([0.08, 4])
    .on("zoom", (e) => g.attr("transform", e.transform));
  root.call(zoomBehavior as any);

  // ── Center-on-node helper ──
  function centerOnNode(nodeId: string) {
    const target = nodes.find((n) => n.id === nodeId);
    if (!target || target.x == null || target.y == null) return;
    const scale = 1; // keep current-ish zoom, but ensure at least 1
    const tx = width / 2 - target.x * scale;
    const ty = height / 2 - target.y * scale;
    root.transition().duration(600).ease(d3.easeCubicInOut)
      .call(
        zoomBehavior.transform as any,
        d3.zoomIdentity.translate(tx, ty).scale(scale),
      );
  }
  centerFnRef.current = centerOnNode;

  // ── Edges ──
  const linkGroup = g.append("g").attr("class", "edges");
  const link = linkGroup.selectAll("line").data(edges).join("line")
    .attr("stroke", (d) => edgeStroke(d))
    .attr("stroke-width", (d) => edgeWidth(d))
    .attr("stroke-dasharray", (d) => edgeDash(d))
    .attr("opacity", (d) => edgeOpacity(d))
    .attr("marker-end", (d) => `url(#arrow-${d.relationship_type ?? d.edge_type})`);

  // ── Edge labels ──
  const edgeLabelGroup = g.append("g").attr("class", "edge-labels");
  const labeledEdges = edges.filter((e) => e.relationship_type && e.relationship_type !== "similarity");

  const edgeLabelBg = edgeLabelGroup.selectAll("rect").data(labeledEdges).join("rect")
    .attr("fill", "#09090b").attr("rx", 4).attr("ry", 4).attr("opacity", 0.85);

  const edgeLabel = edgeLabelGroup.selectAll("text").data(labeledEdges).join("text")
    .text((d) => d.relationship_type?.replace(/_/g, " ") ?? "")
    .attr("text-anchor", "middle")
    .attr("fill", (d) => edgeStroke(d))
    .attr("font-size", 9).attr("font-weight", 600).attr("opacity", 0.85).attr("dy", -5);

  // ── Hyperedge hulls with labels ──
  if (data.hyperedges && data.hyperedges.length > 0) {
    const hullGroup = g.insert("g", ":first-child").attr("class", "hyperedges");
    const hullLabelGroup = g.append("g").attr("class", "hull-labels");
    const hullColors = [
      "rgba(99,102,241,0.10)", "rgba(34,211,238,0.10)",
      "rgba(251,191,36,0.10)", "rgba(248,113,113,0.10)", "rgba(52,211,153,0.10)",
    ];
    const hullStrokeColors = [
      "rgba(99,102,241,0.35)", "rgba(34,211,238,0.35)",
      "rgba(251,191,36,0.35)", "rgba(248,113,113,0.35)", "rgba(52,211,153,0.35)",
    ];
    const hullTextColors = ["#818cf8", "#22d3ee", "#fbbf24", "#f87171", "#34d399"];
    const hulls = data.hyperedges.map((he, idx) => ({
      id: he.id, label: he.label, relType: he.relationship_type,
      memberIds: new Set(he.member_ids ?? []),
      color: hullColors[idx % hullColors.length],
      stroke: hullStrokeColors[idx % hullStrokeColors.length],
      textColor: hullTextColors[idx % hullTextColors.length],
    }));
    function updateHulls() {
      hullGroup.selectAll("path").remove();
      hullLabelGroup.selectAll("*").remove();
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
          return [(px + (dx / dist) * 50), (py + (dy / dist) * 50)] as [number, number];
        });
        hullGroup.append("path").datum(expanded)
          .attr("d", (dd) => `M${dd.map((p) => p.join(",")).join("L")}Z`)
          .attr("fill", h.color).attr("stroke", h.stroke)
          .attr("stroke-width", 1.5).attr("stroke-dasharray", "6 3");
        const topY = Math.min(...pts.map((p) => p[1])) - 60;
        const labelText = h.label || h.relType.replace(/_/g, " ");
        const tw = labelText.length * 5.5 + 16;
        hullLabelGroup.append("rect")
          .attr("x", cx - tw / 2).attr("y", topY - 8)
          .attr("width", tw).attr("height", 18).attr("rx", 9)
          .attr("fill", "#09090b").attr("stroke", h.stroke)
          .attr("stroke-width", 1).attr("opacity", 0.9);
        hullLabelGroup.append("text")
          .attr("x", cx).attr("y", topY + 5).attr("text-anchor", "middle")
          .attr("fill", h.textColor).attr("font-size", 10).attr("font-weight", 700)
          .text(labelText);
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

  // Expose to ref so React can access later
  nodeSelRef.current = node;

  // Background rect
  node.append("rect")
    .attr("class", "card-bg")
    .attr("x", -CARD_W / 2)
    .attr("y", -CARD_H_COLLAPSED / 2)
    .attr("width", CARD_W)
    .attr("height", CARD_H_COLLAPSED)
    .attr("rx", CARD_RX).attr("ry", CARD_RX)
    .attr("fill", (d) => `url(#grad-${d.entity_type ?? "Custom"})`)
    .attr("stroke", (d) => entityColor(d.entity_type) + "55")
    .attr("stroke-width", 1.2)
    .attr("filter", "url(#card-shadow)");

  // Accent bar
  node.append("rect")
    .attr("class", "card-accent")
    .attr("x", -CARD_W / 2)
    .attr("y", -CARD_H_COLLAPSED / 2)
    .attr("width", CARD_W).attr("height", 3)
    .attr("rx", CARD_RX)
    .attr("fill", (d) => entityColor(d.entity_type));

  // Card content foreignObject
  node.append("foreignObject")
    .attr("x", -CARD_W / 2 + 8)
    .attr("y", -CARD_H_COLLAPSED / 2 + 6)
    .attr("width", CARD_W - 16)
    .attr("height", CARD_H_COLLAPSED - 16)
    .append("xhtml:div")
    .style("font-family", "Inter, sans-serif")
    .style("overflow", "hidden")
    .style("height", "100%")
    .html((d: SimNode) => cardHtml(d, false));

  // ── Highlight helper (used by hover, click, and React panel navigation) ──
  function applyHighlight(focusId: string | null) {
    if (!focusId) {
      // Reset everything to default
      node.transition().duration(200).attr("opacity", 1);
      node.select("rect.card-bg").transition().duration(200)
        .attr("stroke-width", 1.2);
      link.transition().duration(200).attr("opacity", (dd: any) => edgeOpacity(dd));
      edgeLabel.transition().duration(200).attr("opacity", 0.85);
      edgeLabelBg.transition().duration(200).attr("opacity", 0.85);
      return;
    }
    const connectedIds = new Set<string>();
    edges.forEach((e) => {
      if (e.source.id === focusId) connectedIds.add(e.target.id);
      if (e.target.id === focusId) connectedIds.add(e.source.id);
    });
    node.transition().duration(150)
      .attr("opacity", (n: SimNode) => (n.id === focusId || connectedIds.has(n.id) ? 1 : 0.15));
    // Active node gets a bright glow ring
    node.select("rect.card-bg").transition().duration(150)
      .attr("stroke-width", (n: SimNode) => (n.id === focusId ? 2.5 : 1.2));
    link.transition().duration(150)
      .attr("opacity", (e: any) => (e.source.id === focusId || e.target.id === focusId ? 0.9 : 0.04));
    edgeLabel.transition().duration(150)
      .attr("opacity", (e: any) => (e.source.id === focusId || e.target.id === focusId ? 1 : 0.04));
    edgeLabelBg.transition().duration(150)
      .attr("opacity", (e: any) => (e.source.id === focusId || e.target.id === focusId ? 0.85 : 0.04));
  }

  // Expose highlight function so React detail panel can call it
  highlightRef.current = applyHighlight;

  // Expose search-highlight: dims everything except matched IDs (and their edges)
  searchHighlightRef.current = (matchIds: Set<string> | null) => {
    if (!matchIds) {
      // Clear search highlight — revert to active or default
      applyHighlight(activeIdRef.current);
      return;
    }
    node.transition().duration(200)
      .attr("opacity", (n: SimNode) => (matchIds.has(n.id) ? 1 : 0.1));
    node.select("rect.card-bg").transition().duration(200)
      .attr("stroke-width", (n: SimNode) => (matchIds.has(n.id) ? 2.5 : 1.2));
    link.transition().duration(200)
      .attr("opacity", (e: any) =>
        matchIds.has(e.source.id) || matchIds.has(e.target.id) ? 0.6 : 0.02,
      );
    edgeLabel.transition().duration(200)
      .attr("opacity", (e: any) =>
        matchIds.has(e.source.id) || matchIds.has(e.target.id) ? 0.85 : 0.02,
      );
    edgeLabelBg.transition().duration(200)
      .attr("opacity", (e: any) =>
        matchIds.has(e.source.id) || matchIds.has(e.target.id) ? 0.85 : 0.02,
      );
  };

  // ── Interactions ──
  node
    .on("mouseover", function (_event, d: SimNode) {
      // Temporarily highlight hovered node's connections
      applyHighlight(d.id);
    })
    .on("mouseout", function () {
      // On mouseout, revert to active-node highlight (or reset if none)
      applyHighlight(activeIdRef.current);
    })
    .on("click", function (event, d: SimNode) {
      event.stopPropagation();
      // Toggle expand/collapse in-place — no React re-render
      const expanded = expandedRef.current;
      const wasExpanded = expanded.has(d.id);
      if (wasExpanded) expanded.delete(d.id);
      else expanded.add(d.id);
      toggleCard(this, d, !wasExpanded);
      // Set as active and lock highlight
      activeIdRef.current = d.id;
      applyHighlight(d.id);
      // Smoothly pan so the clicked node is centered
      centerOnNode(d.id);
      // Update detail panel (React state, but doesn't trigger graph rebuild)
      onSelect(d as unknown as GraphNode);
    });

  root.on("click", () => {
    activeIdRef.current = null;
    applyHighlight(null);
    onSelect(null);
  });

  // ── Tick ──
  const halfW = CARD_W / 2;
  const halfH = CARD_H_COLLAPSED / 2;

  simulation.on("tick", () => {
    // Clip edges at card rect boundaries so they don't overlap cards
    link.each(function (d: any) {
      const sx = d.source.x as number, sy = d.source.y as number;
      const tx = d.target.x as number, ty = d.target.y as number;

      // Determine target card half-height (may be expanded)
      const tExpanded = expandedRef.current.has(d.target.id);
      const tHH = tExpanded ? CARD_H_EXPANDED / 2 : halfH;
      const sExpanded = expandedRef.current.has(d.source.id);
      const sHH = sExpanded ? CARD_H_EXPANDED / 2 : halfH;

      const [x1, y1] = rectEdgePoint(sx, sy, tx, ty, halfW, sHH);
      const [x2, y2] = rectEdgePoint(tx, ty, sx, sy, halfW, tHH);

      d3.select(this as SVGLineElement)
        .attr("x1", x1).attr("y1", y1)
        .attr("x2", x2).attr("y2", y2);
    });

    edgeLabel
      .attr("x", (d: any) => (d.source.x + d.target.x) / 2)
      .attr("y", (d: any) => (d.source.y + d.target.y) / 2);

    edgeLabelBg.each(function (d: any) {
      const mx = (d.source.x + d.target.x) / 2;
      const my = (d.source.y + d.target.y) / 2;
      const text = d.relationship_type?.replace(/_/g, " ") ?? "";
      const tw = text.length * 5.5 + 8;
      d3.select(this as SVGRectElement)
        .attr("x", mx - tw / 2).attr("y", my - 16)
        .attr("width", tw).attr("height", 14);
    });

    node.attr("transform", (d) => `translate(${d.x ?? 0},${d.y ?? 0})`);
  });

  return () => { simulation.stop(); };
}

// ═══════════════════════════════════════════════════════
//  Drag behaviour
// ═══════════════════════════════════════════════════════
function drag(simulation: d3.Simulation<SimNode, undefined>) {
  return d3.drag<SVGGElement, SimNode>()
    .on("start", (event, d) => {
      if (!event.active) simulation.alphaTarget(0.3).restart();
      d.fx = d.x; d.fy = d.y;
    })
    .on("drag", (event, d) => { d.fx = event.x; d.fy = event.y; })
    .on("end", (event, d) => {
      if (!event.active) simulation.alphaTarget(0);
      d.fx = null; d.fy = null;
    });
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/\n/g, "<br/>");
}

/**
 * Compute the point where a line from (cx,cy) toward (tx,ty) exits a
 * rectangle centred at (cx,cy) with half-width hw and half-height hh.
 * Returns the boundary intersection point plus a small outward pad.
 */
function rectEdgePoint(
  cx: number, cy: number,
  tx: number, ty: number,
  hw: number, hh: number,
  pad = 4,
): [number, number] {
  const dx = tx - cx;
  const dy = ty - cy;
  if (dx === 0 && dy === 0) return [cx, cy];

  // Time to hit vertical / horizontal walls
  const tX = dx !== 0 ? (hw + pad) / Math.abs(dx) : Infinity;
  const tY = dy !== 0 ? (hh + pad) / Math.abs(dy) : Infinity;
  const t = Math.min(tX, tY);
  return [cx + dx * t, cy + dy * t];
}
