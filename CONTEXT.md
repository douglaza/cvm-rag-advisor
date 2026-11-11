
cd ~/Documentos/invest-advisor
cat > CONTEXT.md << 'EOF'

# CONTEXT.md — Invest Advisor

## Visão

Assistente de pesquisa regulatória/analítica para mercado financeiro BR.
Agente RAG sobre normas da CVM. Stack: LangGraph + Postgres/pgvector +
Gemini (LLM + embeddings) + FastAPI. Observabilidade futura: Langfuse.

## Arquitetura planejada

- Grafo LangGraph: planner → retriever → synthesizer → compliance
- Corpus: normas CVM (Resolução 175, etc.) → chunking → embeddings (3072d,
  gemini-embedding-001) → pgvector com índice HNSW (cosine)
- API FastAPI expõe o agente

## Estado atual (Fase 0/infra ✅ + MVP funcional ✅)

- Projeto único na RAIZ de ~/Documentos/invest-advisor (sem subpastas-projeto)
- Código legado arquivado em _old/ (pode ser deletado após revisão)
- uv + Python 3.12, .venv na raiz; deps: langgraph, langchain,
  google-genai, fastapi, psycopg[binary,pool], pydantic-settings, chainlit,
  langchain-google-genai
- Docker: container invest_advisor_db (pgvector/pgvector:pg16), healthy
  - Porta HOST 5434 → container 5432 (5432 ocupada por Postgres do sistema)
  - Extensão pgvector 0.8.7 criada no banco invest_advisor
  - Credenciais: postgres/postgres
- **PROJETO FUNCIONAL END-TO-END**: ingest → retrieve híbrido → LLM → UI Chainlit

## Modelos (definitivo para MVP)

- EMBEDDING_MODEL=gemini-embedding-001 — dim 3072 (text-embedding-004: 404)
- CHAT_MODEL no .env — gemini-2.0-flash DESCONTINUADO (404);
  gemini-2.5-flash deu 404 em contas novas
- Estratégia: fixar um modelo ativo no .env + CHAT_FALLBACKS no rag.py
- gemini-flash-latest: confirmado funcionando (free tier, 200 OK)

## Pendências

- [ ] Trocar healthcheck llm.invoke("ok") em _llm() por try/except na
  chamada real (custa 1 chamada por pergunta; causa ~1min de demora)
- [ ] Corrigir CHAT_MODEL no .env (ainda aponta para modelo 404) para
  eliminar o fallback desnecessário
- [ ] Corpus real: URL dados.cvm.gov.br INSTRUMENTOS → 404. Usar PDFs
  oficiais baixados manualmente em docs/
- [ ] Grafo LangGraph + FastAPI (substituir/complementar Chainlit)
- [ ] Migração futura p/ Vertex AI em produção

## Decisões tomadas

- Porta do banco: 5434 (não 5432) — refletir em TODO lugar
- Embeddings MVP: Gemini API (API key) via langchain-google-genai
- Chunking: RecursiveCharacterTextSplitter(1200, overlap 150)
- Schema: VECTOR(3072), índice HNSW sobre halfvec(3072)
- UI MVP: Chainlit (app.py) em vez de FastAPI — mais rápido para demo
- Workflow uv: 'uv run' dispensa ativar .venv, mas ativar também funciona

## Comandos úteis

- uv sync / uv add <pkg></pkg>                    # deps
- docker compose up -d                      # subir banco
- docker compose exec db psql -h localhost -U postgres -d invest_advisor -P pager=off
- uv run python ingest.py                   # ingestão (cache data/cvm/ + docs/)
- uv run python rag.py "pergunta"           # teste CLI do RAG
- chainlit run app.py                       # UI em http://localhost:8000

## Workflow do terminal

- SQL: salvar em arquivo com `cat > arquivo.sql << 'EOF'` e aplicar com
  `psql "$DATABASE_URL" -f arquivo.sql`. Nunca colar SQL direto no bash.
- Python: sempre via `uv run python << 'EOF'`.
- psql sempre com -P pager=off (ou export PAGER=cat) para não suspender no less.

## pgvector — confirmado

- Índice HNSW sobre halfvec(3072) funcionando.
- KNN: ORDER BY embedding::halfvec(3072) <=> %s::halfvec(3072)

## Ingestão (ingest.py)

- Corpus CVM (cache data/cvm/) + docs/ locais; chunks 1200/150;
  batches de 64; upsert por (source, chunk_index).

## rag.py — motor RAG

- retrieve(): híbrido — KNN halfvec(3072) + ts_rank
  websearch_to_tsquery('portuguese'), merge por FULL OUTER JOIN USING(id),
  dedupe por (source, chunk_index). TOP_K = 4.
- LLM com fallback em cadeia (CHAT_MODEL -> CHAT_FALLBACKS no rag.py).
- Prompt: responde só com base nos trechos, citações [n], disclaimer
  "Isto não constitui recomendação de investimento."
- CLI: uv run python rag.py "pergunta"

## Erros encontrados e soluções

1. **gemini-2.0-flash 404 NOT_FOUND** — modelo descontinuado.
   Solução: usar gemini-flash-latest; modelos atuais não têm nome
   estável garantido — manter CHAT_FALLBACKS.
2. **text-embedding-004 404** — Solução: gemini-embedding-001 (dim 3072).
   Ajustar VECTOR() conforme dim real ANTES de criar schema.
3. **gemini-2.5-flash 404 em contas novas / 503 em flash alternativos**
   — free tier com alta demanda. Solução: varredura de candidatos +
   fallback em cadeia no rag.py.
4. **psycopg.errors.AmbiguousColumn** no FULL OUTER JOIN USING(id) com
   colunas de mesmo nome nas duas CTEs — Solução: aliases prefixados
   (v_*, f_*) nas CTEs + COALESCE no SELECT final.
5. **LLM .content vira lista de blocos** [{'type':'text','text':...}] —
   Solução: join dos campos 'text' quando isinstance(msg, list).
6. **Chave 'chunk' vs 'chunk_index'** desalinhada entre retrieve() e
   answer() — padronizar em 'chunk_index'.
7. **Latência de ~1min por pergunta** — causada pelo healthcheck
   llm.invoke("ok") dentro de _llm() + tentativa de modelo 404.
   Solução: remover healthcheck, corrigir CHAT_MODEL no .env.
   (PENDENTE aplicar)
8. **FTS com score baixo (0.194)** — websearch_to_tsquery com 8 palavras
   cruas é pouco seletivo. OK para MVP com 1 doc; reavaliar com corpus
   maior (considerar tsquery com pesos ou abrir mão do limite de 8 termos).
9. **Chainlit: tradução pt-BR não encontrada** — warning inofensivo,
   usa en-US como default.

## Validação end-to-end (2026-11-10)

- docs/teste_cvm.md ingerido; pergunta "O que é a CVM?" respondida
  corretamente na Chainlit com citação [1] e disclaimer.
- Scores: vec=0.781, fts=0.194 (híbrido funcionando).
- Único incômodo: latência (ver erro #7).

## Entrega final

- app.py (Chainlit): resposta + bloco de fontes com scores vec/fts.
- Dockerfile (uv slim) + docker-compose.yml (pgvector/pg16 + app,
  healthcheck db).
- README.md com setup completo.
  EOF
  echo "CONTEXT.md atualizado ✅"
