import os
import ast
from code_indexer.call_graph_visitor import CodeGraphVisitor


class WorkspaceIndexer:

    def __init__(self, workspace_root):

        self.workspace_root = workspace_root

        self.call_graph = []
        self.class_graph = {}
        self.function_index = {}

    def build(self):

        for root, dirs, files in os.walk(self.workspace_root):

            dirs[:] = [d for d in dirs if d not in (
                ".git", "__pycache__", "venv", ".env", "node_modules"
            )]

            for file in files:

                if not file.endswith(".py"):
                    continue

                file_path = os.path.join(root, file)

                relative_path = os.path.relpath(file_path, self.workspace_root)

                module_path = relative_path.replace(os.sep, ".").rstrip(".py")

                try:

                    with open(file_path, "r", encoding="utf-8") as f:

                        tree = ast.parse(f.read())

                        visitor = CodeGraphVisitor(
                            module_prefix=module_path,
                            file_path=relative_path
                        )

                        visitor.visit(tree)

                        self.call_graph.extend(visitor.call_edges)

                        self.function_index.update(visitor.function_index)

                        for k, v in visitor.class_graph.items():

                            if k not in self.class_graph:

                                self.class_graph[k] = v

                except SyntaxError:
                    pass

                except Exception as e:
                    print(f"[Warning] parse failed {file_path}: {e}")

        return {
            "call_graph": self.call_graph,
            "class_graph": self.class_graph,
            "function_index": self.function_index
        }