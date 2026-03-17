import os
import ast
from typing import List

def get_workspace_skeleton_direct(root: str, ignore_dirs: List[str] = None) -> str:
    """
    直接扫描目录并生成大纲字符串。
    不依赖 Workspace 模型，不存储源码，内存占用极低。
    """
    if ignore_dirs is None:
        ignore_dirs = {".git", "__pycache__", "venv", ".venv", "node_modules"}
    
    skeleton_lines = ["### Project Architecture Skeleton ###\n"]
    
    for dirpath, dirnames, filenames in os.walk(root):
        # 排除不需要扫描的目录
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
        
        rel_dir = os.path.relpath(dirpath, root)
        if rel_dir == ".":
            rel_dir = ""

        for f in filenames:
            if not f.endswith(".py"):
                continue
            
            file_path = os.path.join(dirpath, f)
            display_path = os.path.join(rel_dir, f)
            skeleton_lines.append(f"📄 File: {display_path}")
            
            try:
                with open(file_path, "r", encoding="utf-8") as file:
                    tree = ast.parse(file.read())
                
                for node in ast.iter_child_nodes(tree):
                    # 提取类及其方法
                    if isinstance(node, ast.ClassDef):
                        doc = (ast.get_docstring(node) or "").split('\n')[0]
                        methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                        methods_str = f" (Methods: {', '.join(methods)})" if methods else ""
                        skeleton_lines.append(f"  🏛️ class {node.name}{methods_str} | {doc}")
                    
                    # 提取全局函数
                    elif isinstance(node, ast.FunctionDef):
                        args = [a.arg for a in node.args.args]
                        doc = (ast.get_docstring(node) or "").split('\n')[0]
                        skeleton_lines.append(f"  λ def {node.name}({', '.join(args)}) | {doc}")
                        
            except Exception as e:
                skeleton_lines.append(f"  ⚠️ Error parsing file: {e}")
            
            skeleton_lines.append("") # 文件间空行

    return "\n".join(skeleton_lines)