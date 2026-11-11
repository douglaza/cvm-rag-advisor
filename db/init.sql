-- db/init.sql

DROP TABLE IF EXISTS "Step", "Thread", "User", "Element" CASCADE;

CREATE EXTENSION IF NOT EXISTS vector;

-- ===== Tabela do RAG =====
CREATE TABLE IF NOT EXISTS documents (
    id           BIGSERIAL PRIMARY KEY,
    source       TEXT NOT NULL,
    doc_type     TEXT,
    title        TEXT,
    url          TEXT,
    chunk_index  INT  NOT NULL,
    content      TEXT NOT NULL,
    embedding    vector(3072),
    tsv          tsvector GENERATED ALWAYS AS (to_tsvector('portuguese', content)) STORED,
    UNIQUE (source, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_documents_embedding
    ON documents USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_documents_tsv ON documents USING gin (tsv);

-- ===== Tabelas do Chainlit =====
CREATE TABLE IF NOT EXISTS "User" (
    "id" TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    "identifier" TEXT NOT NULL UNIQUE,
    "metadata" JSONB,
    "createdAt" TIMESTAMPTZ DEFAULT now(),
    "updatedAt" TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "Thread" (
    "id" TEXT PRIMARY KEY,
    "createdAt" TIMESTAMPTZ DEFAULT now(),
    "updatedAt" TIMESTAMPTZ DEFAULT now(),
    "name" TEXT,
    "userId" TEXT,
    "userIdentifier" TEXT,
    "tags" TEXT[],
    "metadata" JSONB
);

CREATE TABLE IF NOT EXISTS "Step" (
    "id" TEXT PRIMARY KEY,
    "name" TEXT,
    "type" TEXT,
    "threadId" TEXT,
    "parentId" TEXT,
    "disableFeedback" BOOLEAN,
    "isError" BOOLEAN,
    "input" TEXT,
    "output" TEXT,
    "showInput" TEXT,
    "createdAt" TIMESTAMPTZ DEFAULT now(),
    "startTime" TIMESTAMPTZ,
    "endTime" TIMESTAMPTZ,
    "generation" JSONB,
    "metadata" JSONB
);

CREATE TABLE IF NOT EXISTS "Element" (
    "id" TEXT PRIMARY KEY,
    "threadId" TEXT NOT NULL REFERENCES "Thread"("id") ON DELETE CASCADE,
    "stepId" TEXT,
    "type" TEXT,
    "name" TEXT,
    "metadata" JSONB,
    "url" TEXT,
    "chainlitKey" TEXT,
    "display" TEXT,
    "objectKey" TEXT,
    "size" TEXT,
    "mime" TEXT,
    "language" TEXT,
    "page" INTEGER,
    "props" JSONB,
    "createdAt" TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS "Feedback" (
    "id" TEXT PRIMARY KEY,
    "stepId" TEXT NOT NULL REFERENCES "Step"("id") ON DELETE CASCADE,
    "name" TEXT NOT NULL,
    "value" DOUBLE PRECISION NOT NULL,
    "comment" TEXT,
    "createdAt" TIMESTAMPTZ DEFAULT now()
);