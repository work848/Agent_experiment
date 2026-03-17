from tools.base_tool import tool
import subprocess


@tool
def auto_commit(message="agent update"):
    """In state machine,if step success marked as success. git commit will be executed.
    Args:        message (str): The commit message to use for the git commit. Defaults to "agent update.
    Returns:        None
    """
    try:

        subprocess.run(["git", "add", "."], check=True)

        subprocess.run(
            ["git", "commit", "-m", message],
            check=False
        )

    except Exception:
        pass

@tool
def git_rollback():
    """Rollbackroll to last successful step in the git repository.
    Returns:        str: A message indicating the success or failure of the rollback.
    """
    try:
        subprocess.run(
            ["git", "reset", "--hard", "HEAD~1"],
            check=True
        )
        return "Rollback successful"

    except Exception as e:
        return f"Rollback failed: {str(e)}"