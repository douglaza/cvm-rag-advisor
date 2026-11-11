# Invest Advisor
Consultor de investimentos RAG sobre regulação CVM (Português).

## Stack
- **Postgres + pgvector** (HNSW, halfvec 3072) — busca híbrida: semântica + FTS `portuguese`
- **Gemini** — embeddings (gemini-embedding-001) e chat com fallback em cadeia
- **Chainlit** — interface de chat | **uv** — gerenciamento | **Docker Compose** — deploy

## Setup
1. Copie `.env.example` → `.env` (GOOGLE_API_KEY, DATABASE_URL, EMBEDDING_MODEL, CHAT_MODEL)
2. `uv sync`
3. Suba o banco: `docker compose up -d db` e aplique `schema.sql`
4. Indexe: coloque PDFs/MD/TXT em `docs/` e rode `uv run python ingest.py`
5. Teste CLI: `uv run python rag.py "sua pergunta"`
6. UI: `uv run chainlit run app.py`

## Aviso
Respostas apenas informativas, baseadas nos documentos indexados. **Não constitui recomendação de investimento.**
