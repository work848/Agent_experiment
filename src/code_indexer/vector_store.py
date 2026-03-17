import uuid

from memory.chroma_client import (
    get_collection,
    embed_texts
)


def store_function_embedding(name: str, code: str):

    collection = get_collection()

    embedding = embed_texts([code])[0]

    collection.add(
        ids=[str(uuid.uuid4())],
        embeddings=[embedding],
        documents=[code],
        metadatas=[{"function": name}]
    )