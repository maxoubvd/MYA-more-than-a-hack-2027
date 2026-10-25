"""Content-addressed provenance and atomic caches. Match derivatives stay local."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile

import numpy as np

from src.preprocessing.atd_parser import PARSER_VERSION

CACHE_SCHEMA = 1
ARRAY_KEYS = ("players", "ball", "frame_ids", "video_frames")


def fingerprint(path: Path):
    path = Path(path).resolve()
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("Input changed while fingerprinting")
    return {"path": str(path), "size": after.st_size, "mtime_ns": after.st_mtime_ns, "sha256": digest.hexdigest()}


def provenance(source, txt_path, xml_path, num_frames, num_slots):
    return {"cache_schema": CACHE_SCHEMA, "parser_version": PARSER_VERSION,
            "source": source, "num_frames": num_frames, "num_slots": num_slots,
            "coordinates": "original normalized x/y; scalar speed unchanged (XML unit); video_frame=frame_id-1",
            "inputs": {"atd": fingerprint(txt_path), "xml": fingerprint(xml_path)}}


def inputs_unchanged(metadata):
    for signature in metadata["inputs"].values():
        current = Path(signature["path"]).stat()
        if (current.st_size, current.st_mtime_ns) != (signature["size"], signature["mtime_ns"]):
            raise RuntimeError("Input changed during ingestion; result discarded")


def validate_arrays(arrays, num_frames, num_slots):
    if set(arrays) != set(ARRAY_KEYS):
        raise ValueError("Incomplete cache arrays")
    for key, shape in (("players", (num_frames, num_slots, 3)), ("ball", (num_frames, 3))):
        if arrays[key].shape != shape or arrays[key].dtype != np.float32 or np.isinf(arrays[key]).any():
            raise ValueError("Invalid cached tracking dimensions/dtype/values")
    for key, start in (("frame_ids", 1), ("video_frames", 0)):
        value = arrays[key]
        if value.dtype != np.int32 or not np.array_equal(value, np.arange(start, num_frames + start)):
            raise ValueError("Invalid cached frame alignment")


def read_cache(path, expected):
    """Old, stale, corrupt, or incomplete caches are misses; never allow pickle."""
    try:
        with np.load(path, allow_pickle=False) as archive:
            if set(archive.files) != set(ARRAY_KEYS) | {"metadata"}:
                return None
            if json.loads(str(archive["metadata"].item())) != expected:
                return None
            arrays = {key: archive[key] for key in ARRAY_KEYS}
        validate_arrays(arrays, expected["num_frames"], expected["num_slots"])
        return arrays
    except (OSError, ValueError, KeyError, EOFError, zipfile.BadZipFile):
        return None


def write_cache(path, arrays, metadata):
    validate_arrays(arrays, metadata["num_frames"], metadata["num_slots"])
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.stem + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            np.savez_compressed(handle, **arrays, metadata=np.array(json.dumps(metadata, sort_keys=True)))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
