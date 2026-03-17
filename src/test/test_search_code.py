import os
import shutil
from tools.search_code import search_code
from config.workspace_config import WORKSPACE

def setup_module():
    """测试前准备：清理并创建测试工作区"""
    if os.path.exists(WORKSPACE):
        shutil.rmtree(WORKSPACE)
    os.makedirs(WORKSPACE)

def test_search_code_basic():
    """测试基本搜索功能和代码片段截取"""
    path = os.path.join(WORKSPACE, "logic.py")
    content = [
        "import os\n",
        "def find_me():\n",        # 第 2 行 (索引 1)
        "    print('target')\n",   # 第 3 行 (索引 2) - 关键词在这里
        "    return True\n",
        "def other():\n",
        "    pass\n"
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.writelines(content)

    result = search_code("target")
    
    # 验证返回格式
    assert "FILE:" in result
    assert "LINE: 3" in result
    assert "print('target')" in result
    assert "def find_me()" in result  # 验证是否包含了上一行 (i-3 逻辑)

def test_search_code_max_results():
    """测试最大结果数限制"""
    # 创建 10 个包含关键词的文件
    for i in range(10):
        path = os.path.join(WORKSPACE, f"test_{i}.py")
        with open(path, "w") as f:
            f.write("keyword_here")

    # 限制只返回 3 个结果
    result = search_code("keyword_here", max_results=3)
    
    # 通过统计 "FILE:" 出现的次数来判断结果数量
    count = result.count("FILE:")
    assert count == 3

def test_search_code_unsupported_extension():
    """测试是否忽略了不支持的文件类型（如 .txt）"""
    path = os.path.join(WORKSPACE, "hidden.txt")
    with open(path, "w") as f:
        f.write("find_this_text")

    result = search_code("find_this_text")
    assert "No matches found." in result

def test_search_code_case_insensitive():
    """测试大小写不敏感搜索"""
    path = os.path.join(WORKSPACE, "upper.py")
    with open(path, "w") as f:
        f.write("HELLO_WORLD = 1")

    result = search_code("hello")  # 小写搜大写
    assert "HELLO_WORLD" in result