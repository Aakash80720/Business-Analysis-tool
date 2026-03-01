import Link from "next/link";
import {
  ArrowRight,
  Network,
  MessageSquare,
  Upload,
  Sparkles,
} from "lucide-react";

const features = [
  {
    icon: Upload,
    title: "Smart Document Ingestion",
    desc: "Upload PDFs, DOCX, CSVs — contextual chunking with LangGraph extracts business entities automatically.",
  },
  {
    icon: Network,
    title: "Knowledge Graph",
    desc: "LLM-extracted labeled relationships and hyperedges connecting Goals, KPIs, Risks, and Actions.",
  },
  {
    icon: MessageSquare,
    title: "RAG-Powered Chat",
    desc: "Ask questions grounded in your documents — vector retrieval + graph context for rich answers.",
  },
  {
    icon: Sparkles,
    title: "Cross-Session Bridges",
    desc: "Discover hidden connections across projects with automatic semantic bridge detection.",
  },
];

export default function HomePage() {
  return (
    <main className="flex-1 flex flex-col">
      {/* ── Nav ── */}
      <nav className="flex items-center justify-between px-6 py-4 max-w-7xl mx-auto w-full">
        <span className="text-lg font-bold tracking-tight">
          <span className="text-primary">Nexus</span>
        </span>
        <div className="flex items-center gap-3">
          <Link
            href="/login"
            className="px-4 py-2 text-sm text-[var(--text-secondary)] hover:text-white transition"
          >
            Sign in
          </Link>
          <Link
            href="/dashboard"
            className="px-4 py-2 rounded-lg bg-primary hover:bg-primary-hover text-white text-sm font-medium transition shadow-glow"
          >
            Get Started
          </Link>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="flex-1 flex items-center justify-center px-6 py-20">
        <div className="text-center space-y-8 max-w-3xl animate-in">
          {/* Badge */}
          <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-primary-muted text-primary text-xs font-medium">
            <Sparkles size={14} />
            Powered by LangGraph + Neo4j
          </div>

          <h1 className="text-5xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight leading-[1.1]">
            Turn documents into
            <br />
            <span className="bg-gradient-to-r from-primary via-accent to-primary bg-clip-text text-transparent">
              strategic insight
            </span>
          </h1>

          <p className="text-lg sm:text-xl text-[var(--text-secondary)] max-w-2xl mx-auto leading-relaxed">
            Upload business documents, extract entities with AI, explore
            contextual knowledge graphs, and chat with your data — all in
            one intelligent workspace.
          </p>

          <div className="flex items-center gap-4 justify-center pt-2">
            <Link
              href="/dashboard"
              className="group inline-flex items-center gap-2 px-6 py-3.5 rounded-xl bg-primary hover:bg-primary-hover text-white font-semibold transition shadow-glow"
            >
              Open Dashboard
              <ArrowRight
                size={16}
                className="group-hover:translate-x-0.5 transition-transform"
              />
            </Link>
            <Link
              href="/workspace"
              className="px-6 py-3.5 rounded-xl border border-[var(--border)] hover:border-[var(--border-hover)] text-sm font-medium transition"
            >
              View Workspace
            </Link>
          </div>
        </div>
      </section>

      {/* ── Features grid ── */}
      <section className="px-6 pb-24 max-w-6xl mx-auto w-full">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((f, i) => (
            <div
              key={f.title}
              className="glow-card bg-surface rounded-2xl p-6 space-y-3 animate-in"
              style={{ animationDelay: `${i * 80}ms` }}
            >
              <div className="w-10 h-10 rounded-xl bg-primary-muted flex items-center justify-center">
                <f.icon size={20} className="text-primary" />
              </div>
              <h3 className="font-semibold">{f.title}</h3>
              <p className="text-sm text-[var(--text-muted)] leading-relaxed">
                {f.desc}
              </p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Footer ── */}
      <footer className="border-t border-[var(--border)] py-6 text-center text-xs text-[var(--text-muted)]">
        Nexus — Business Knowledge Graph Platform
      </footer>
    </main>
  );
}
