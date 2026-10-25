"""Deterministic UTF-8/LF submission export, validated before atomic replacement."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import tempfile

from src import config
from src.hygiene.validator import validate_labels, validate_submission_file


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_submission(path, labels, *, n_expected=config.TOTAL_FRAMES):
    labels = validate_labels(labels, n_expected)
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.stem + ".", suffix=".csv", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("frame,label\n")
            handle.writelines(f"{frame},{label}\n" for frame, label in enumerate(labels))
            handle.flush()
            os.fsync(handle.fileno())
        validation = validate_submission_file(Path(temporary), n_expected)
        digest = sha256_file(temporary)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return {"path": str(path), "sha256": digest, **validation}
