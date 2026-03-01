/**
 * Centralised API client — single point of contact with the FastAPI backend.
 *
 * Follows the Facade pattern: every component calls ApiClient methods
 * instead of raw fetch().
 */

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ═══════════════════════════════════════════════════════
//  Types
// ═══════════════════════════════════════════════════════

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  email: string;
}

export interface SessionOut {
  id: string;
  title: string;
  description: string;
  owner_id: string;
  document_count: number;
  chunk_count: number;
  cluster_count: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentOut {
  id: string;
  session_id: string;
  filename: string;
  file_type: string;
  page_count: number;
  chunk_count: number;
  created_at: string;
}

export interface EmbeddingResult {
  session_id: string;
  chunks_embedded: number;
  tokens_used: number;
  cost_usd: number;
}

export interface ClusterOut {
  id: string;
  label: string;
  summary: string;
  method: string;
  level: number;
  chunk_count: number;
  parent_id: string | null;
}

export interface GraphNode {
  id: string;
  label: string;
  type: "chunk" | "cluster";
  cluster_id?: string | null;
  metadata: Record<string, unknown>;
  x?: number | null;
  y?: number | null;
}

export interface GraphEdge {
  source: string;
  target: string;
  weight: number;
  edge_type: "similarity" | "hierarchy" | "bridge";
}

export interface GraphResponse {
  session_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  clusters: ClusterOut[];
}

export interface ChatResponse {
  reply: string;
  sources: Record<string, unknown>[];
  tokens_used: number;
  cost_usd: number;
}

export interface CostSummary {
  total_embedding_tokens: number;
  total_chat_tokens: number;
  total_embedding_cost: number;
  total_chat_cost: number;
  embedding_budget_remaining: number;
  chat_budget_remaining: number;
}

// ═══════════════════════════════════════════════════════
//  Client class
// ═══════════════════════════════════════════════════════

class ApiClient {
  private token: string | null = null;

  setToken(token: string) {
    this.token = token;
    if (typeof window !== "undefined") {
      localStorage.setItem("bat_token", token);
    }
  }

  loadToken(): string | null {
    if (!this.token && typeof window !== "undefined") {
      this.token = localStorage.getItem("bat_token");
    }
    return this.token;
  }

  clearToken() {
    this.token = null;
    if (typeof window !== "undefined") {
      localStorage.removeItem("bat_token");
    }
  }

  private async request<T>(
    path: string,
    options: RequestInit = {},
  ): Promise<T> {
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string> ?? {}),
    };

    const tk = this.loadToken();
    if (tk) headers["Authorization"] = `Bearer ${tk}`;

    // Don't set Content-Type for FormData (browser sets boundary)
    if (!(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }

    const res = await fetch(`${BASE_URL}${path}`, { ...options, headers });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(body.detail ?? `API error ${res.status}`);
    }
    if (res.status === 204) return {} as T;
    return res.json() as Promise<T>;
  }

  // ── Auth ──

  async register(email: string, password: string, fullName = "") {
    const data = await this.request<TokenResponse>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ email, password, full_name: fullName }),
    });
    this.setToken(data.access_token);
    return data;
  }

  async login(email: string, password: string) {
    const data = await this.request<TokenResponse>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    });
    this.setToken(data.access_token);
    return data;
  }

  // ── Sessions ──

  listSessions() {
    return this.request<{ sessions: SessionOut[] }>("/api/sessions");
  }

  createSession(title: string, description = "") {
    return this.request<SessionOut>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ title, description }),
    });
  }

  getSession(id: string) {
    return this.request<SessionOut>(`/api/sessions/${id}`);
  }

  deleteSession(id: string) {
    return this.request<void>(`/api/sessions/${id}`, { method: "DELETE" });
  }

  // ── Documents ──

  async uploadDocument(
    sessionId: string,
    file: File,
    options?: { userNotes?: string; contextual?: boolean },
  ) {
    const form = new FormData();
    form.append("session_id", sessionId);
    form.append("file", file);
    if (options?.userNotes) {
      form.append("user_notes", options.userNotes);
    }
    form.append("contextual", String(options?.contextual ?? false));
    return this.request<DocumentOut>("/api/documents/upload", {
      method: "POST",
      body: form,
    });
  }

  listDocuments(sessionId: string) {
    return this.request<{ documents: DocumentOut[] }>(`/api/documents/${sessionId}`);
  }

  // ── Embeddings ──

  generateEmbeddings(sessionId: string) {
    return this.request<EmbeddingResult>("/api/embeddings/generate", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
    });
  }

  // ── Graph ──

  getGraph(sessionId: string) {
    return this.request<GraphResponse>(`/api/graph/${sessionId}`);
  }

  clusterSession(sessionId: string, method = "kmeans", nClusters?: number) {
    return this.request<ClusterOut[]>("/api/graph/cluster", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        method,
        n_clusters: nClusters ?? null,
      }),
    });
  }

  getBridges(sessionIds: string[] = []) {
    const params = sessionIds.map((s) => `session_ids=${s}`).join("&");
    return this.request<{ edges: GraphEdge[]; session_ids: string[] }>(
      `/api/graph/bridges?${params}`,
    );
  }

  // ── Chat ──

  chat(sessionId: string, message: string, includeBridges = false) {
    return this.request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({
        session_id: sessionId,
        message,
        include_bridges: includeBridges,
      }),
    });
  }

  // ── Cost ──

  getCostUsage() {
    return this.request<CostSummary>("/api/cost/usage");
  }
}

// Singleton
const apiClient = new ApiClient();
export default apiClient;
