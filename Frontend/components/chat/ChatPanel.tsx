"use client";

import { useState, useRef } from "react";
import apiClient, { type ChatResponse } from "@/lib/api-client";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface Props {
  sessionId: string;
}

/**
 * ChatPanel — RAG-powered conversational interface.
 */
export default function ChatPanel({ sessionId }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  async function send() {
    if (!input.trim() || loading) return;
    const userMsg: Message = { role: "user", content: input };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res: ChatResponse = await apiClient.chat(sessionId, userMsg.content);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.reply },
      ]);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${err.message}` },
      ]);
    } finally {
      setLoading(false);
      bottomRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <p className="text-center text-[var(--text-muted)] mt-20">
            Ask questions about your uploaded documents.
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
              m.role === "user"
                ? "ml-auto bg-primary text-white"
                : "mr-auto bg-surface-light"
            }`}
          >
            {m.content}
          </div>
        ))}
        {loading && (
          <div className="mr-auto bg-surface-light rounded-2xl px-4 py-3 text-sm text-[var(--text-muted)] animate-pulse">
            Thinking…
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-white/10 p-4 flex gap-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask about your business documents…"
          className="flex-1 px-4 py-3 rounded-xl bg-surface border border-white/10 focus:border-primary outline-none text-sm"
        />
        <button
          onClick={send}
          disabled={loading}
          className="px-5 py-3 rounded-xl bg-primary hover:bg-primary-dark text-white font-medium text-sm transition disabled:opacity-50"
        >
          Send
        </button>
      </div>
    </div>
  );
}
