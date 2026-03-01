"use client";

/**
 * EntityBadge — a visual pill displaying an entity type with colour coding.
 * (Renamed from ClusterBubble — clusters no longer exist in the schema.)
 */
export default function EntityBadge({
  label,
  color,
  count,
}: {
  label: string;
  color: string;
  count?: number;
}) {
  return (
    <div
      className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs font-medium"
      style={{ backgroundColor: `${color}22`, color, border: `1px solid ${color}33` }}
    >
      <span
        className="w-2 h-2 rounded-full shrink-0"
        style={{ backgroundColor: color }}
      />
      {label}{count != null ? ` (${count})` : ""}
    </div>
  );
}
