"use client";

import { useEffect, useState, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Network,
  MessageSquare,
  FileText,
  Sparkles,
  Loader2,
  Upload,
  Layers,
} from "lucide-react";
import apiClient, {
  type SessionOut,
  type GraphResponse,
  type DocumentOut,
} from "@/lib/api-client";
import ForceGraph from "@/components/graph/ForceGraph";
import ChatPanel from "@/components/chat/ChatPanel";
import DocumentUploader from "@/components/upload/DocumentUploader";

export default function SessionPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [session, setSession] = useState<SessionOut | null>(null);
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [documents, setDocuments] = useState<DocumentOut[]>([]);
  const [tab, setTab] = useState<"graph" | "chat">("graph");
  const [building, setBuilding] = useState(false);
  const [embedding, setEmbedding] = useState(false);

  const load = useCallback(async () => {
    try {
      const [s, d] = await Promise.all([
        apiClient.getSession(id),
        apiClient.listDocuments(id),
      ]);
      setSession(s);
      setDocuments(d.documents);
      if (s.entity_count > 0) {
        const g = await apiClient.getGraph(id);
        setGraph(g);
      }
    } catch {
      router.push("/dashboard");
    }
  }, [id, router]);

  useEffect(() => {
    if (id) load();
  }, [id, load]);

  async function handleEmbed() {
    setEmbedding(true);
    try {
      await apiClient.generateEmbeddings(id);
      await load();
    } finally {
      setEmbedding(false);
    }
  }

  async function handleBuildGraph() {
    setBuilding(true);
    try {
      await apiClient.buildGraph(id);
      await load();
    } finally {
      setBuilding(false);
    }
  }

  /* ── Skeleton loader ── */
  if (!session) {
    return (
      <main className="flex-1 flex flex-col h-screen">
        <div className="glass border-b border-[var(--border)] px-6 py-3">
          <div className="skeleton h-5 w-48 rounded" />
        </div>
        <div className="flex-1 flex items-center justify-center">
          <Loader2 className="animate-spin text-primary" size={28} />
        </div>
      </main>
    );
  }

  const tabs = [
    { key: "graph" as const, label: "Knowledge Graph", icon: Network },
    { key: "chat" as const, label: "Chat", icon: MessageSquare },
  ];

  return (
    <main className="flex-1 flex flex-col h-screen overflow-hidden">
      {/* ── Top bar ── */}
      <header className="glass border-b border-[var(--border)] px-6 py-2.5 flex items-center gap-3 shrink-0">
        <button
          onClick={() => router.push("/dashboard")}
          className="p-2 rounded-lg hover:bg-surface-light text-[var(--text-muted)] hover:text-white transition"
        >
          <ArrowLeft size={16} />
        </button>

        <div className="flex items-center gap-2 min-w-0">
          <span className="text-lg font-bold text-primary">Nexus</span>
          <span className="text-[var(--text-muted)] text-sm">/</span>
          <span className="text-sm font-medium truncate">{session.name}</span>
        </div>

        {/* Stats pills */}
        <div className="ml-auto flex items-center gap-3">
          <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface text-xs text-[var(--text-muted)]">
            <FileText size={12} /> {documents.length} docs
          </span>
          <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-surface text-xs text-[var(--text-muted)]">
            <Layers size={12} /> {session.entity_count} entities
          </span>
        </div>
      </header>

      {/* ── Tab bar + actions ── */}
      <div className="flex items-center border-b border-[var(--border)] px-6 shrink-0">
        <div className="flex">
          {tabs.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`flex items-center gap-2 px-4 py-2.5 text-sm font-medium border-b-2 transition ${
                tab === t.key
                  ? "border-primary text-white"
                  : "border-transparent text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              }`}
            >
              <t.icon size={14} />
              {t.label}
            </button>
          ))}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <button
            onClick={handleEmbed}
            disabled={embedding || documents.length === 0}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-surface hover:bg-surface-light border border-[var(--border)] text-[var(--text-secondary)] hover:text-white disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            {embedding ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Upload size={12} />
            )}
            Embeddings
          </button>
          <button
            onClick={handleBuildGraph}
            disabled={building || session.entity_count === 0}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-primary/20 hover:bg-primary/30 text-primary border border-primary/30 disabled:opacity-40 disabled:cursor-not-allowed transition"
          >
            {building ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Sparkles size={12} />
            )}
            Build Graph
          </button>
        </div>
      </div>

      {/* ── Content area ── */}
      <div className="flex-1 flex overflow-hidden">
        {/* Main panel */}
        <div className="flex-1 relative">
          {tab === "graph" ? (
            graph && graph.nodes.length > 0 ? (
              <ForceGraph data={graph} />
            ) : (
              <div className="flex flex-col items-center justify-center h-full gap-4 text-[var(--text-muted)]">
                <Network size={48} className="opacity-30" />
                <p className="text-sm max-w-xs text-center">
                  Upload documents, generate embeddings, then build the knowledge
                  graph to visualise entities and relationships.
                </p>
              </div>
            )
          ) : (
            <ChatPanel sessionId={id} />
          )}
        </div>

        {/* ── Right sidebar ── */}
        <aside className="w-80 border-l border-[var(--border)] flex flex-col overflow-hidden shrink-0">
          <div className="p-4 shrink-0">
            <DocumentUploader sessionId={id} onUploaded={load} />
          </div>
          <div className="px-4 pb-2 shrink-0">
            <h3 className="text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider">
              Documents ({documents.length})
            </h3>
          </div>
          <ul className="flex-1 overflow-y-auto px-4 pb-4 space-y-2">
            {documents.map((d) => (
              <li
                key={d.id}
                className="bg-surface rounded-xl px-3 py-2.5 text-sm border border-[var(--border)] hover:border-primary/30 transition"
              >
                <p className="truncate font-medium text-[var(--text-secondary)]">
                  {d.filename}
                </p>
                <p className="text-xs text-[var(--text-muted)] mt-0.5">
                  {d.page_count} pages · {d.entity_count} entities
                </p>
              </li>
            ))}
            {documents.length === 0 && (
              <li className="text-xs text-[var(--text-muted)] text-center py-6">
                No documents yet. Upload a PDF to get started.
              </li>
            )}
          </ul>
        </aside>
      </div>
    </main>
  );
}
