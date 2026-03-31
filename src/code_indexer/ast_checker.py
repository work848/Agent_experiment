import os
import ast
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ImplementationCheckResult:
    def __init__(self, found: bool, param_count_match: Optional[bool] = None, actual_params: Optional[list] = None, expected_params: Optional[int] = None, detail: str = ""):
        self.found = found
        self.param_count_match = param_count_match
        self.actual_params = actual_params or []
        self.expected_params = expected_params
        self.detail = detail

    def passed(self) -> bool:
        if not self.found:
            return False
        if self.param_count_match is False:
            return False
        return True


def check_if_implemented(file_path: str, interface_name: str) -> bool:
    """
    Check if a specific function, async function, or class exists in the AST of the target file.
    Args:
        file_path: Absolute path to the python file.
        interface_name: The name of the function or class to look for.
    Returns:
        True if the file exists and the specified definition exists inside it, False otherwise.
    """
    result = check_implementation_detail(file_path, interface_name)
    return result.found


def check_implementation_detail(file_path: str, interface_name: str, expected_param_count: Optional[int] = None) -> ImplementationCheckResult:
    """
    Check if a function exists and optionally validate its parameter count.
    Returns an ImplementationCheckResult with detailed findings.
    """
    if not os.path.exists(file_path):
        return ImplementationCheckResult(found=False, detail=f"File not found: {file_path}")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        tree = ast.parse(content)

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == interface_name:
                    # Count params excluding 'self'
                    actual_params = [a.arg for a in node.args.args if a.arg != "self"]
                    param_count_match = None
                    detail = f"Found {interface_name} with {len(actual_params)} param(s): {actual_params}"
                    if expected_param_count is not None:
                        param_count_match = len(actual_params) == expected_param_count
                        if not param_count_match:
                            detail = f"Found {interface_name} but param count mismatch: expected {expected_param_count}, got {len(actual_params)} ({actual_params})"
                    return ImplementationCheckResult(
                        found=True,
                        param_count_match=param_count_match,
                        actual_params=actual_params,
                        expected_params=expected_param_count,
                        detail=detail,
                    )
            if isinstance(node, ast.ClassDef):
                if node.name == interface_name:
                    return ImplementationCheckResult(found=True, detail=f"Found class {interface_name}")

        return ImplementationCheckResult(found=False, detail=f"{interface_name} not found in {file_path}")

    except SyntaxError as e:
        logger.warning(f"Syntax error while parsing {file_path}: {e}")
        return ImplementationCheckResult(found=False, detail=f"Syntax error: {e}")
    except Exception as e:
        logger.warning(f"Error checking implementation in {file_path}: {e}")
        return ImplementationCheckResult(found=False, detail=f"Error: {e}")
