"use client";

import { Link2 } from "lucide-react";

/**
 * BridgeEdge — renders a visual indicator for cross-session connections.
 */
export default function BridgeEdge({
  sourceLabel,
  targetLabel,
  weight,
}: {
  sourceLabel: string;
  targetLabel: string;
  weight: number;
}) {
  return (
    <div className="flex items-center gap-2 text-xs px-3 py-2 rounded-lg hover:bg-surface-light transition">
      <span className="text-[var(--text-secondary)] truncate max-w-[120px]">
        {sourceLabel}
      </span>
      <Link2 size={10} className="text-warning shrink-0" />
      <span className="text-[var(--text-secondary)] truncate max-w-[120px]">
        {targetLabel}
      </span>
      <span className="ml-auto text-warning font-mono font-medium tabular-nums">
        {(weight * 100).toFixed(0)}%
      </span>
    </div>
  );
}
