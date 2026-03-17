import os
import importlib
from pathlib import Path

def load_all_tools():

    tool_dir = "tools"
    
    current_dir = Path(__file__).parent.resolve()
    
    tool_dir = current_dir
    for file in os.listdir(tool_dir):

        if file.endswith(".py") and file not in ["__init__.py", "base_tool.py"]:

            module_name = file[:-3]

            module = importlib.import_module(f"tools.{module_name}")

            importlib.reload(module)