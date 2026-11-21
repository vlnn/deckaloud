import subprocess
from pathlib import Path

SOURCES = "*.txt"
ADDED_FILE = "+++ b/"
ADDED_ID = "+id:"
ID_LINE = "id:"


def files_with_uncommitted_ids(root: Path) -> tuple[str, ...]:
    return tuple(sorted({*changed_files_with_new_ids(root), *untracked_files_with_ids(root)}))


def git_lines(root: Path, *args: str) -> list[str]:
    command = ["git", "-c", "core.quotepath=false", *args, "--", SOURCES]
    try:
        done = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8", check=False)
    except OSError:
        return []
    return done.stdout.splitlines() if done.returncode == 0 else []


def changed_files_with_new_ids(root: Path) -> set[str]:
    found = set()
    current = None
    for line in git_lines(root, "diff", "HEAD", "--unified=0", "--no-color", "--relative"):
        if line.startswith(ADDED_FILE):
            current = line.removeprefix(ADDED_FILE)
        elif line.startswith(ADDED_ID) and current:
            found.add(current)
    return found


def untracked_files_with_ids(root: Path) -> set[str]:
    untracked = git_lines(root, "ls-files", "--others", "--exclude-standard")
    return {name for name in untracked if has_ids(root / name)}


def has_ids(path: Path) -> bool:
    return any(line.startswith(ID_LINE) for line in path.read_text(encoding="utf-8-sig").splitlines())
