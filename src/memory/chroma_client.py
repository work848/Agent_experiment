# src/memory/chroma_client.py

import os
from dotenv import load_dotenv
import chromadb
from langchain_openai import OpenAIEmbeddings

# 加载环境变量
load_dotenv("APIKey.env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# -------------------------
# Embedding 模型
# -------------------------
embedding_model = OpenAIEmbeddings(
    model="Pro/BAAI/bge-m3",
    api_key=OPENAI_API_KEY,
    openai_api_base="https://api.siliconflow.cn/v1",
    chunk_size=64
)

# -------------------------
# Chroma client
# -------------------------
client = chromadb.HttpClient(host="localhost", port=8000)

COLLECTION_NAME = "agent_long_term_memory"


def get_collection():
    try:
        collection = client.get_collection(COLLECTION_NAME)
    except Exception:
        collection = client.create_collection(name=COLLECTION_NAME)

    return collection


def embed_texts(texts: list[str]):
    return embedding_model.embed_documents(texts)


def embed_query(text: str):
    return embedding_model.embed_query(text)