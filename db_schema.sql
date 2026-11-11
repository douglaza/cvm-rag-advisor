-- db_schema.sql — schema do invest-advisor (pgvector)
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id          BIGSERIAL PRIMARY KEY,
    source      TEXT NOT NULL,
    doc_type    TEXT NOT NULL DEFAULT 'doc',
    title       TEXT NOT NULL,
    url         TEXT,
    chunk_index INT  NOT NULL,
    content     TEXT NOT NULL,
    embedding   VECTOR(3072) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (source, chunk_index)
);

-- HNSW com halfvec suporta os embeddings de 3072 dimensões.
CREATE INDEX IF NOT EXISTS idx_documents_embedding
    ON documents USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops);

-- Índice de texto para o retriever híbrido (opcional)
CREATE INDEX IF NOT EXISTS idx_documents_content
    ON documents USING gin (to_tsvector('portuguese', content));
