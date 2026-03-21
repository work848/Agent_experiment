import ast
import os
import networkx as nx
from typing import List, Dict, Any, Optional
from code_indexer.call_graph_visitor import CodeGraphVisitor
    
class ProjectGraphManager:
    def __init__(self):
        # 初始化一个有向图
        self.unified_graph = nx.DiGraph()

    # --- 来源 1：从 Interface 设计提取逻辑图 ---
    def build_logical_graph(self, plan: List[Dict[str, Any]]):
        """
        根据 Planner 和 Interface Node 的设计建立逻辑图
        """
        for step in plan:
            step_id = step.get("id")
            interface = step.get("interface")
            
            # 添加节点，标记为“计划中”
            self.unified_graph.add_node(step_id, label=step.get("description"), status="planned")
            
            if interface and "dependencies" in interface:
                for dep_id in interface["dependencies"]:
                    # 建立逻辑依赖边 (A 依赖 B)
                    self.unified_graph.add_edge(step_id, dep_id, type="dependency_logic")

    # --- 来源 2：从实际代码提取物理图 ---
    def build_actual_graph(self, workspace_root: str):
        """
        使用 AST 扫描源码，纯粹地提取当前代码的实际调用关系。
        节点 ID 直接使用代码中的函数名/方法名。
        """
        visitor = CodeGraphVisitor()

        # 1. 遍历并解析工作区代码
        for root, dirs, files in os.walk(workspace_root):
            # 过滤无关目录
            dirs[:] = [d for d in dirs if d not in ('.git', '__pycache__', 'venv', '.env', 'node_modules')]
            
            for file in files:
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    relative_path = os.path.relpath(os.path.join(root, file), workspace_root)
                    module_path = relative_path.replace(os.sep, '.').rstrip('.py')
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            tree = ast.parse(f.read(), filename=file_path)
                            visitor = CodeGraphVisitor(module_prefix=module_path)
                            visitor.visit(tree)
                    except SyntaxError:
                        pass # 忽略语法错误的半成品文件
                    except Exception as e:
                        print(f"[Warning] 读取 {file_path} 失败: {e}")

        # 2. 将物理代码节点和边灌入统一图
        for node_id in visitor.nodes:
            if not self.unified_graph.has_node(node_id):
                # source="code" 明确标记这是来自真实代码的节点
                self.unified_graph.add_node(node_id, status="existing", source="code")

        for caller, callee in visitor.edges:
            # 添加物理调用边
            self.unified_graph.add_edge(caller, callee, type="actual_call")

    # --- 核心功能：双图对比分析 ---
    def get_analysis_report(self) -> Dict:
        """
        对比逻辑图和实际图，找出差异
        """
        report = {
            "missing_implementations": [],  # 计划了但代码里还没写的
            "unplanned_calls": [],         # 代码里写了但计划里没声明的（私自乱调）
            "bottlenecks": []              # 被依赖最多的核心节点
        }
        
        # 逻辑示例：
        for u, v, data in self.unified_graph.edges(data=True):
            if data.get("type") == "dependency_logic":
                # 如果逻辑上有依赖，但实际代码没产生调用
                # 这里可以进行复杂的匹配逻辑
                pass
                
        return report

    # --- 核心功能：拓扑排序（给 Agent 导航） ---
    def get_writing_sequence(self) -> List[str]:
        """
        计算最科学的编写顺序：先写被依赖最多的底层工具
        """
        try:
            # 拓扑排序返回一个列表，例如 [1, 2, 4, 3]
            # 顺序是：先写 1, 2，最后写 3
            return list(nx.topological_sort(self.unified_graph))
        except nx.NetworkXUnfeasible:
            # 如果出现循环依赖，这里会报错，提醒 Inspector 检查架构
            return []