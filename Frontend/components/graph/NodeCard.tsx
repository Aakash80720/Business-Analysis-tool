"use client";

import type { GraphNode } from "@/lib/api-client";
import { entityColor } from "@/lib/d3-config";

interface Props {
  node: GraphNode;
  onClose: () => void;
}

/**
 * NodeCard — detail overlay when a graph node is selected.
 */
export default function NodeCard({ node, onClose }: Props) {
  const color = entityColor(node.entity_type);

  return (
    <div className="absolute top-4 right-4 w-72 bg-surface/95 backdrop-blur-sm rounded-2xl p-4 shadow-lg border border-[var(--border)] space-y-3 z-50 animate-in">
      <div className="flex items-start justify-between">
        <div className="space-y-1 min-w-0">
          <h4 className="font-semibold text-sm text-white truncate">
            {node.label}
          </h4>
          <span
            className="inline-block text-[10px] font-medium px-2 py-0.5 rounded-full"
            style={{ background: color + "22", color }}
          >
            {node.entity_type ?? "Custom"}
          </span>
        </div>
        <button
          onClick={onClose}
          className="text-[var(--text-muted)] hover:text-white transition text-sm leading-none p-1"
        >
          ✕
        </button>
      </div>
      {node.metadata && Object.keys(node.metadata).length > 0 && (
        <div className="space-y-1 border-t border-[var(--border)] pt-2">
          {Object.entries(node.metadata).map(([k, v]) => (
            <div key={k} className="flex gap-2 text-[11px]">
              <span className="text-[var(--text-muted)] shrink-0">{k}:</span>
              <span className="text-[var(--text-secondary)] truncate">
                {String(v)}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
