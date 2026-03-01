import Link from "next/link";

export default function HomePage() {
  return (
    <main className="flex-1 flex items-center justify-center">
      <div className="text-center space-y-6 max-w-xl px-6">
        <h1 className="text-5xl font-bold bg-gradient-to-r from-primary to-accent bg-clip-text text-transparent">
          Business Analysis Tool
        </h1>
        <p className="text-lg text-[var(--text-muted)]">
          Upload documents, embed knowledge with OpenAI, cluster strategic
          insights, and explore interactive knowledge graphs.
        </p>
        <div className="flex gap-4 justify-center">
          <Link
            href="/dashboard"
            className="px-6 py-3 rounded-xl bg-primary hover:bg-primary-dark text-white font-medium transition"
          >
            Get Started
          </Link>
        </div>
      </div>
    </main>
  );
}
