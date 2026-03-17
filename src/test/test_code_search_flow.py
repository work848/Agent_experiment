import pytest
from code_indexer import work_space_indexer
from memory.chroma_client import get_collection, embed_texts
# 假设你的类定义在以下路径，请根据实际情况修改 import
from search.code_search_engine import CodeSearchEngine
from code_indexer.work_space_indexer import WorkspaceIndexer

def test_code_search_flow():
    # 1. 配置路径
    workspace_root = r"C:\makeMoney\PersonalProject\Agent_project\src\tools"
    
    # # 2. 提取代码结构 (Indexer)
    print("\n[1/4] 正在扫描代码库...")
    indexer = WorkspaceIndexer(workspace_root)
    graph_data = indexer.build()
    
    # # 3. 初始化 Search Engine
    # # 注意：Chroma 原生 query 如果不传 embedding_function，需要我们手动处理向量
    collection = get_collection()
    
    engine = CodeSearchEngine(
        chroma_collection=collection,
        call_graph=graph_data["call_graph"],
        function_index=graph_data["function_index"],
        workspace_root=workspace_root
    )

    # 4. 构建向量索引 (将代码存入 Chroma)
    # 注意：如果你的 CodeSearchEngine 内部没有处理 embedding，
    # 这里的 build_vector_index 逻辑可能需要确保调用了你定义的 embed_texts
    print("[2/4] 正在构建向量索引 (写入 ChromaDB)...")
    engine.build_vector_index()

    # 5. 执行搜索测试
    query ="""def search_code(query: str, max_results: int = 5) -> str:"""
    print(f"[3/4] 正在执行语义搜索: '{query}'")
    
    # 执行搜索
    search_result = engine.search(query)

    # 6. 验证结果
    print("[4/4] 搜索结果验证:")
    print(f"找到的相关函数列表: {search_result['functions']}")
    
    assert isinstance(search_result["functions"], list)
    assert "context" in search_result
    
    if search_result["context"]:
        print("✅ 成功获取代码上下文")
        print(search_result["context"] + "...")
    else:
        print("❌ 搜索成功但未找到匹配的代码上下文")

if __name__ == "__main__":
    # 直接运行此文件也可以测试
    test_code_search_flow()