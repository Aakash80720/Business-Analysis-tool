"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import apiClient, {
  type SessionOut,
  type GraphResponse,
  type DocumentOut,
} from "@/lib/api-client";
import ForceGraph from "@/components/graph/ForceGraph";
import ChatPanel from "@/components/chat/ChatPanel";
import DocumentUploader from "@/components/upload/DocumentUploader";
import SessionToolbar from "@/components/session/SessionToolbar";

export default function SessionPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const [session, setSession] = useState<SessionOut | null>(null);
  const [graph, setGraph] = useState<GraphResponse | null>(null);
  const [documents, setDocuments] = useState<DocumentOut[]>([]);
  const [tab, setTab] = useState<"graph" | "chat">("graph");

  useEffect(() => {
    if (id) load();
  }, [id]);

  async function load() {
    try {
      const [s, d] = await Promise.all([
        apiClient.getSession(id),
        apiClient.listDocuments(id),
      ]);
      setSession(s);
      setDocuments(d.documents);
      if (s.chunk_count > 0) {
        const g = await apiClient.getGraph(id);
        setGraph(g);
      }
    } catch {
      router.push("/dashboard");
    }
  }

  async function handleEmbed() {
    await apiClient.generateEmbeddings(id);
    await load();
  }

  async function handleCluster(method: string) {
    await apiClient.clusterSession(id, method);
    await load();
  }

  if (!session) {
    return (
      <main className="flex-1 flex items-center justify-center">
        <p className="text-[var(--text-muted)]">Loading session…</p>
      </main>
    );
  }

  return (
    <main className="flex-1 flex flex-col h-screen overflow-hidden">
      {/* Toolbar */}
      <SessionToolbar
        session={session}
        onEmbed={handleEmbed}
        onCluster={handleCluster}
        onBack={() => router.push("/dashboard")}
      />

      {/* Tab bar */}
      <div className="flex border-b border-white/10 px-6">
        <button
          onClick={() => setTab("graph")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition ${
            tab === "graph"
              ? "border-primary text-white"
              : "border-transparent text-[var(--text-muted)]"
          }`}
        >
          Knowledge Graph
        </button>
        <button
          onClick={() => setTab("chat")}
          className={`px-4 py-2 text-sm font-medium border-b-2 transition ${
            tab === "chat"
              ? "border-primary text-white"
              : "border-transparent text-[var(--text-muted)]"
          }`}
        >
          Chat
        </button>
      </div>

      {/* Content */}
      <div className="flex-1 flex overflow-hidden">
        {/* Main panel */}
        <div className="flex-1 relative">
          {tab === "graph" ? (
            graph && graph.nodes.length > 0 ? (
              <ForceGraph data={graph} />
            ) : (
              <div className="flex items-center justify-center h-full text-[var(--text-muted)]">
                Upload documents & generate embeddings to see the graph.
              </div>
            )
          ) : (
            <ChatPanel sessionId={id} />
          )}
        </div>

        {/* Sidebar: upload */}
        <aside className="w-80 border-l border-white/10 p-4 space-y-4 overflow-y-auto">
          <DocumentUploader sessionId={id} onUploaded={load} />

          <h3 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wider">
            Documents ({documents.length})
          </h3>
          <ul className="space-y-2">
            {documents.map((d) => (
              <li
                key={d.id}
                className="bg-surface-light rounded-lg px-3 py-2 text-sm"
              >
                <p className="truncate font-medium">{d.filename}</p>
                <p className="text-xs text-[var(--text-muted)]">
                  {d.page_count} pages · {d.chunk_count} chunks
                </p>
              </li>
            ))}
          </ul>
        </aside>
      </div>
    </main>
  );
}
