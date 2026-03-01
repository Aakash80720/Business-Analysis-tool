"use client";

import { useState, useRef } from "react";
import apiClient from "@/lib/api-client";

interface Props {
  sessionId: string;
  onUploaded: () => void;
}

/**
 * DocumentUploader — drag-and-drop file upload with contextual chunking options.
 *
 * When "Smart Contextual Chunking" is enabled the backend runs the full
 * LangGraph pipeline:  semantic split → LLM context enrichment → Neo4j
 * graph context.  User notes provide additional domain context that gets
 * woven into every chunk for better retrieval.
 */
export default function DocumentUploader({ sessionId, onUploaded }: Props) {
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [contextual, setContextual] = useState(false);
  const [userNotes, setUserNotes] = useState("");
  const [uploadProgress, setUploadProgress] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFiles(files: FileList | null) {
    if (!files || files.length === 0) return;
    setUploading(true);
    try {
      const total = files.length;
      for (let i = 0; i < total; i++) {
        const file = files[i];
        setUploadProgress(`Uploading ${file.name} (${i + 1}/${total})…`);
        await apiClient.uploadDocument(sessionId, file, {
          userNotes: contextual ? userNotes : undefined,
          contextual,
        });
      }
      setUserNotes("");
      onUploaded();
    } catch (err: any) {
      alert(err.message ?? "Upload failed");
    } finally {
      setUploading(false);
      setUploadProgress(null);
    }
  }

  return (
    <div className="space-y-3">
      {/* ── Drop zone ── */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDragging(false);
          handleFiles(e.dataTransfer.files);
        }}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition ${
          dragging
            ? "border-primary bg-primary/10"
            : "border-white/10 hover:border-white/20"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept=".pdf,.docx,.csv,.xlsx,.xls,.txt"
          className="hidden"
          onChange={(e) => handleFiles(e.target.files)}
        />
        {uploading ? (
          <p className="text-sm text-[var(--text-muted)] animate-pulse">
            {uploadProgress ?? "Uploading…"}
          </p>
        ) : (
          <>
            <p className="text-sm font-medium">Drop files here</p>
            <p className="text-xs text-[var(--text-muted)] mt-1">
              PDF, DOCX, CSV, XLSX, TXT
            </p>
          </>
        )}
      </div>

      {/* ── Contextual chunking toggle ── */}
      <label className="flex items-center gap-2 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={contextual}
          onChange={(e) => setContextual(e.target.checked)}
          className="rounded border-white/20 bg-white/5 text-primary
                     focus:ring-primary/50 h-4 w-4"
        />
        <span className="text-xs font-medium">
          Smart Contextual Chunking
        </span>
        <span className="text-[10px] text-[var(--text-muted)]">
          (LangGraph + Neo4j)
        </span>
      </label>

      {/* ── User notes textarea (visible when contextual is on) ── */}
      {contextual && (
        <div className="space-y-1">
          <label className="text-xs text-[var(--text-muted)]">
            Document notes — provide context about this document for better
            chunking &amp; retrieval
          </label>
          <textarea
            value={userNotes}
            onChange={(e) => setUserNotes(e.target.value)}
            placeholder="e.g. This is a Q3 2025 financial report for Acme Corp. Focus on revenue projections and risk factors…"
            rows={3}
            className="w-full rounded-lg bg-white/5 border border-white/10
                       text-sm p-2 placeholder:text-white/30
                       focus:outline-none focus:border-primary/50
                       resize-none"
          />
        </div>
      )}
    </div>
  );
}
