"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import apiClient, { type SessionOut } from "@/lib/api-client";

export default function DashboardPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionOut[]>([]);
  const [title, setTitle] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadSessions();
  }, []);

  async function loadSessions() {
    try {
      const res = await apiClient.listSessions();
      setSessions(res.sessions);
    } catch {
      // In dev mode auth is bypassed — just show empty state
      setSessions([]);
    } finally {
      setLoading(false);
    }
  }

  async function createSession() {
    if (!title.trim()) return;
    await apiClient.createSession(title);
    setTitle("");
    loadSessions();
  }

  async function deleteSession(id: string) {
    await apiClient.deleteSession(id);
    loadSessions();
  }

  if (loading) {
    return (
      <main className="flex-1 flex items-center justify-center">
        <p className="text-[var(--text-muted)]">Loading…</p>
      </main>
    );
  }

  return (
    <main className="flex-1 p-6 max-w-5xl mx-auto w-full space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <button
          onClick={() => {
            apiClient.clearToken();
            router.push("/");
          }}
          className="text-sm text-[var(--text-muted)] hover:text-white transition"
        >
          Home
        </button>
      </div>

      {/* Create session */}
      <div className="flex gap-3">
        <input
          placeholder="New session title…"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && createSession()}
          className="flex-1 px-4 py-3 rounded-xl bg-surface border border-white/10 focus:border-primary outline-none"
        />
        <button
          onClick={createSession}
          className="px-6 py-3 rounded-xl bg-primary hover:bg-primary-dark text-white font-medium transition"
        >
          Create
        </button>
      </div>

      {/* Session list */}
      {sessions.length === 0 ? (
        <p className="text-[var(--text-muted)]">
          No sessions yet. Create one above to get started.
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {sessions.map((s) => (
            <div
              key={s.id}
              className="bg-surface rounded-2xl p-5 space-y-3 border border-white/5 hover:border-primary/40 transition cursor-pointer"
              onClick={() => router.push(`/session/${s.id}`)}
            >
              <h3 className="font-semibold text-lg truncate">{s.title}</h3>
              <div className="flex gap-4 text-xs text-[var(--text-muted)]">
                <span>{s.document_count} docs</span>
                <span>{s.chunk_count} chunks</span>
                <span>{s.cluster_count} clusters</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-xs text-[var(--text-muted)]">
                  {new Date(s.updated_at).toLocaleDateString()}
                </span>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteSession(s.id);
                  }}
                  className="text-xs text-red-400 hover:text-red-300"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </main>
  );
}
