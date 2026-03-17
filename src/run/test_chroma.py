# src/run/safe_chroma.py
import os
from pathlib import Path
from langchain_chroma import Chroma
from langchain_core.documents import Document
from utils.embedding_utils import get_embedding_model
from chromadb.config import Settings

# ==============================
# 配置路径
# ==============================
PERSIST_DIR = Path("long_memory/chroma_db")
COLLECTION_NAME = "agent_memory"

# 确保文件夹存在
PERSIST_DIR.mkdir(parents=True, exist_ok=True)

# ==============================
# 1. 加载 embedding
# ==============================
embedding = get_embedding_model()
print("Embedding model loaded successfully!")

# ==============================
# 2. 初始化 Chroma
# ==============================
vectorstore = Chroma(
    collection_name=COLLECTION_NAME,
    embedding_function=embedding,
    persist_directory=str(PERSIST_DIR),
    client_settings=Settings(
        anonymized_telemetry=False  # 关闭 telemetry 避免卡住
    )
)
print(f"Chroma vectorstore initialized successfully at {PERSIST_DIR}!")

# ==============================
# 3. 如果数据库为空，写入测试数据
# ==============================
try:
    doc_count = vectorstore._collection.count()
    print(f"Existing docs in collection: {doc_count}")
except Exception as e:
    print("Error reading collection count:", e)
    doc_count = 0

if doc_count == 0:
    print("Database empty. Writing test documents...")
    docs = [
        Document(page_content="User prefers Java for coding"),
        Document(page_content="User is building an AI agent using LangGraph"),
        Document(page_content="User likes studying AI systems")
    ]
    try:
        vectorstore.add_documents(docs)
        print("Test documents stored successfully!")
        print("Total docs:", vectorstore._collection.count())
    except Exception as e:
        print("Error storing documents:", e)

# ==============================
# 4. 查询测试
# ==============================
try:
    print("Start searching...")
    results = vectorstore.similarity_search(
        "What programming language does the user like?",
        k=2
    )
    print("Search finished!\nResults:")
    for r in results:
        print("-", r.page_content)
except Exception as e:
    print("Error during similarity search:", e)