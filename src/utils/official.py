"""Import the local official scorer only at the reviewed, pinned revision."""
from __future__ import annotations

import importlib
from pathlib import Path
import subprocess
import sys

from src import config


def check_official_revision():
    expected = (config.MYA_DIR / "official-revision.txt").read_text(encoding="ascii").strip()
    revision = subprocess.run(["git", "-C", str(config.CHALLENGE_DIR), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    if revision != expected:
        raise RuntimeError("Official repository revision differs from official-revision.txt")
    # The revision alone does not detect local edits of the scorer/rules/constants.
    dirty = subprocess.run(["git", "-C", str(config.CHALLENGE_DIR), "status", "--porcelain",
                            "--", "evaluation", "games.py", "RULES.md", "FAQ.md", "DATA.md", "EVALUATION.md"],
                           capture_output=True, text=True, check=True).stdout
    if dirty.strip():
        raise RuntimeError("Official scorer/reference documents contain unreviewed changes")
    return revision


def load_official_metrics():
    check_official_revision()
    for folder in (config.CHALLENGE_DIR, config.EVAL_DIR):
        if str(folder) not in sys.path:
            sys.path.insert(0, str(folder))
    module = importlib.import_module("possession_metrics")
    if Path(module.__file__).resolve() != (config.EVAL_DIR / "possession_metrics.py").resolve():
        raise RuntimeError("A different possession_metrics module is already imported")
    return module
