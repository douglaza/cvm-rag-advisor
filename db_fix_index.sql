-- Correcao: HNSW max 2000 dims -> usar halfvec(3072) via indice de expressao
DROP INDEX IF EXISTS idx_documents_embedding;

CREATE INDEX IF NOT EXISTS idx_documents_embedding
    ON documents USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops);
