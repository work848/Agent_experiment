from memory.chroma_client import (
    get_collection,
    embed_query
)


def search_code(query: str, k=5):

    collection = get_collection()

    query_embedding = embed_query(query)

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=k
    )

    docs = results["documents"][0]

    metas = results["metadatas"][0]

    output = []

    for doc, meta in zip(docs, metas):

        output.append({
            "function": meta["function"],
            "code": doc
        })

    return output