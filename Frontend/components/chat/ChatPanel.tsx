"use client";

import { useState, useRef, useEffect } from "react";
import { Send, MessageSquare, Bot, User } from "lucide-react";
import apiClient, { type ChatResponse } from "@/lib/api-client";

interface Message {
  role: "user" | "assistant";
  content: string;
}

interface Props {
  sessionId: string;
}

/**
 * ChatPanel — RAG-powered conversational interface with markdown rendering.
 */
export default function ChatPanel({ sessionId }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

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
      inputRef.current?.focus();
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-6 space-y-5">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-[var(--text-muted)]">
            <MessageSquare size={40} className="opacity-30" />
            <p className="text-sm text-center max-w-xs">
              Ask questions about your uploaded documents. Answers are grounded
              in your knowledge graph.
            </p>
          </div>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`flex gap-3 animate-in ${
              m.role === "user" ? "flex-row-reverse" : ""
            }`}
            style={{ animationDelay: "50ms" }}
          >
            {/* Avatar */}
            <div
              className={`shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs ${
                m.role === "user"
                  ? "bg-primary/20 text-primary"
                  : "bg-surface-light text-[var(--text-muted)]"
              }`}
            >
              {m.role === "user" ? <User size={14} /> : <Bot size={14} />}
            </div>
            {/* Bubble */}
            <div
              className={`max-w-[75%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                m.role === "user"
                  ? "bg-primary text-white"
                  : "bg-surface border border-[var(--border)] chat-prose"
              }`}
            >
              {m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex gap-3 animate-in">
            <div className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center bg-surface-light text-[var(--text-muted)]">
              <Bot size={14} />
            </div>
            <div className="bg-surface border border-[var(--border)] rounded-2xl px-4 py-3 flex items-center gap-2">
              <span className="pulse-dot" />
              <span className="pulse-dot" style={{ animationDelay: "0.2s" }} />
              <span className="pulse-dot" style={{ animationDelay: "0.4s" }} />
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      {/* Input */}
      <div className="border-t border-[var(--border)] p-4">
        <div className="flex gap-2 items-center bg-surface rounded-xl border border-[var(--border)] focus-within:border-primary/50 transition px-3">
          <input
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
            placeholder="Ask about your business documents…"
            className="flex-1 py-3 bg-transparent outline-none text-sm placeholder:text-[var(--text-muted)]"
          />
          <button
            onClick={send}
            disabled={loading || !input.trim()}
            className="p-2 rounded-lg text-primary hover:bg-primary/10 disabled:opacity-30 disabled:cursor-not-allowed transition"
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
