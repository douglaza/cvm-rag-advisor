"""
rag.py — Motor RAG do invest-advisor
Retriever hibrido (vetorial + full-text portugues) + LLM Gemini com fallback.
Uso CLI: uv run python rag.py "sua pergunta"
"""
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from psycopg.types.json import Json

load_dotenv(Path(__file__).resolve().with_name(".env"))

TOP_K = 4
# Fallback: tenta na ordem se um modelo falhar (quota/timeout/indisponibilidade)
CHAT_FALLBACKS = ["gemini-flash-latest", "gemini-2.5-flash", "gemini-2.5-flash-lite"]

def _emb() -> GoogleGenerativeAIEmbeddings:
    return GoogleGenerativeAIEmbeddings(
        model=os.environ["EMBEDDING_MODEL"],
        google_api_key=os.environ["GOOGLE_API_KEY"],
    )

def retrieve(query: str) -> list[dict]:
    """Busca hibrida: similaridade semantica (HNSW/halfvec) + ts_rank full-text."""
    vec = _emb().embed_query(query)
    pat = " ".join(query.split()[:8])  # termo simples para o FTS
    sql = """
    WITH v AS (
        SELECT id, source AS v_source, doc_type AS v_doc_type, title AS v_title,
               chunk_index AS v_chunk_index, content AS v_content,
               (embedding::halfvec(3072) <=> %s::halfvec(3072)) AS dist
        FROM documents
        ORDER BY embedding::halfvec(3072) <=> %s::halfvec(3072)
        LIMIT %s
    ),
    f AS (
        SELECT id, source AS f_source, doc_type AS f_doc_type, title AS f_title,
               chunk_index AS f_chunk_index, content AS f_content,
               ts_rank(to_tsvector('portuguese', content),
                       websearch_to_tsquery('portuguese', %s)) AS rank
        FROM documents
        WHERE to_tsvector('portuguese', content)
              @@ websearch_to_tsquery('portuguese', %s)
        ORDER BY rank DESC
        LIMIT %s
    )
    SELECT COALESCE(v.v_source, f.f_source),
           COALESCE(v.v_doc_type, f.f_doc_type),
           COALESCE(v.v_title, f.f_title),
           COALESCE(v.v_chunk_index, f.f_chunk_index),
           COALESCE(v.v_content, f.f_content),
           CASE WHEN v.id IS NOT NULL THEN 1.0 - v.dist ELSE NULL END AS vscore,
           f.rank AS fscore
    FROM v FULL OUTER JOIN f USING (id)
    """
    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute(sql, ("[" + ",".join(map(str, vec)) + "]",) * 2
                    + (TOP_K, pat, pat, TOP_K))
        rows = cur.fetchall()
    hits, seen = [], set()
    for source, doc_type, title, idx, content, vs, fs in rows:
        key = (source, idx)
        if key in seen:
            continue
        seen.add(key)
        hits.append({"source": source, "doc_type": doc_type, "title": title,
                     "chunk_index": idx, "content": content,
                     "vscore": vs, "fscore": fs})
    return hits

# def _llm() -> ChatGoogleGenerativeAI:
#     models = [os.environ.get("CHAT_MODEL", "gemini-2.5-flash")] + CHAT_FALLBACKS
#     last = None
#     for m in dict.fromkeys(models):  # dedupe, mantem ordem
#         try:
#             llm = ChatGoogleGenerativeAI(model=m,
#                                          google_api_key=os.environ["GOOGLE_API_KEY"],
#                                          timeout=120)
#             llm.invoke("ok")  # healthcheck barato
#             return llm
#         except Exception as e:
#             last = e
#             print(f"[fallback] {m} indisponivel: {str(e)[:80]}")
#     raise last

def _llm() -> ChatGoogleGenerativeAI:
    models = [os.environ.get("CHAT_MODEL", "gemini-flash-latest")] + CHAT_FALLBACKS
    last = None
    for m in dict.fromkeys(models):
        try:
            return ChatGoogleGenerativeAI(model=m,
                                         google_api_key=os.environ["GOOGLE_API_KEY"],
                                         timeout=120)
        except Exception as e:
            last = e
            print(f"[fallback] {m} indisponivel: {str(e)[:80]}")
    raise last


def answer(question: str) -> dict:
    hits = retrieve(question)
    if not hits:
        return {"answer": "Não encontrei nada na base sobre isso. Adicione documentos em docs/ e rode ingest.py.", "sources": []}
    ctx = "\n\n---\n\n".join(
        f"[{i+1}] ({h['source']}, chunk {h['chunk_index']})\n{h['content']}"
        for i, h in enumerate(hits))
    prompt = f"""Você é um consultor de investimentos que responde APENAS com base nos
trechos regulatórios fornecidos. Regras:
- Responda em português, de forma objetiva.
- Cite as fontes usadas no formato [n].
- Se os trechos não forem suficientes, diga isso claramente — NÃO invente.
- Inclua a frase: "Isto não constitui recomendação de investimento."

TRECHOS:
{ctx}

PERGUNTA: {question}"""
    msg = _llm().invoke(prompt).content
    if isinstance(msg, list):  # blocos [{'type':'text','text':...}]
        msg = "\n".join(b.get("text", "") for b in msg if isinstance(b, dict))
    text = str(msg).strip()
    return {"answer": text,
            "sources": [{"source": h["source"], "chunk_index": h["chunk_index"],
                         "vscore": h["vscore"], "fscore": h["fscore"]}
                        for h in hits]}

if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "O que trata a Resolução CVM 30?"
    print(f"Q: {q}\n")
    r = answer(q)
    print(r["answer"])
    print("\nFontes:")
    for s in r["sources"]:
        print(f"  {s['source']} #chunk {s['chunk_index']} (vec={s['vscore'] and round(s['vscore'],3)}, fts={s['fscore'] and round(s['fscore'],3)})")
