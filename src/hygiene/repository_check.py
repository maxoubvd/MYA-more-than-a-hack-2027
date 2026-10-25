"""Check publication hygiene without opening or printing match data."""
from __future__ import annotations

import json
from pathlib import Path, PurePosixPath
import subprocess
import sys

from src import config


def issues_for_paths(root, paths):
    issues = []
    for name in paths:
        path = PurePosixPath(name)
        parts = path.parts
        if any(any(c in part for c in '<>:"\\|?*') or part.endswith((" ", ".")) for part in parts):
            issues.append(f"Windows-incompatible filename: {name}")
            continue
        suffix = path.suffix.lower()
        if (any(p in ("data", ".cache", ".venv", "__pycache__") for p in parts)
                or suffix in (".npz", ".parquet", ".mp4", ".avi", ".mov", ".zip", ".pyc")
                or ("BAR-ATH" in name and suffix in (".txt", ".xml", ".csv"))):
            issues.append(f"Private/generated asset must not be tracked: {name}")
        if suffix == ".ipynb":
            notebook = json.loads((Path(root) / name).read_text(encoding="utf-8"))
            if any(c.get("outputs") or c.get("execution_count") is not None or c.get("attachments")
                   for c in notebook["cells"]):
                issues.append(f"Notebook outputs/execution counts/attachments must be removed: {name}")
    return issues


def run():
    tracked = subprocess.run(["git", "-C", str(config.MYA_DIR), "ls-files", "-z"],
                             check=True, capture_output=True).stdout.decode("utf-8").split("\0")
    # Also inspect eligible untracked files so newly added notebooks cannot slip through.
    untracked = subprocess.run(["git", "-C", str(config.MYA_DIR), "ls-files", "--others", "--exclude-standard", "-z"],
                               check=True, capture_output=True).stdout.decode("utf-8").split("\0")
    issues = issues_for_paths(config.MYA_DIR, sorted(set(filter(None, tracked + untracked))))
    for issue in issues:
        print(issue)
    if not issues:
        print("Publication check passed: filenames, asset categories and notebook outputs")
    return not issues


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
