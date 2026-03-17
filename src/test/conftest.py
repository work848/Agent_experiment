# src/test/conftest.py
import pytest
import shutil
import os
from config.workspace_config import WORKSPACE

@pytest.fixture(scope="function", autouse=True)
def manage_workspace():
    """
    scope="function": 每个测试函数运行前都会清理一次（最安全）
    autouse=True: 每个测试函数都会自动执行，不需要手动传参
    """
    # Setup: 准备环境
    if os.path.exists(WORKSPACE):
        shutil.rmtree(WORKSPACE)
    os.makedirs(WORKSPACE, exist_ok=True)

    yield  # 暂停，去跑具体的测试函数

    # Teardown: 清理现场
    if os.path.exists(WORKSPACE):
        shutil.rmtree(WORKSPACE)