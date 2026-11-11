# Invest Advisor

Assistente experimental de pesquisa sobre regulação do mercado de investimentos
brasileiro. O MVP combina documentos locais, busca híbrida em PostgreSQL/pgvector
e Gemini para gerar respostas em português com referências aos trechos consultados.

> **Tutorial visual:** [acesse o tutorial do projeto](https://douglaza.github.io/cvm-rag-advisor/advisor.html).
> Ele apresenta diagramas do fluxo, a busca híbrida e exemplos de ingestão.

> **Importante:** este projeto é informativo e experimental. As respostas dependem
> dos documentos que foram indexados; não são aconselhamento jurídico ou financeiro
> nem recomendação de investimento.

## Como funciona

O sistema tem dois fluxos:

1. **Ingestão (`ingest.py`)** — lê PDFs, Markdown e texto em `docs/`, tenta
   obter uma fonte CVM configurada no código e guarda essa cópia em `data/cvm/`.
   O texto é dividido em trechos de até 1.200 caracteres, com sobreposição de
   150 caracteres. O Gemini cria um embedding de 3.072 dimensões para cada
   trecho, que é salvo no PostgreSQL.
2. **Consulta (`app.py` → `rag.py`)** — a interface Chainlit recebe a pergunta.
   O motor cria seu embedding e combina busca vetorial por similaridade com
   busca textual em português. Os trechos encontrados são enviados ao Gemini
   como contexto; a resposta inclui citações `[n]`, a lista de fontes e um
   aviso de que não constitui recomendação de investimento.

```text
PDF / Markdown / TXT ──► ingest.py ──► chunks + embeddings ──► PostgreSQL
                                                                    ▲
Navegador ──► Chainlit (app.py) ──► rag.py ──► busca híbrida ──────┘
                                        │
                                        └── Gemini ──► resposta + fontes
```

### Busca e armazenamento

- **PostgreSQL 16 + pgvector** armazenam o conteúdo, os metadados e os vetores.
- A coluna de embeddings usa `vector(3072)`; o índice HNSW é criado sobre uma
  expressão `halfvec(3072)` para suportar essa dimensão.
- A busca vetorial usa distância de cosseno. A busca textual usa
  `websearch_to_tsquery('portuguese')` e `ts_rank`; os resultados são unidos e
  deduplicados.
- O motor usa até quatro trechos (`TOP_K = 4`) como contexto para o modelo.
- A ingestão usa upsert pela combinação `(source, chunk_index)`, para atualizar
  trechos existentes ao reprocessar a mesma fonte.

## O que está implementado

| Componente | Situação |
| --- | --- |
| Ingestão de PDF, Markdown e TXT | Implementada em `ingest.py` |
| Busca vetorial e textual | Implementada em `rag.py` |
| Respostas com Gemini e citações | Implementadas em `rag.py` |
| Interface de chat | Chainlit em `app.py` |
| Banco local com pgvector | Docker Compose e `db/init.sql` |
| LangGraph, API FastAPI e Langfuse | Dependências/planos; não fazem parte do fluxo atual do MVP |

O endereço de download CVM atualmente definido em `ingest.py` pode falhar
(histórico de resposta HTTP 404). Para um corpus confiável, coloque documentos
oficiais em `docs/` e confira no log da ingestão quais fontes foram carregadas.
O arquivo `docs/teste_cvm.md` é apenas um exemplo para teste, não uma fonte
regulatória completa.

## Requisitos

- Python 3.12
- [uv](https://docs.astral.sh/uv/) (recomendado) ou `pip`
- Docker com Docker Compose v2 para executar o PostgreSQL localmente
- Uma chave `GOOGLE_API_KEY` do [Google AI Studio](https://aistudio.google.com/apikey)

## Configuração e execução local

Na raiz do projeto:

```bash
git clone https://github.com/douglaza/cvm-rag-advisor.git
cd cvm-rag-advisor
cp .env.example .env
```

Edite `.env` e informe sua chave `GOOGLE_API_KEY`. Os demais valores do
`.env.example` selecionam o banco local e os modelos do MVP. Não compartilhe nem
envie o arquivo `.env` ao Git.

Instale as dependências e suba o banco:

```bash
uv sync
docker compose up -d db
```

Se preferir `pip` em vez de `uv`, crie e ative um ambiente virtual e instale
as dependências de runtime:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Na primeira inicialização de um volume vazio, o Compose executa
`db/init.sql` automaticamente. Se o volume já existia, os scripts de
`docker-entrypoint-initdb.d` não são executados novamente. Para criar as tabelas
que faltarem em um banco existente, aplique o script idempotente:

```bash
docker compose exec -T db psql -U postgres -d invest_advisor < db/init.sql
```

> `CREATE TABLE IF NOT EXISTS` não migra tabelas antigas. Se você tiver um schema
> anterior, faça backup e revise/migre as colunas antes de ingerir documentos.

Adicione arquivos `.pdf`, `.md` ou `.txt` a `docs/` e execute a ingestão:

```bash
uv run python ingest.py
```

A ingestão chama a API de embeddings do Google e pode consumir cota. Ela encerra
com erro claro se faltarem variáveis obrigatórias ou se a dimensão da coluna
`documents.embedding` não corresponder aos 3.072 valores esperados.

Teste uma consulta no terminal:

```bash
uv run python rag.py "O que trata a Resolução CVM 30?"
```

Inicie a interface:

```bash
uv run chainlit run app.py --host 127.0.0.1 --port 8000
```

Abra <http://localhost:8000>.

## Execução com Docker Compose

Com `.env` configurado, inicie o banco e a interface:

```bash
docker compose up --build -d
docker compose logs -f app
```

A interface fica disponível em <http://localhost:8000>. Para ingerir arquivos
que estejam em `docs/` no host, use:

```bash
docker compose exec app uv run python ingest.py
```

O serviço `app` monta `docs/` e conecta ao serviço `db` na porta interna `5432`.
Para encerrar sem apagar os dados persistidos:

```bash
docker compose down
```

O banco publica a porta `5434` no host (`localhost:5434`). As credenciais
definidas no Compose são para desenvolvimento local; altere-as e restrinja o
acesso antes de expor o banco a uma rede.

## Configuração

| Variável | Obrigatória | Finalidade |
| --- | --- | --- |
| `DATABASE_URL` | Sim | Conexão PostgreSQL. Local: `postgresql://postgres:postgres@localhost:5434/invest_advisor`. No Compose, o serviço `app` substitui o host/porta por `db:5432`. |
| `GOOGLE_API_KEY` | Sim | Acesso à API Gemini para embeddings e geração de respostas. |
| `EMBEDDING_MODEL` | Sim para ingestão e consulta | Modelo de embeddings. O schema atual espera `gemini-embedding-001` (3.072 dimensões). |
| `CHAT_MODEL` | Não | Modelo Gemini principal; o padrão do código é `gemini-flash-latest`. |
| `LANGFUSE_*` | Não | Variáveis reservadas para observabilidade; Langfuse ainda não está integrado ao fluxo do MVP. |

Não reutilize nomes de modelos descontinuados. A disponibilidade e as cotas do
Gemini podem variar por conta e região; consulte o Google AI Studio se receber
erros `404`, `429` ou `503`.

## Arquivos principais

```text
app.py              Interface Chainlit e conexão com a camada de dados
rag.py              Busca híbrida, montagem do contexto e resposta Gemini
ingest.py           Leitura, chunking, embeddings e gravação dos documentos
docs/               PDFs, Markdown e TXT a indexar
data/cvm/           Cache local da fonte remota CVM
db/init.sql         Schema inicial do PostgreSQL e tabelas Chainlit
docker-compose.yml  Banco pgvector e aplicação
Dockerfile          Imagem da aplicação
pyproject.toml      Dependências e configuração do projeto
uv.lock             Versões fixadas para instalação reproduzível com uv
requirements.txt    Dependências de runtime para instalação com pip
advisor.html        Tutorial visual publicado no GitHub Pages
```

## Problemas comuns

- **`GOOGLE_API_KEY` ausente:** configure `.env`; a chave não deve ser colocada
  no código nem commitada.
- **Embedding com dimensão incompatível:** mantenha o modelo de embedding e
  `vector(3072)` alinhados; é preciso reingerir os documentos ao trocar de modelo.
- **Fonte CVM retorna 404:** a ingestão registra a falha e continua com os
  documentos locais. Baixe documentos oficiais e coloque-os em `docs/`.
- **Banco não sobe ou não conecta:** verifique `docker compose ps`,
  `docker compose logs db` e se a porta `5434` do host está livre.
- **Modelo Gemini retorna `404`, `429` ou `503`:** confirme o identificador do
  modelo, sua disponibilidade para a chave e a cota. Alguns erros dependem da
  disponibilidade temporária do serviço.
- **Aviso de tradução pt-BR do Chainlit:** o Chainlit pode usar a tradução
  padrão em inglês; esse aviso não impede o funcionamento do chat.

## Privacidade e uso responsável

Não inclua credenciais ou documentos confidenciais no repositório. As perguntas
e os trechos enviados ao Gemini são processados pelo serviço externo do Google;
considere isso ao escolher o material indexado. Verifique as normas diretamente
nas publicações oficiais antes de tomar decisões.

---

Respostas exclusivamente informativas, baseadas nos documentos indexados.
**Isto não constitui recomendação de investimento.**
