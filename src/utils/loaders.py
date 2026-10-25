"""Validated source-specific ingestion shared by notebooks and future pipelines.

No interpolation, team prediction, or training takes place here. Observed masks
mean finite delivered coordinates, not evidence that a ball is in play.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.source_policy import require_use
from src.preprocessing.atd_parser import (
    DataValidationError, child_text, local_name, parse_atd, parse_metadata, read_xml,
)
from src.preprocessing.cache_manager import (
    ARRAY_KEYS, inputs_unchanged, provenance, read_cache, write_cache,
)
from src.preprocessing.coordinates import to_metres


def _read_csv(path):
    try:
        return pd.read_csv(path)
    except (ValueError, pd.errors.ParserError, UnicodeError):
        raise DataValidationError("Malformed CSV (contents withheld)") from None


def load_ground_truth(path=None, public_window_only=False, *, purpose="diagnostic"):
    """Official public labels: exclusively a format/alignment/meaning diagnostic."""
    require_use("public_labels", purpose)
    table = _read_csv(Path(path or config.GT_PUBLIC_CSV))
    if (list(table.columns) != ["frame", "label"] or len(table) != config.TOTAL_FRAMES
            or not np.array_equal(table["frame"].to_numpy(), np.arange(config.TOTAL_FRAMES))
            or not table["label"].isin(config.LABELS).all()):
        raise DataValidationError("Invalid public label table")
    if public_window_only:
        start, end = config.PUBLIC_WINDOW_SPAN
        table = table[table["frame"].between(start, end)].reset_index(drop=True)
    table.attrs["allowed_use"] = "diagnostic_only"
    return table


def load_ground_truth_meta(path=None, *, purpose="diagnostic"):
    require_use("public_labels", purpose)
    with Path(path or config.GT_PUBLIC_META_JSON).open(encoding="utf-8") as handle:
        return json.load(handle)


def load_team_mapping(path=None, *, source="tactical"):
    spec = config.get_source(source)
    return parse_metadata(Path(path or spec.xml_path), spec.num_frames, spec.num_slots, config.FPS).team_mapping


def load_atd(source="tactical", max_frames=None, use_cache=True, save_cache=True,
             *, path=None, xml_path=None, cache_path=None):
    """Load a camera on ITS timeline, preserving the legacy dictionary interface.

    A preview still validates every input record, but allocates only max_frames
    rows and never reads/writes a full cache. Fingerprints hash complete inputs;
    caches with a different source, XML, content, dimensions or parser are misses.
    Normalised raw arrays and metric copies keep the native scalar speed. Missing speed is
    separate from missing x/y; missing data is never replaced by zero.
    """
    spec = config.get_source(source)
    txt_path = Path(path or spec.txt_path)
    xml_path = Path(xml_path or spec.xml_path)
    cache_path = Path(cache_path or spec.cache_path)
    if max_frames is not None and (type(max_frames) is not int or not 1 <= max_frames <= spec.num_frames):
        raise ValueError("max_frames must be an integer within the source range")
    signature = provenance(source, txt_path, xml_path, spec.num_frames, spec.num_slots)
    metadata = parse_metadata(xml_path, spec.num_frames, spec.num_slots, config.FPS)
    arrays = read_cache(cache_path, signature) if use_cache and max_frames is None else None
    cache_hit = arrays is not None
    if arrays is None:
        arrays = dict(zip(ARRAY_KEYS, parse_atd(txt_path, spec.num_frames, spec.num_slots, max_frames=max_frames)))
        inputs_unchanged(signature)
        if save_cache and max_frames is None:
            write_cache(cache_path, arrays, signature)
    inputs_unchanged(signature)
    players, ball = arrays["players"], arrays["ball"]
    return {**arrays, "team_mapping": metadata.team_mapping, "source": source,
            "speed_unit": metadata.speed_unit,
            "speed_documentation_conflict": metadata.speed_unit != "m/s",
            "players_observed": np.isfinite(players[..., :2]).all(axis=-1),
            "ball_observed": np.isfinite(ball[..., :2]).all(axis=-1),
            "players_speed_observed": np.isfinite(players[..., 2]),
            "ball_speed_observed": np.isfinite(ball[..., 2]),
            "players_metres": to_metres(players), "ball_metres": to_metres(ball),
            "provenance": signature, "cache_hit": cache_hit,
            "complete": max_frames is None or max_frames == spec.num_frames}


# Compatibility for previous callers; all parsing now uses the strict module.
def _parse_raw_atd_file(file_path, num_frames, num_slots=config.NUM_SLOTS):
    return parse_atd(file_path, num_frames, num_slots)


def load_homography(source="tactical", path=None):
    """Return (H, error_pixels, valid, table), indexed by exact zero-based frame.

    Valid matrices must be finite and invertible. Invalid rows must explicitly
    carry nine NaNs. Negative delivered errors are retained in the raw table,
    marked unavailable, and returned as NaN (never as trustworthy low errors).
    """
    spec = config.get_source(source)
    table = _read_csv(Path(path or spec.homography_path))
    matrix_cols = [f"h{r}{c}" for r in range(3) for c in range(3)]
    required = ["frame", *matrix_cols, "reprojection_error", "valid"]
    if any(c not in table for c in required):
        raise DataValidationError("Homography is missing required columns")
    if len(table) != spec.num_frames or not np.array_equal(table["frame"], np.arange(spec.num_frames)):
        raise DataValidationError("Homography frame count/order/alignment mismatch")
    if not table["valid"].isin([0, 1]).all():
        raise DataValidationError("Homography valid flag must be 0 or 1, never missing")
    try:
        matrices = table[matrix_cols].to_numpy(dtype=np.float64).reshape(-1, 3, 3)
        errors = table["reprojection_error"].to_numpy(dtype=np.float64)
    except (TypeError, ValueError):
        raise DataValidationError("Non-numeric homography coefficients/errors") from None
    valid = table["valid"].to_numpy(dtype=bool)
    if (not np.isfinite(matrices[valid]).all() or not np.isnan(matrices[~valid]).all()
            or np.isinf(errors).any()
            or not np.isfinite(errors[valid]).all()):
        raise DataValidationError("Homography coefficients/error disagree with validity")
    if valid.any() and (np.linalg.slogdet(matrices[valid])[0] == 0).any():
        raise DataValidationError("Valid homography matrix is singular")
    table["reprojection_error_observed"] = np.isfinite(errors) & (errors >= 0)
    table.attrs["negative_error_count"] = int((errors < 0).sum())
    errors = np.where(errors >= 0, errors, np.nan)
    return matrices, errors, valid, table


def load_smart_tagging(path=None, fps=config.FPS, *, num_frames=None):
    """SportsCode intervals [start_frame,end_frame), using nearest frame (half up).

    Group names are casefolded for lookup, raw names/values and unknown fields
    remain in raw_tags. N/A stays N/A and never becomes an invented team.
    Duplicate groups are retained as lists, ambiguous semantic groups fail.
    """
    if not np.isfinite(fps) or fps <= 0:
        raise ValueError("fps must be positive and finite")
    num_frames = config.TOTAL_FRAMES if num_frames is None else num_frames
    root = read_xml(Path(path or config.TACTICAL_SMART_TAGGING_XML))
    rows = []
    for index, instance in enumerate(e for e in root.iter() if local_name(e).casefold() == "instance"):
        try:
            start_s, end_s = float(child_text(instance, "start")), float(child_text(instance, "end"))
        except ValueError:
            raise DataValidationError(f"Smart Tagging interval {index}: invalid timestamps") from None
        if not np.isfinite([start_s, end_s]).all() or not 0 <= start_s < end_s <= num_frames / fps:
            raise DataValidationError(f"Smart Tagging interval {index}: invalid bounds")
        start, end = int(np.floor(start_s * fps + .5)), int(np.floor(end_s * fps + .5))
        if not 0 <= start < end <= num_frames:
            raise DataValidationError(f"Smart Tagging interval {index}: empty/out-of-range frame interval")
        tags, normalised = {}, {}
        for label in instance:
            if local_name(label).casefold() != "label":
                continue
            group, text = child_text(label, "group"), child_text(label, "text")
            if not group:
                raise DataValidationError(f"Smart Tagging interval {index}: missing group")
            if group in tags:
                tags[group] = tags[group] + [text] if isinstance(tags[group], list) else [tags[group], text]
            else:
                tags[group] = text
            key = group.casefold()
            if key in normalised and key in ("team", "half", "type"):
                raise DataValidationError(f"Smart Tagging interval {index}: ambiguous semantic group")
            normalised[key] = text
        team = normalised.get("team")
        team_code = {"barcelona": "H", "fc barcelona": "H", "atletic club": "A", "athletic club": "A"}.get((team or "").casefold())
        rows.append({"code": child_text(instance, "code").upper(), "start_s": start_s, "end_s": end_s,
                     "start_frame": start, "end_frame": end, "duration_s": end_s - start_s,
                     "duration_frames": end - start, "team": team, "team_code": team_code,
                     "half": normalised.get("half"), "phase_type": normalised.get("type"),
                     "raw_tags": tags, "normalised_tags": normalised})
    columns = ["code", "start_s", "end_s", "start_frame", "end_frame", "duration_s", "duration_frames",
               "team", "team_code", "half", "phase_type", "raw_tags", "normalised_tags"]
    result = pd.DataFrame(rows, columns=columns)
    result.attrs["interval_convention"] = "[start_frame,end_frame)"
    result.attrs["unknown_team_count"] = sum(row["team_code"] is None for row in rows)
    return result
