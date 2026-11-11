"""
ingest.py — Ingestao de documentos para o invest-advisor
1. Baixa o corpus da CVM (fontes em SOURCES) -> cache local em data/cvm/
2. Indexa PDFs/MD/TXT de docs/ locais
3. Gera embeddings (gemini-embedding-001, 3072 dims) e insere no Postgres (pgvector)
"""
import hashlib
import os
import pathlib
import sys

import psycopg
import requests
from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader, TextLoader
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

load_dotenv(pathlib.Path(__file__).resolve().with_name(".env"))

CHUNK_SIZE = 1200
CHUNK_OVERLAP = 150
BATCH = 64
EMBEDDING_DIMENSIONS = 3072

SOURCES = [
    # (doc_type, url, source_name)
    ("regulamento",
     "https://dados.cvm.gov.br/dados/INSTITUCIONAL/INSTRUMENTOS/Dados/Resolu%C3%A7%C3%B5es%20-%20Institucional_2020.csv",
     "cvm_resolucoes"),
]

def fetch(url: str, cache: pathlib.Path) -> str:
    if cache.exists():
        return cache.read_text(encoding="utf-8", errors="ignore")
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    cache.write_bytes(r.content)
    return cache.read_text(encoding="utf-8", errors="ignore")

def load_all() -> list:
    docs = []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    # 1) Corpus CVM (cache em data/cvm/)
    cache_dir = pathlib.Path("data/cvm")
    cache_dir.mkdir(parents=True, exist_ok=True)
    for doc_type, url, name in SOURCES:
        try:
            text = fetch(url, cache_dir / f"{name}_{hashlib.md5(url.encode()).hexdigest()[:8]}")
            for i, ch in enumerate(splitter.split_text(text)):
                docs.append({"source": name, "doc_type": doc_type, "title": name,
                             "url": url, "content": ch, "chunk_index": i})
            print(f"[CVM] {name}: ok")
        except Exception as e:
            print(f"[CVM] {name}: FALHOU ({type(e).__name__}: {str(e)[:100]})")

    # 2) Docs locais em docs/
    docs_dir = pathlib.Path("docs")
    if docs_dir.exists():
        for path in sorted(docs_dir.rglob("*")):
            try:
                if path.suffix.lower() == ".pdf":
                    pages = PyPDFLoader(str(path)).load()
                    text = "\n".join(p.page_content for p in pages)
                elif path.suffix.lower() in (".txt", ".md"):
                    text = TextLoader(str(path), encoding="utf-8").load()[0].page_content
                else:
                    continue
                name = path.stem
                for i, ch in enumerate(splitter.split_text(text)):
                    docs.append({"source": str(path), "doc_type": "doc", "title": name,
                                 "url": None, "content": ch, "chunk_index": i})
                print(f"[LOCAL] {path.name}: ok")
            except Exception as e:
                print(f"[LOCAL] {path.name}: FALHOU ({type(e).__name__}: {str(e)[:100]})")

    print(f"\nTotal de chunks: {len(docs)}")
    return docs

def main():
    required_env = ("DATABASE_URL", "EMBEDDING_MODEL", "GOOGLE_API_KEY")
    missing_env = [name for name in required_env if not os.getenv(name)]
    if missing_env:
        sys.exit(
            "Variáveis ausentes: " + ", ".join(missing_env)
            + ". Configure-as no arquivo .env."
        )

    docs = load_all()
    if not docs:
        sys.exit("Nada para indexar.")

    embedder = GoogleGenerativeAIEmbeddings(
        model=os.environ["EMBEDDING_MODEL"],
        google_api_key=os.environ["GOOGLE_API_KEY"],
    )

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT format_type(a.atttypid, a.atttypmod)
               FROM pg_attribute AS a
               WHERE a.attrelid = to_regclass('documents')
                 AND a.attname = 'embedding'
                 AND NOT a.attisdropped"""
        )
        column = cur.fetchone()
        expected_type = f"vector({EMBEDDING_DIMENSIONS})"
        if not column or column[0] != expected_type:
            actual_type = column[0] if column else "coluna ausente"
            raise RuntimeError(
                f"documents.embedding está como {actual_type}; "
                f"o modelo configurado requer {expected_type}. "
                "Ajuste o schema antes de indexar."
            )

        for start in range(0, len(docs), BATCH):
            batch = docs[start:start + BATCH]
            vectors = embedder.embed_documents([d["content"] for d in batch])
            if len(vectors) != len(batch):
                raise RuntimeError(
                    f"O modelo retornou {len(vectors)} embeddings para "
                    f"{len(batch)} documentos."
                )
            invalid_dimensions = sorted(
                {len(vector) for vector in vectors if len(vector) != EMBEDDING_DIMENSIONS}
            )
            if invalid_dimensions:
                raise RuntimeError(
                    f"O modelo retornou embeddings com dimensões "
                    f"{invalid_dimensions}; esperado {EMBEDDING_DIMENSIONS}."
                )

            for d, v in zip(batch, vectors, strict=True):
                cur.execute(
                    """INSERT INTO documents (source, doc_type, title, url, chunk_index, content, embedding)
                       VALUES (%s, %s, %s, %s, %s, %s, %s)
                       ON CONFLICT (source, chunk_index) DO UPDATE
                       SET content = EXCLUDED.content, embedding = EXCLUDED.embedding""",
                    (d["source"], d["doc_type"], d["title"], d["url"],
                     d["chunk_index"], d["content"],
                     "[" + ",".join(map(str, v)) + "]"),
                )
            print(f"Inseridos {start + len(batch)}/{len(docs)}")
        conn.commit()
    print("Ingestao concluida.")

if __name__ == "__main__":
    main()
