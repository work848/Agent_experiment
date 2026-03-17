import ast
from config.workspace_config import SKIP_FUNCTIONS

class CodeGraphVisitor(ast.NodeVisitor):

    def __init__(self, module_prefix="", file_path=""):

        self.module_prefix = module_prefix
        self.file_path = file_path

        self.current_function = None
        self.current_class = None

        # 输出
        self.call_edges = []
        self.class_graph = {}
        self.function_index = {}

        # 辅助信息
        self.imports = {}
        self.aliases = {}
        self.var_types = {}

    # -------------------------
    # import
    # -------------------------

    def visit_Import(self, node):

        for alias in node.names:

            name = alias.name
            asname = alias.asname or name

            self.aliases[asname] = name

    def visit_ImportFrom(self, node):

        module = node.module

        for alias in node.names:

            name = alias.name
            asname = alias.asname or name

            if module:
                self.imports[asname] = f"{module}.{name}"
            else:
                self.imports[asname] = name

    # -------------------------
    # class
    # -------------------------

    def visit_ClassDef(self, node):

        class_name = node.name

        full_class = f"{self.module_prefix}.{class_name}"

        if class_name not in self.class_graph:

            self.class_graph[class_name] = {
                "module": self.module_prefix,
                "methods": [],
                "inherits": []
            }

        # 继承关系
        for base in node.bases:

            if isinstance(base, ast.Name):

                self.class_graph[class_name]["inherits"].append(base.id)

        prev_class = self.current_class
        self.current_class = class_name

        self.generic_visit(node)

        self.current_class = prev_class

    # -------------------------
    # function
    # -------------------------

    def visit_FunctionDef(self, node):

        if self.current_class:

            func_name = f"{self.module_prefix}.{self.current_class}.{node.name}"

            self.class_graph[self.current_class]["methods"].append(node.name)

        else:

            func_name = f"{self.module_prefix}.{node.name}"

        # function index
        self.function_index[func_name] = {
            "file": self.file_path,
            "line": node.lineno
        }

        prev_function = self.current_function
        self.current_function = func_name

        self.generic_visit(node)

        self.current_function = prev_function

    # -------------------------
    # variable type inference
    # -------------------------

    def visit_Assign(self, node):

        if isinstance(node.value, ast.Call):

            if isinstance(node.value.func, ast.Name):

                class_name = node.value.func.id

                for target in node.targets:

                    if isinstance(target, ast.Name):

                        self.var_types[target.id] = class_name

        self.generic_visit(node)

    # -------------------------
    # call graph
    # -------------------------

    def visit_Call(self, node):
        if not self.current_function:
            self.generic_visit(node)
            return

        callee = None
        
        # 1. 处理属性调用 (obj.method)
        if isinstance(node.func, ast.Attribute):
            attr = node.func.attr
            # --- 激进过滤：如果是常见的内置方法名，直接扔掉 ---
            if attr in [
                "lower", "upper", "strip", "split", "join", "replace", # 字符串
                "append", "extend", "pop", "get", "items", "values",  # 容器
                "write", "read", "readlines", "close",               # 文件
                "abspath", "basename", "exists", "relpath", "dirname", "splitext" # 路径
            ]:
                self.generic_visit(node)
                return
                
            # 尝试构建完整路径
            if isinstance(node.func.value, ast.Name):
                obj = node.func.value.id
                if obj in self.var_types:
                    callee = f"{self.module_prefix}.{self.var_types[obj]}.{attr}"
                elif obj in self.imports:
                    callee = f"{self.imports[obj]}.{attr}"
                else:
                    # 如果只是 f.write() 这种，obj 是 f，由于没有类型，我们不记录它
                    # 除非它在 imports 里（如 os.path.abspath）
                    pass 
        
        # 2. 处理直接调用 (foo)
        elif isinstance(node.func, ast.Name):
            name = node.func.id
            # --- 过滤掉没有模块前缀的孤立函数 (通常是内置函数或本地没定义的函数) ---
            if name in SKIP_FUNCTIONS or name in ["min", "max", "enumerate", "open", "any"]:
                self.generic_visit(node)
                return
                
            if name in self.imports:
                callee = self.imports[name]
            else:
                # 只有当它确实是我们自己定义的函数时才记录
                # 暂时标记为当前模块前缀
                callee = f"{self.module_prefix}.{name}"

        # 3. 最终落库：只记录带有“业务路径”的调用
        if callee and "." in callee:
            # 排除掉掉常见的第三方库/系统库干扰
            if not callee.startswith(("os.", "sys.", "pathlib.", "builtins.", "json.")):
                self.call_edges.append((self.current_function, callee))

        self.generic_visit(node)