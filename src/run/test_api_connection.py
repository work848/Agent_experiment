from utils.embedding_utils import get_embedding_model
# 1 获取 embedding
embedding = get_embedding_model()
print("Embedding model loaded successfully!")
vec = embedding.embed_query("hello world")

print(len(vec))
print(vec[:5])
