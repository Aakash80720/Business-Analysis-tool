"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import apiClient, { type SessionOut, type GraphEdge } from "@/lib/api-client";

export default function WorkspacePage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionOut[]>([]);
  const [bridges, setBridges] = useState<GraphEdge[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadAll();
  }, []);

  async function loadAll() {
    try {
      const res = await apiClient.listSessions();
      setSessions(res.sessions);
      const br = await apiClient.getBridges();
      setBridges(br.edges);
    } catch {
      setSessions([]);
      setBridges([]);
    } finally {
      setLoading(false);
    }
  }

  if (loading) {
    return (
      <main className="flex-1 flex items-center justify-center">
        <p className="text-[var(--text-muted)]">Loading workspace…</p>
      </main>
    );
  }

  return (
    <main className="flex-1 p-6 max-w-6xl mx-auto w-full space-y-8">
      <h1 className="text-3xl font-bold">Workspace</h1>
      <p className="text-[var(--text-muted)]">
        Unified view across all sessions with {bridges.length} cross-session
        bridge connections.
      </p>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {sessions.map((s) => (
          <div
            key={s.id}
            onClick={() => router.push(`/session/${s.id}`)}
            className="bg-surface rounded-2xl p-5 space-y-2 border border-white/5 hover:border-accent/40 transition cursor-pointer"
          >
            <h3 className="font-semibold truncate">{s.title}</h3>
            <div className="flex gap-3 text-xs text-[var(--text-muted)]">
              <span>{s.document_count} docs</span>
              <span>{s.chunk_count} chunks</span>
              <span>{s.cluster_count} clusters</span>
            </div>
          </div>
        ))}
      </div>

      {bridges.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-xl font-semibold">Bridge Connections</h2>
          <div className="bg-surface rounded-xl p-4 max-h-64 overflow-y-auto text-sm space-y-1">
            {bridges.map((b, i) => (
              <div key={i} className="flex gap-4 text-[var(--text-muted)]">
                <span className="font-mono">{b.source.slice(0, 8)}</span>
                <span>↔</span>
                <span className="font-mono">{b.target.slice(0, 8)}</span>
                <span className="text-accent">{(b.weight * 100).toFixed(1)}%</span>
              </div>
            ))}
          </div>
        </section>
      )}
    </main>
  );
}
