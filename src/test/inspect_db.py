from memory.chroma_client import get_collection

def inspect_db():
    collection = get_collection()
    # 获取库中所有数据（包含文档内容和元数据）
    results = collection.get(include=["documents", "metadatas"])
    
    ids = results["ids"]
    docs = results["documents"]
    metas = results["metadatas"]
    
    print(f"\n=== ChromaDB 审计报告 (共 {len(ids)} 条记录) ===")
    
    if not ids:
        print("❌ 警告：数据库是空的！")
        return

    for i in range(len(ids)):
        print(f"\nID: {ids[i]}")
        print(f"File: {metas[i].get('file', 'N/A')}")
        # 只打印前 100 个字符看看内容
        content_snippet = docs[i].replace('\n', ' ')[:100]
        print(f"Content: {content_snippet}...")
        print("-" * 30)

    # 特别检查 search_code
    search_hits = [id for id in ids if "search_code" in id]
    if search_hits:
        print(f"\n✅ 确认：'search_code' 已在库中 (ID: {search_hits})")
    else:
        print(f"\n❌ 缺漏：'search_code' 不在库中！")

if __name__ == "__main__":
    inspect_db()