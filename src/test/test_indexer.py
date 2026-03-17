import os
import json
from code_indexer.work_space_indexer import WorkspaceIndexer
from search.code_search_engine import CodeSearchEngine
# 假设你的类定义在这些文件中
# from your_module import WorkspaceIndexer, CodeSearchEngine 

def test_indexing():
    target_path = r"C:\makeMoney\PersonalProject\Agent_project\src\tools"
    
    print(f"开始扫描路径: {target_path}")
    
    if not os.path.exists(target_path):
        print("错误: 路径不存在，请检查路径是否正确。")
        return

    # 1. 初始化索引器
    indexer = WorkspaceIndexer(target_path)
    
    # 2. 执行构建
    graph_data = indexer.build()
    
    # 3. 打印测试结果
    print("\n---  扫描结果汇总 ---")
    print(f"找到函数数量: {len(graph_data['function_index'])}")
    print(f"找到调用关系数量: {len(graph_data['call_graph'])}")
    
    print("\n--- 部分函数索引 (前5个) ---")
    for i, (name, info) in enumerate(graph_data['function_index'].items()):
        if i >= 20: break
        print(f"函数: {name} -> 文件: {info['file']}, 行号: {info['line']}")

    print("\n--- 部分调用关系 (前5个) ---")
    for i, edge in enumerate(graph_data['call_graph']):
        if i >= 30: break
        print(f"调用: {edge[0]} -> {edge[1]}")

    # 4. 验证数据完整性
    if len(graph_data['function_index']) > 0:
        print("\n 测试通过: 成功提取到代码结构数据！")
    else:
        print("\n 警告: 未提取到任何函数，请检查该目录下是否有合法的 .py 文件。")

if __name__ == "__main__":
    test_indexing()