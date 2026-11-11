"""app.py — UI conversacional do invest-advisor (Chainlit)"""
import os
import chainlit as cl
from chainlit.data.chainlit_data_layer import ChainlitDataLayer

from rag import answer

database_url = os.getenv("DATABASE_URL") or os.getenv("CHAINLIT_DATABASE_URL")
if not database_url:
    raise RuntimeError(
        "Configure CHAINLIT_DATABASE_URL ou DATABASE_URL para conectar o banco."
    )

os.environ.setdefault("DATABASE_URL", database_url)
os.environ.setdefault("CHAINLIT_DATABASE_URL", database_url)


@cl.data_layer
def data_layer():
    return ChainlitDataLayer(database_url)


@cl.on_chat_start
async def start():
    await cl.Message(
        content="👋 **Invest Advisor** — pergunte sobre regulação CVM e fundos de investimento.\n\n"
                "_Baseado exclusivamente nos documentos indexados (rode ingest.py para atualizar)._"
    ).send()

@cl.on_message
async def on_message(msg: cl.Message):
    resposta = await cl.make_async(answer)(msg.content)
    await cl.Message(content=resposta["answer"]).send()
    if resposta["sources"]:
        fontes = "\n".join(
            f"- `{s['source']}` chunk {s['chunk_index']}"
            f" (vec={s['vscore'] and round(s['vscore'], 3)}, fts={s['fscore'] and round(s['fscore'], 3)})"
            for s in resposta["sources"]
        )
        await cl.Message(content=f"📚 **Fontes:**\n{fontes}").send()
