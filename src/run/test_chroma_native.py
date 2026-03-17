# src/run/test_chroma_native.py
import os
# 【新增】禁用本地请求的代理，防止触发 502 错误
# os.environ["NO_PROXY"] = "localhost,127.0.0.1,::1"
from pathlib import Path
from dotenv import load_dotenv
import chromadb
from chromadb.utils import embedding_functions

# 加载环境变量
load_dotenv(dotenv_path="APIKey.env")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# -----------------------------
# 1️⃣ 定义 Embedding 函数（用 OpenAI Embeddings）
# -----------------------------
# 注意 chromadb 自己不依赖 LangChain，所以用 embedding_function 需要自己封装
def get_embedding(texts):
    from langchain_openai import OpenAIEmbeddings
    model = OpenAIEmbeddings(
        model="Pro/BAAI/bge-m3",
        api_key=OPENAI_API_KEY,
        openai_api_base="https://api.siliconflow.cn/v1",
        chunk_size=64
    )
    return [v for v in model.embed_documents(texts)]  # 返回向量列表
print("Embedding function defined successfully!")
# -----------------------------
# 2️⃣ 初始化 Chroma 客户端
# -----------------------------
# 注释掉容易在 Windows 崩溃的原生持久化客户端
# persist_dir = Path("long_memory/chroma_db")
# persist_dir.mkdir(parents=True, exist_ok=True)
# client = chromadb.PersistentClient(path=str(persist_dir))

# 替换为 HttpClient 去连接刚刚启动的独立服务
client = chromadb.HttpClient(host="localhost", port=8000)
print(f"Chroma HttpClient connected to localhost:8000!")

# 获取或创建 collection
collection_name = "agent_memory"
try:
    collection = client.get_collection(collection_name)
    print(f"Collection '{collection_name}' loaded successfully!")
except Exception:
    collection = client.create_collection(name=collection_name)

print(f"Collection '{collection_name}' initialized. Existing docs:", len(collection.get()["ids"]))
# -----------------------------
# 3️⃣ 添加文档（增量写入）
# -----------------------------
docs = [
    "User prefers Java for coding",
    "User is building an AI agent using LangGraph",
    "User likes studying AI systems"
]

# 生成向量
vectors = get_embedding(docs)

# 使用 chromadb 原生 API 添加
print("Adding documents to collection...")
collection.add(
    documents=docs,
    metadatas=[{"source": "test"} for _ in docs],
    ids=[f"doc{i}" for i in range(len(docs))],
    embeddings=vectors
)

print("After adding, total docs:", len(collection.get()["ids"]))

# -----------------------------
# 4️⃣ 查询相似向量
# -----------------------------
query_text = "What programming language does the user like?"
query_vector = get_embedding([query_text])[0]

results = collection.query(
    query_embeddings=[query_vector],
    n_results=2
)

print("\nSearch Results:")
for doc, score in zip(results["documents"][0], results["distances"][0]):
    print(doc, "=> score:", score)