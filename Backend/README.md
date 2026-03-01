# 📊 Business Analysis Tool

> **Embedding + Contextual Graph-based Knowledge Platform**
> Cluster business points, embed real documents with OpenAI, and explore strategic insights through interactive knowledge graphs.

---

## ✨ Features

| Layer | Capability |
|-------|-----------|
| **Document Ingestion** | Upload PDF, DOCX, CSV — auto-parsed and chunked |
| **Smart Embedding** | OpenAI `text-embedding-3-small` vectors stored in pgvector |
| **Clustering** | K-Means + Hierarchical clustering of business points |
| **Knowledge Graph** | NetworkX graph → D3.js force-directed visualization |
| **Cross-Session Bridges** | Cosine-similarity links between sessions |
| **RAG Chat** | GPT-4o answers grounded in your embedded documents |
| **Cost Tracking** | Per-request token & dollar tracking with budget guardrails |

---

## 🏗️ Architecture

```
┌────────────────────────────────────────────────────┐
│                  Next.js 15 Frontend               │
│  Dashboard │ Session Canvas │ Workspace │ Chat     │
│  D3.js Force Graph · Cluster Bubbles · Node Cards  │
└──────────────────────┬─────────────────────────────┘
                       │  REST / JSON
┌──────────────────────▼─────────────────────────────┐
│                  FastAPI Backend                    │
│  /sessions  /documents  /embeddings  /graph  /chat │
│                                                    │
│  Services:                                         │
│   extractor → chunker → embedder → clusterer       │
│   graph_builder → bridge_engine → chat_engine      │
│                                                    │
│  PostgreSQL + pgvector  (or SQLite fallback)        │
└────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- Node.js 18+ & pnpm
- (Optional) PostgreSQL 15+ with pgvector extension

### Backend

```bash
cd Backend
pip install -r requirement.txt

# Copy and edit environment variables
# Edit .env with your OPENAI_API_KEY

# Start the API server
uvicorn src.main:app --reload --port 8000
```

### Frontend

```bash
cd Frontend
pnpm install
pnpm dev          # → http://localhost:3000
```

---

## 📁 Project Structure

```
Backend/
├── .env                          # Shared environment config
├── pyproject.toml                # Poetry project config
├── requirement.txt               # pip requirements
├── src/
│   ├── main.py                   # FastAPI app entry
│   ├── config.py                 # Pydantic settings (singleton)
│   ├── routers/                  # API route handlers
│   ├── services/                 # Core business logic
│   ├── models/                   # DB models + Pydantic schemas
│   └── utils/                    # Helpers (normalizer, cost tracker)
│
Frontend/
├── app/                          # Next.js 15 App Router
│   ├── (auth)/login/
│   ├── dashboard/
│   ├── session/[id]/
│   ├── workspace/
│   └── api/                      # BFF routes
├── components/
│   ├── graph/                    # D3.js graph components
│   ├── chat/                     # Chat panel
│   ├── upload/                   # Document uploader
│   └── session/                  # Session manager
└── lib/
    ├── d3-config.ts
    └── api-client.ts
```

---

## 📝 API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/sessions` | Create analysis session |
| `GET` | `/api/sessions` | List all sessions |
| `POST` | `/api/documents/upload` | Upload & parse document |
| `POST` | `/api/embeddings/generate` | Generate embeddings for a session |
| `GET` | `/api/graph/{session_id}` | Get full graph (nodes + edges + clusters) |
| `GET` | `/api/graph/bridges` | Get cross-session bridge edges |
| `POST` | `/api/chat` | RAG chat with GPT-4o |
| `GET` | `/api/cost/usage` | Token & cost usage summary |

---

## 🔧 Environment Variables

See `.env` for all configurable values. Key ones:

| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Your OpenAI API key |
| `DATABASE_URL` | PostgreSQL connection string (empty = SQLite) |
| `JWT_SECRET` | Secret for JWT token signing |
| `MONTHLY_EMBEDDING_BUDGET` | Max USD spend on embeddings per month |
| `MONTHLY_CHAT_BUDGET` | Max USD spend on chat per month |

---

## License

MIT
