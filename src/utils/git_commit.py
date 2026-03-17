import subprocess


def git_commit(message="agent update"):

    subprocess.run(["git", "add", "."])
    subprocess.run(["git", "commit", "-m", message])

    return "commit created"