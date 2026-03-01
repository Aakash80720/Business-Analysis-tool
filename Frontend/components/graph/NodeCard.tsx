"use client";

import type { GraphNode } from "@/lib/api-client";

interface Props {
  node: GraphNode;
  onClose: () => void;
}

/**
 * NodeCard — detail overlay when a graph node is selected.
 */
export default function NodeCard({ node, onClose }: Props) {
  return (
    <div className="absolute top-4 right-4 w-72 bg-surface rounded-2xl p-4 shadow-2xl border border-white/10 space-y-2 z-50">
      <div className="flex items-center justify-between">
        <span className="text-xs uppercase tracking-wider text-[var(--text-muted)]">
          {node.type}
        </span>
        <button onClick={onClose} className="text-[var(--text-muted)] hover:text-white">
          ✕
        </button>
      </div>
      <h4 className="font-semibold text-sm leading-snug">{node.label}</h4>
      {node.cluster_id && (
        <p className="text-xs text-[var(--text-muted)]">
          Cluster: {node.cluster_id.slice(0, 8)}
        </p>
      )}
      <pre className="text-xs bg-surface-light rounded-lg p-2 max-h-40 overflow-y-auto whitespace-pre-wrap">
        {JSON.stringify(node.metadata, null, 2)}
      </pre>
    </div>
  );
}
