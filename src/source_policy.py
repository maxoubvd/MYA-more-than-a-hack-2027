"""Explicit source/use separation. Public match labels are diagnostics only."""
from __future__ import annotations

import json
from pathlib import Path

from src import config

USES = {"pipeline", "diagnostic", "training", "calibration", "selection", "external_validation"}


def load_registry(path=None):
    with Path(path or config.MYA_DIR / "docs" / "sources.json").open(encoding="utf-8") as handle:
        registry = json.load(handle)
    for source in registry["sources"]:
        validate_source(source)
    return registry


def validate_source(source):
    required = {"id", "match", "origin", "version", "rights", "nature", "allowed_uses", "local_path"}
    if not required <= source.keys() or not source["allowed_uses"] or not set(source["allowed_uses"]) <= USES:
        raise ValueError("Incomplete/invalid source registration")
    if source["match"] == config.GAME and source["nature"] == "human":
        if source["id"] != "public_labels" or set(source["allowed_uses"]) != {"diagnostic"}:
            raise PermissionError("Human labels for the competition match are forbidden, except official diagnostics")
    if "external_validation" in source["allowed_uses"] and source["match"] == config.GAME:
        raise PermissionError("External validation must concern other matches")


def require_use(source_id, purpose, *, registry=None):
    if purpose not in USES:
        raise ValueError("Unknown source purpose")
    registry = registry or load_registry()
    source = next((s for s in registry["sources"] if s["id"] == source_id), None)
    if source is None:
        raise PermissionError("Unregistered source")
    validate_source(source)
    if purpose not in source["allowed_uses"]:
        raise PermissionError(f"Source {source_id} is not authorised for {purpose}")
    return source
