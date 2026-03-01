"use client";

import type { SessionOut } from "@/lib/api-client";

interface Props {
  session: SessionOut;
  onEmbed: () => void;
  onCluster: (method: string) => void;
  onBack: () => void;
}

/**
 * SessionToolbar — header controls for embedding, clustering, navigation.
 */
export default function SessionToolbar({
  session,
  onEmbed,
  onCluster,
  onBack,
}: Props) {
  return (
    <header className="flex items-center gap-4 px-6 py-3 border-b border-white/10 bg-surface">
      <button
        onClick={onBack}
        className="text-[var(--text-muted)] hover:text-white transition text-sm"
      >
        ← Back
      </button>
      <h2 className="text-lg font-semibold truncate flex-1">{session.title}</h2>
      <span className="text-xs text-[var(--text-muted)]">
        {session.document_count} docs · {session.chunk_count} chunks ·{" "}
        {session.cluster_count} clusters
      </span>

      <button
        onClick={onEmbed}
        className="px-4 py-2 rounded-lg bg-accent/20 text-accent text-xs font-medium hover:bg-accent/30 transition"
      >
        Generate Embeddings
      </button>
      <button
        onClick={() => onCluster("kmeans")}
        className="px-4 py-2 rounded-lg bg-primary/20 text-primary text-xs font-medium hover:bg-primary/30 transition"
      >
        K-Means
      </button>
      <button
        onClick={() => onCluster("hierarchical")}
        className="px-4 py-2 rounded-lg bg-primary/20 text-primary text-xs font-medium hover:bg-primary/30 transition"
      >
        Hierarchical
      </button>
    </header>
  );
}
