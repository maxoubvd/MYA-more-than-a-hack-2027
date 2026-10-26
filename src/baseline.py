"""No training: metric nearest player, then the official H/A-only majority rule.

This deliberately inherits the reference's weak missing-ball -> D assumption.
That is a documented baseline hypothesis, never a sensor validity fact. An
explicit X alternative is available, with no public-score-based selection.
"""
from __future__ import annotations

import numpy as np

from src import config
from src.hygiene.masking import apply_official_masks, checked_intervals
from src.hygiene.validator import validate_labels

DEFAULT_HALF_WIDTH = 50  # Published official reference, fixed BEFORE public diagnostics.


def nearest_team_labels(players, ball, team_mapping, *, missing_label="D", batch_size=8192, pitch_dims=config.PITCH_DIMS):
    """Nearest finite x/y in metres; exact distance ties use the first XML slot.

    Speeds are never used. Input is the original normalised representation from
    the strict ATD loader. No coordinate fill, distance threshold or learned label.
    """
    players, ball = np.asarray(players), np.asarray(ball)
    if (players.ndim != 3 or players.shape[-1] != 3 or players.shape[1] == 0
            or ball.shape != (players.shape[0], 3)):
        raise ValueError("Expected players (N,S,3) and ball (N,3)")
    if missing_label not in ("D", "X") or type(batch_size) is not int or batch_size <= 0:
        raise ValueError("Expected missing_label D/X and positive batch size")
    slots = players.shape[1]
    if set(team_mapping) != set(range(slots)) or any(team_mapping[i] not in ("H", "A") for i in range(slots)):
        raise ValueError("A complete XML H/A team mapping is required")
    teams = np.asarray([team_mapping[i] for i in range(slots)])
    result = np.full(len(ball), missing_label, dtype="<U1")
    scale = np.asarray(pitch_dims, dtype=np.float64)
    if scale.shape != (2,) or not np.isfinite(scale).all() or (scale <= 0).any():
        raise ValueError("Pitch dimensions must be two positive finite metre values")
    for start in range(0, len(ball), batch_size):
        end = min(start + batch_size, len(ball))
        positions = players[start:end, :, :2].astype(np.float64)
        ball_positions = ball[start:end, :2].astype(np.float64)
        if np.isinf(positions).any() or np.isinf(ball_positions).any():
            raise ValueError("Infinite positions are not missing observations")
        observed = np.isfinite(positions).all(axis=-1) & np.isfinite(ball_positions).all(axis=-1)[:, None]
        delta = (positions - ball_positions[:, None, :]) * scale
        distances = np.sum(delta * delta, axis=-1)
        distances[~observed] = np.inf
        nearest = np.argmin(distances, axis=1)
        supported = observed.any(axis=1)
        part = result[start:end]
        part[supported] = teams[nearest[supported]]
    return result


def majority_vote(labels, half_width=DEFAULT_HALF_WIDTH, *, missing_label="D"):
    """Official centred +/- half_width vote: H/A only, tie -> H, no votes -> D/X.

    half_width=50 means up to 101 frames, not a 50-frame-wide window. At zero
    preserve each raw label. This function handles one continuous period.
    """
    labels = validate_labels(labels)
    if type(half_width) is not int or half_width < 0 or missing_label not in ("D", "X"):
        raise ValueError("Expected a nonnegative integer half-width and missing_label D/X")
    if half_width == 0 or not len(labels):
        return labels.copy()
    index = np.arange(len(labels))
    low = np.maximum(0, index - half_width)
    high = np.minimum(len(labels), index + half_width + 1)
    home_prefix = np.r_[0, np.cumsum(labels == "H")]
    away_prefix = np.r_[0, np.cumsum(labels == "A")]
    home, away = home_prefix[high] - home_prefix[low], away_prefix[high] - away_prefix[low]
    result = np.full(len(labels), missing_label, dtype="<U1")
    supported = home + away > 0
    result[supported] = np.where(home[supported] >= away[supported], "H", "A")
    return result


def predict_baseline(atd, *, half_width=DEFAULT_HALF_WIDTH, missing_label="D",
                     intervals=config.EVALUATED_INTERVALS, dead_zone=config.DEAD_ZONE_2HT_INTERVAL):
    """Prediction without labels; period heads cannot inherit the previous half.

    Beginning of a period: use only that period's available centred window. If
    none has a supported H/A observation, emit the explicit missing_label policy.
    """
    if atd.get("source") != "tactical" or not atd.get("complete", False):
        raise ValueError("A complete tactical source is required for a submission")
    n_frames = len(atd["ball"])
    if not np.array_equal(atd["video_frames"], np.arange(n_frames)):
        raise ValueError("Tracking is not aligned to zero-based video frames")
    raw = nearest_team_labels(atd["players"], atd["ball"], atd["team_mapping"], missing_label=missing_label)
    raw = apply_official_masks(raw, intervals=intervals, dead_zone=dead_zone)
    result = np.full(n_frames, "X", dtype="<U1")
    for start, end in checked_intervals(n_frames, intervals):
        result[start:end] = majority_vote(raw[start:end], half_width, missing_label=missing_label)
    return apply_official_masks(result, intervals=intervals, dead_zone=dead_zone)
