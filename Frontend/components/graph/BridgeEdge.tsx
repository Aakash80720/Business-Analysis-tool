"use client";

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
    <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
      <span className="truncate max-w-[120px]">{sourceLabel}</span>
      <span className="text-accent-warm">⟷</span>
      <span className="truncate max-w-[120px]">{targetLabel}</span>
      <span className="ml-auto text-accent font-mono">
        {(weight * 100).toFixed(0)}%
      </span>
    </div>
  );
}
