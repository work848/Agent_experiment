import os
import ast
import logging

logger = logging.getLogger(__name__)

def check_if_implemented(file_path: str, interface_name: str) -> bool:
    """
    Check if a specific function, async function, or class exists in the AST of the target file.
    Args:
        file_path: Absolute path to the python file.
        interface_name: The name of the function or class to look for.
    Returns:
        True if the file exists and the specified definition exists inside it, False otherwise.
    """
    if not os.path.exists(file_path):
        return False
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            
        tree = ast.parse(content)
        
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == interface_name:
                    return True
                    
        return False
    except SyntaxError as e:
        logger.warning(f"Syntax error while parsing {file_path}: {e}")
        return False
    except Exception as e:
        logger.warning(f"Error checking implementation in {file_path}: {e}")
        return False
