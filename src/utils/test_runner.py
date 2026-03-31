import subprocess
import sys
from dataclasses import dataclass


@dataclass
class TestRunResult:
    passed: bool
    output: str
    return_code: int


def run_pytest(test_file: str, workspace_root: str, timeout: int = 30) -> TestRunResult:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", test_file, "-v", "--tb=short"],
        cwd=workspace_root,
        capture_output=True,
        text=True,
        timeout=timeout + 5,
    )
    output = (result.stdout + result.stderr).strip()
    return TestRunResult(
        passed=result.returncode == 0,
        output=output,
        return_code=result.returncode,
    )
