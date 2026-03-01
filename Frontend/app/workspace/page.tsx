"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ArrowLeft,
  Network,
  FileText,
  Link2,
  ArrowRight,
} from "lucide-react";
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
      setBridges(br.bridges);
    } catch {
      setSessions([]);
      setBridges([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="flex-1 flex flex-col min-h-screen">
      {/* ── Top bar ── */}
      <header className="sticky top-0 z-30 glass border-b border-[var(--border)] px-6 py-3">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push("/dashboard")}
              className="p-2 rounded-lg hover:bg-surface-light text-[var(--text-muted)] hover:text-white transition"
            >
              <ArrowLeft size={16} />
            </button>
            <span className="text-lg font-bold tracking-tight">
              <span className="text-primary">Nexus</span>
            </span>
            <span className="text-[var(--text-muted)] text-sm">/</span>
            <span className="text-sm font-medium">Workspace</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-[var(--text-muted)]">
            <Link2 size={14} className="text-primary" />
            {bridges.length} bridge connections
          </div>
        </div>
      </header>

      <div className="flex-1 px-6 py-8 max-w-6xl mx-auto w-full space-y-8">
        {/* ── Description ── */}
        <div className="space-y-1 animate-in">
          <h1 className="text-2xl font-bold">Unified Workspace</h1>
          <p className="text-sm text-[var(--text-muted)]">
            All your analysis sessions and cross-session semantic bridges in one
            view.
          </p>
        </div>

        {/* ── Sessions ── */}
        {loading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="skeleton h-28 rounded-2xl" />
            ))}
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {sessions.map((s, i) => (
              <div
                key={s.id}
                onClick={() => router.push(`/session/${s.id}`)}
                className="glow-card group bg-surface rounded-2xl p-5 space-y-3 cursor-pointer transition animate-in"
                style={{ animationDelay: `${i * 50}ms` }}
              >
                <div className="flex items-start justify-between">
                  <h3 className="font-semibold text-sm truncate pr-2 group-hover:text-primary transition">
                    {s.name}
                  </h3>
                  <ArrowRight
                    size={14}
                    className="text-primary opacity-0 group-hover:opacity-100 transition shrink-0 mt-0.5"
                  />
                </div>
                <div className="flex items-center gap-3">
                  <span className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
                    <FileText size={12} /> {s.document_count} docs
                  </span>
                  <span className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
                    <Network size={12} /> {s.entity_count} entities
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ── Bridges ── */}
        {bridges.length > 0 && (
          <section className="space-y-4 animate-in" style={{ animationDelay: "200ms" }}>
            <div className="flex items-center gap-2">
              <Link2 size={16} className="text-warning" />
              <h2 className="text-lg font-semibold">Bridge Connections</h2>
              <span className="ml-auto text-xs text-[var(--text-muted)]">
                {bridges.length} total
              </span>
            </div>
            <div className="bg-surface rounded-2xl border border-[var(--border)] divide-y divide-[var(--border)] max-h-72 overflow-y-auto">
              {bridges.map((b, i) => (
                <div
                  key={i}
                  className="flex items-center gap-4 px-4 py-3 text-sm hover:bg-surface-light transition"
                >
                  <span className="font-mono text-xs text-[var(--text-secondary)] truncate max-w-[140px]">
                    {b.source.slice(0, 8)}…
                  </span>
                  <span className="text-warning">⟷</span>
                  <span className="font-mono text-xs text-[var(--text-secondary)] truncate max-w-[140px]">
                    {b.target.slice(0, 8)}…
                  </span>
                  <span className="ml-auto text-xs font-medium text-accent tabular-nums">
                    {(b.weight * 100).toFixed(1)}%
                  </span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full bg-surface-light text-[var(--text-muted)]">
                    {b.relationship_type}
                  </span>
                </div>
              ))}
            </div>
          </section>
        )}
      </div>
    </main>
  );
}
