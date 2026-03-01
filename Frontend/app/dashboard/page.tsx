"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Plus,
  FileText,
  Network,
  Trash2,
  LayoutGrid,
  ArrowRight,
  Loader2,
} from "lucide-react";
import apiClient, { type SessionOut } from "@/lib/api-client";

export default function DashboardPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionOut[]>([]);
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadSessions();
  }, []);

  async function loadSessions() {
    try {
      const res = await apiClient.listSessions();
      setSessions(res.sessions);
    } catch (err: any) {
      console.error("Failed to load sessions:", err);
      setSessions([]);
    } finally {
      setLoading(false);
    }
  }

  async function createSession() {
    if (!name.trim()) return;
    setCreating(true);
    setError(null);
    try {
      const session = await apiClient.createSession(name.trim());
      setName("");
      router.push(`/session/${session.id}`);
    } catch (err: any) {
      console.error("Failed to create session:", err);
      setError(err.message ?? "Failed to create session");
    } finally {
      setCreating(false);
    }
  }

  async function deleteSession(id: string) {
    try {
      await apiClient.deleteSession(id);
      loadSessions();
    } catch (err: any) {
      console.error("Failed to delete session:", err);
      setError(err.message ?? "Failed to delete session");
    }
  }

  return (
    <main className="flex-1 flex flex-col min-h-screen">
      {/* ── Top bar ── */}
      <header className="sticky top-0 z-30 glass border-b border-[var(--border)] px-6 py-3">
        <div className="max-w-6xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <span
              className="text-lg font-bold tracking-tight cursor-pointer"
              onClick={() => router.push("/")}
            >
              <span className="text-primary">Nexus</span>
            </span>
            <span className="text-[var(--text-muted)] text-sm">/</span>
            <span className="text-sm font-medium">Dashboard</span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => router.push("/workspace")}
              className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-[var(--text-secondary)] hover:text-white hover:bg-surface-light transition"
            >
              <LayoutGrid size={15} /> Workspace
            </button>
            <button
              onClick={() => {
                apiClient.clearToken();
                router.push("/");
              }}
              className="text-xs text-[var(--text-muted)] hover:text-white transition"
            >
              Sign Out
            </button>
          </div>
        </div>
      </header>

      <div className="flex-1 px-6 py-8 max-w-6xl mx-auto w-full space-y-8">
        {/* ── Create session ── */}
        <div className="flex gap-3">
          <div className="relative flex-1">
            <input
              placeholder="New analysis session…"
              value={name}
              onChange={(e) => setName(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && createSession()}
              className="w-full pl-4 pr-4 py-3 rounded-xl bg-surface border border-[var(--border)] focus:border-primary outline-none text-sm placeholder:text-[var(--text-muted)] transition"
            />
          </div>
          <button
            onClick={createSession}
            disabled={creating || !name.trim()}
            className="inline-flex items-center gap-2 px-5 py-3 rounded-xl bg-primary hover:bg-primary-hover text-white font-medium text-sm transition shadow-glow disabled:opacity-40"
          >
            {creating ? (
              <Loader2 size={16} className="animate-spin" />
            ) : (
              <Plus size={16} />
            )}
            Create
          </button>
        </div>

        {/* ── Error banner ── */}
        {error && (
          <div className="flex items-center justify-between gap-3 px-4 py-3 rounded-xl bg-danger/10 border border-danger/20 text-danger text-sm animate-in">
            <span>{error}</span>
            <button
              onClick={() => setError(null)}
              className="text-danger/60 hover:text-danger transition text-xs"
            >
              ✕
            </button>
          </div>
        )}

        {/* ── Session grid ── */}
        {loading ? (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="skeleton h-36 rounded-2xl" />
            ))}
          </div>
        ) : sessions.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 space-y-4 animate-in">
            <div className="w-16 h-16 rounded-2xl bg-surface-light flex items-center justify-center">
              <FileText size={28} className="text-[var(--text-muted)]" />
            </div>
            <p className="text-[var(--text-muted)] text-sm">
              No sessions yet. Create one above to start analysing.
            </p>
          </div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {sessions.map((s, i) => (
              <div
                key={s.id}
                onClick={() => router.push(`/session/${s.id}`)}
                className="glow-card group bg-surface rounded-2xl p-5 space-y-4 cursor-pointer transition animate-in"
                style={{ animationDelay: `${i * 50}ms` }}
              >
                {/* Title */}
                <div className="flex items-start justify-between">
                  <h3 className="font-semibold text-[15px] truncate pr-2 group-hover:text-primary transition">
                    {s.name}
                  </h3>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      deleteSession(s.id);
                    }}
                    className="p-1.5 rounded-lg opacity-0 group-hover:opacity-100 hover:bg-danger/10 text-[var(--text-muted)] hover:text-danger transition"
                    title="Delete session"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>

                {/* Stats */}
                <div className="flex items-center gap-3">
                  <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
                    <FileText size={13} />
                    <span>{s.document_count} docs</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-xs text-[var(--text-muted)]">
                    <Network size={13} />
                    <span>{s.entity_count} entities</span>
                  </div>
                </div>

                {/* Footer */}
                <div className="flex items-center justify-between pt-1 border-t border-[var(--border)]">
                  <span className="text-[11px] text-[var(--text-muted)]">
                    {new Date(s.updated_at).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    })}
                  </span>
                  <span className="flex items-center gap-1 text-xs text-primary opacity-0 group-hover:opacity-100 transition">
                    Open <ArrowRight size={12} />
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  );
}
