import os
from config.workspace_config import WORKSPACE
from tools.base_tool import tool

@tool
def search_code(query: str, max_results: int = 5) -> str:
    """
    Search code in the workspace.

    Args:
        query: keyword to search
        max_results: maximum number of results

    Returns:
        matched code snippets
    """

    results = []

    for root, dirs, files in os.walk(WORKSPACE):

        for file in files:

            if not file.endswith((".py", ".js", ".ts", ".java", ".cpp", ".go")):
                continue

            path = os.path.join(root, file)

            try:
                with open(path, "r", encoding="utf-8") as f:

                    lines = f.readlines()

                    for i, line in enumerate(lines):

                        if query.lower() in line.lower():

                            start = max(i - 3, 0)
                            end = min(i + 3, len(lines))

                            snippet = "".join(lines[start:end])

                            results.append(
                                f"""
                                FILE: {path}
                                LINE: {i+1}

                                {snippet}
                                """
                            )

                            if len(results) >= max_results:
                                return "\n".join(results)

            except:
                pass

    if not results:
        return "No matches found."

    return "\n".join(results)