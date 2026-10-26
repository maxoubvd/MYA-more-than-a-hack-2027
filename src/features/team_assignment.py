"""Observation-only schema shared by tactical ATD and external inputs."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from src.utils.external_data import ExternalInputs
from src.preprocessing.atd_parser import child_text, local_name, read_xml


@dataclass(frozen=True)
class FeatureInputs:
    players_xy: np.ndarray
    ball_xy: np.ndarray
    team_mapping: np.ndarray
    frame_ids: np.ndarray
    period_ids: np.ndarray
    fps: float
    pitch_dims: tuple[float, float]

    def validate(self):
        p, b = np.asarray(self.players_xy), np.asarray(self.ball_xy)
        if p.ndim != 3 or p.shape[-1] != 2 or p.shape[1] == 0 or len(p)==0 or b.shape != (len(p), 2):
            raise ValueError("Expected players (N,S,2) and ball (N,2)")
        if np.asarray(self.team_mapping).shape != (p.shape[1],) or not np.isin(self.team_mapping, ["H", "A"]).all():
            raise ValueError("Complete H/A slot mapping required")
        if np.isinf(p).any() or np.isinf(b).any():
            raise ValueError("Infinite coordinates are not missing observations")
        if (not np.isfinite(self.fps) or self.fps <= 0 or len(self.pitch_dims) != 2
                or not np.isfinite(self.pitch_dims).all() or min(self.pitch_dims) <= 0):
            raise ValueError("Invalid cadence or pitch dimensions")
        periods = np.asarray(self.period_ids)
        frames = np.asarray(self.frame_ids)
        if periods.shape != (len(p),) or frames.shape != (len(p),) or not np.issubdtype(frames.dtype, np.integer):
            raise ValueError("Invalid feature timeline")
        if not np.issubdtype(periods.dtype, np.integer) or (periods < 0).any():
            raise ValueError("Periods must be nonnegative integer identifiers")
        for start, end in period_runs(periods):
            if not (np.diff(frames[start:end]) == 1).all():
                raise ValueError("Missing complete frames inside a feature period")
        return self


def period_runs(period_ids):
    ids = np.asarray(period_ids)
    if ids.ndim != 1:
        raise ValueError("Expected one-dimensional period IDs")
    edges = np.r_[0, np.flatnonzero(ids[1:] != ids[:-1]) + 1, len(ids)]
    result = [(int(a), int(b)) for a, b in zip(edges[:-1], edges[1:]) if b > a and ids[a] > 0]
    keys = [int(ids[a]) for a, _ in result]
    if len(keys) != len(set(keys)):
        raise ValueError("A period may not reappear after a boundary")
    return result


def from_external(inputs):
    if not isinstance(inputs, ExternalInputs):
        raise TypeError("External features accept ExternalInputs only, never target containers")
    return FeatureInputs(inputs.players_xy_normalized, inputs.ball_xy_normalized,
                         inputs.team_mapping, inputs.frame_ids, inputs.period_ids,
                         inputs.fps, inputs.pitch_dims).validate()


def from_tactical(atd, *, intervals, fps, pitch_dims):
    if atd.get("source") != "tactical" or not atd.get("complete"):
        raise ValueError("Complete tactical ATD required")
    n, slots = atd["players"].shape[:2]
    periods = np.zeros(n, dtype=np.int8)
    previous = 0
    for period, (start, end) in enumerate(intervals, 1):
        if not 0 <= previous <= start < end <= n:
            raise ValueError("Invalid tactical periods")
        periods[start:end] = period
        previous = end
    if set(atd["team_mapping"]) != set(range(slots)):
        raise ValueError("Incomplete tactical team mapping")
    return FeatureInputs(atd["players"][..., :2], atd["ball"][..., :2],
        np.array([atd["team_mapping"][i] for i in range(slots)]), atd["video_frames"],
        periods, fps, pitch_dims).validate()


def attack_directions_from_xml(path):
    """First-half provider metadata; opposite second half per Kloppy EPTS convention.

    Only projections along the attack axis are produced. Raw positions and both
    velocity components remain in their original coordinate frame.
    """
    root = read_xml(path)
    result = {}
    team_names = {"barcelona": "H", "fc barcelona": "H", "atletic club": "A", "athletic club": "A"}
    for team in (e for e in root.iter() if local_name(e) == "Team"):
        label = team_names.get(child_text(team, "Name").casefold())
        if label is None:
            continue
        params = {child_text(p, "Name").casefold(): child_text(p, "Value").casefold()
                  for p in team.iter() if local_name(p) == "ProviderParameter"}
        first = {"left_to_right": 1., "right_to_left": -1.}.get(params.get("attack_direction_first_half"))
        second = {"left_to_right": 1., "right_to_left": -1.}.get(params.get("attack_direction_second_half"))
        if first is not None:
            result[(1, label)] = first
            result[(2, label)] = -first if second is None else second
    return result
