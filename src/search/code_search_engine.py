import os
import ast

import re
from memory.chroma_client import embed_query, embed_texts
from config.workspace_config import SKIP_FUNCTIONS

class CodeSearchEngine:

    def __init__(self, chroma_collection, call_graph, function_index, workspace_root):

        self.collection = chroma_collection
        self.call_graph = call_graph
        self.function_index = function_index
        self.workspace_root = workspace_root

    # ------------------------------------------------
    # 读取函数代码
    # ------------------------------------------------

    def read_function_code(self, func_name):

        if func_name not in self.function_index:
            return None

        info = self.function_index[func_name]

        file_path = os.path.join(self.workspace_root, info["file"])
        start_line = info["line"]

        try:

            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            code = []

            for i in range(start_line - 1, len(lines)):

                line = lines[i]

                if i > start_line - 1 and line.startswith("def "):
                    break

                code.append(line)

            return "".join(code)

        except Exception:
            return None

    # ------------------------------------------------
    # 自动构建函数向量索引
    # ------------------------------------------------

    def build_vector_index(self):

        ids = []
        documents = []
        metadatas = []

        for func_name in self.function_index:
            base_name = func_name.split('.')[-1] # 只看函数名
            if base_name in SKIP_FUNCTIONS:
                continue
            
            code = self.read_function_code(func_name)

            if not code:
                continue

            ids.append(func_name)

            documents.append(code)

            metadatas.append({
                "function": func_name,
                "file": self.function_index[func_name]["file"]
            })

        if ids:

            embeddings = embed_texts(documents) 
            self.collection.add(
                ids=ids,
                documents=documents,
                embeddings=embeddings,  
                metadatas=metadatas
            )

    # ------------------------------------------------
    # Vector Search
    # ------------------------------------------------

    def vector_search(self, query, k=3):
        query_vector = embed_query(query)
        
        results = self.collection.query(
        query_embeddings=[query_vector], 
        n_results=k
    )

        return results["ids"][0]

    # ------------------------------------------------
    # Call Graph 扩展
    # ------------------------------------------------

    def expand_call_graph(self, functions, depth=1):

        related = set(functions)

        for _ in range(depth):

            new_nodes = set()

            for caller, callee in self.call_graph:
                # 过滤掉基础库函数
                if any(base in SKIP_FUNCTIONS for base in [caller.split('.')[-1], callee.split('.')[-1]]):
                    continue
                if callee in related:
                    new_nodes.add(caller)

                if caller in related:
                    new_nodes.add(callee)

            related |= new_nodes

        return list(related)

    # ------------------------------------------------
    # 获取代码 context
    # ------------------------------------------------

    def get_code_context(self, functions, max_functions=8):

        context = []

        for func in functions[:max_functions]:

            code = self.read_function_code(func)

            if code:

                context.append(
                    f"\n# Function: {func}\n{code}\n"
                )

        return "\n".join(context)

    # ------------------------------------------------
    # 主查询
    # ------------------------------------------------

    def search(self, query):
        # 1. --- 提取 Query 中的潜在函数名 (硬匹配准备) ---
        # 比如从 "def search_code(...)" 提取出 "search_code"
        match = re.search(r'def\s+([a-zA-Z_0-9]+)', query)
        potential_name = match.group(1) if match else query.strip("(): ").lower()
        
        hard_matches = []
        # 如果函数索引里有包含这个名字的 Key，直接列为一类匹配
        for full_name in self.function_index:
            short_name = full_name.split('.')[-1]
            if potential_name == short_name or potential_name in full_name:
                hard_matches.append(full_name)

        # 2. --- 向量搜索 ---
        vector_results = self.vector_search(query, k=5)

        # 3. --- 合并与置顶 ---
        # 逻辑：硬匹配到的函数排在最前面，然后是向量搜索的结果
        combined_results = []
        seen = set()
        
        for func in (hard_matches + vector_results):
            if func not in seen:
                combined_results.append(func)
                seen.add(func)

        # 4. --- 截断并获取上下文 ---
        # 只取最相关的 3 个，防止上下文爆炸
        final_functions = combined_results[:3]
        
        # 5. --- 扩展调用链 (之前已经清理得很干净了) ---
        expanded = self.expand_call_graph(final_functions, depth=1)
        
        context = self.get_code_context(expanded)
        
        return {
            "functions": expanded,
            "context": context
        }