"use client";

import { ArrowLeft, Upload, Sparkles, FileText, Layers } from "lucide-react";
import type { SessionOut } from "@/lib/api-client";

interface Props {
  session: SessionOut;
  onEmbed: () => void;
  onBuildGraph: () => void;
  onBack: () => void;
}

/**
 * SessionToolbar — header controls for embedding, graph building, navigation.
 */
export default function SessionToolbar({
  session,
  onEmbed,
  onBuildGraph,
  onBack,
}: Props) {
  return (
    <header className="glass flex items-center gap-4 px-6 py-2.5 border-b border-[var(--border)] shrink-0">
      <button
        onClick={onBack}
        className="p-2 rounded-lg hover:bg-surface-light text-[var(--text-muted)] hover:text-white transition"
      >
        <ArrowLeft size={16} />
      </button>
      <h2 className="text-sm font-semibold truncate flex-1">{session.name}</h2>
      <span className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
        <FileText size={12} /> {session.document_count} docs
      </span>
      <span className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
        <Layers size={12} /> {session.entity_count} entities
      </span>

      <button
        onClick={onEmbed}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-surface hover:bg-surface-light border border-[var(--border)] text-[var(--text-secondary)] hover:text-white transition"
      >
        <Upload size={12} /> Embeddings
      </button>
      <button
        onClick={onBuildGraph}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-primary/20 hover:bg-primary/30 text-primary border border-primary/30 transition"
      >
        <Sparkles size={12} /> Build Graph
      </button>
    </header>
  );
}
