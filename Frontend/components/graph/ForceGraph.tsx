"use client";

import { useEffect, useRef } from "react";
import * as d3 from "d3";
import type { GraphResponse, GraphNode, GraphEdge } from "@/lib/api-client";
import {
  FORCE_CONFIG,
  clusterColor,
  nodeRadius,
  edgeStroke,
  edgeWidth,
  edgeDash,
} from "@/lib/d3-config";

interface Props {
  data: GraphResponse;
}

interface SimNode extends Omit<GraphNode, "x" | "y">, d3.SimulationNodeDatum {
  cluster_id?: string | null;
}

/**
 * ForceGraph — D3 force-directed graph rendered into an SVG.
 *
 * Encapsulates all D3 logic; the parent only passes `GraphResponse`.
 */
export default function ForceGraph({ data }: Props) {
  const svgRef = useRef<SVGSVGElement>(null);

  useEffect(() => {
    if (!svgRef.current || !data.nodes.length) return;
    render(svgRef.current, data);
  }, [data]);

  return <svg ref={svgRef} className="w-full h-full" />;
}

// ═══════════════════════════════════════════════════════
//  D3 render (imperative — runs once per data change)
// ═══════════════════════════════════════════════════════

function render(svg: SVGSVGElement, data: GraphResponse) {
  const { width, height } = svg.getBoundingClientRect();
  const root = d3.select(svg);
  root.selectAll("*").remove();

  // Build cluster index for colouring
  const clusterIds = [...new Set(data.clusters.map((c) => c.id))];
  const clusterIndex = (id: string | null | undefined) =>
    id ? clusterIds.indexOf(id) : -1;

  // Clone data for D3 mutation
  const nodes: SimNode[] = data.nodes.map(({ x, y, ...rest }) => ({
    ...rest,
    x: x ?? undefined,
    y: y ?? undefined,
  }));
  const edges: GraphEdge[] = data.edges.map((e) => ({ ...e }));

  // ── Simulation ──
  const simulation = d3
    .forceSimulation(nodes)
    .force(
      "link",
      d3
        .forceLink<SimNode, any>(edges)
        .id((d: any) => d.id)
        .distance((d: any) => FORCE_CONFIG.linkDistance(d))
    )
    .force("charge", d3.forceManyBody().strength(FORCE_CONFIG.chargeStrength))
    .force("center", d3.forceCenter(width / 2, height / 2).strength(FORCE_CONFIG.centerStrength))
    .force("collision", d3.forceCollide(FORCE_CONFIG.collisionRadius));

  // ── Zoom ──
  const g = root.append("g");
  root.call(
    d3.zoom<SVGSVGElement, unknown>().scaleExtent([0.2, 5]).on("zoom", (e) => {
      g.attr("transform", e.transform);
    }) as any
  );

  // ── Edges ──
  const link = g
    .append("g")
    .selectAll("line")
    .data(edges)
    .join("line")
    .attr("stroke", (d) => edgeStroke(d))
    .attr("stroke-width", (d) => edgeWidth(d))
    .attr("stroke-dasharray", (d) => edgeDash(d))
    .attr("opacity", 0.6);

  // ── Nodes ──
  const node = g
    .append("g")
    .selectAll<SVGCircleElement, SimNode>("circle")
    .data(nodes)
    .join("circle")
    .attr("r", (d) => nodeRadius(d))
    .attr("fill", (d) =>
      d.type === "cluster"
        ? clusterColor(clusterIndex(d.id))
        : d.cluster_id
        ? clusterColor(clusterIndex(d.cluster_id))
        : "#475569"
    )
    .attr("stroke", "#fff")
    .attr("stroke-width", (d) => (d.type === "cluster" ? 2 : 0.5))
    .call(drag(simulation) as any);

  // ── Labels ──
  const label = g
    .append("g")
    .selectAll("text")
    .data(nodes.filter((n) => n.type === "cluster"))
    .join("text")
    .text((d) => d.label)
    .attr("text-anchor", "middle")
    .attr("dy", -32)
    .attr("fill", "#e2e8f0")
    .attr("font-size", 11)
    .attr("font-weight", 600);

  // ── Tooltip ──
  node.append("title").text((d) => d.label);

  // ── Tick ──
  simulation.on("tick", () => {
    link
      .attr("x1", (d: any) => d.source.x)
      .attr("y1", (d: any) => d.source.y)
      .attr("x2", (d: any) => d.target.x)
      .attr("y2", (d: any) => d.target.y);

    node.attr("cx", (d) => d.x ?? 0).attr("cy", (d) => d.y ?? 0);
    label.attr("x", (d) => d.x ?? 0).attr("y", (d) => d.y ?? 0);
  });
}

// ═══════════════════════════════════════════════════════
//  Drag behaviour
// ═══════════════════════════════════════════════════════

function drag(simulation: d3.Simulation<SimNode, undefined>) {
  return d3
    .drag<SVGCircleElement, SimNode>()
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
