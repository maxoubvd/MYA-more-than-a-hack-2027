"""Describe missing observations offline, separately inside each period."""
from __future__ import annotations

import numpy as np
from src.features.team_assignment import period_runs


def gap_features(observed, period_ids, fps):
    observed = np.asarray(observed, dtype=bool)
    if observed.shape != np.asarray(period_ids).shape or not np.isfinite(fps) or fps <= 0:
        raise ValueError("Invalid gap input")
    output = {name: np.full(len(observed), np.nan, dtype=np.float32) for name in
              ("gap_duration_s", "since_observation_s", "until_observation_s", "gap_left_censored", "gap_right_censored")}
    last_index = np.full(len(observed), -1, dtype=np.int32)
    gaps = []
    for start, end in period_runs(period_ids):
        values = observed[start:end]
        index = np.arange(end-start)
        previous = np.maximum.accumulate(np.where(values, index, -1))
        following = np.minimum.accumulate(np.where(values, index, len(index))[::-1])[::-1]
        output["since_observation_s"][start:end] = np.where(previous >= 0, (index-previous)/fps, np.nan)
        output["until_observation_s"][start:end] = np.where(following < len(index), (following-index)/fps, np.nan)
        last_index[start:end] = np.where(previous >= 0, previous+start, -1)
        for key in ("gap_duration_s", "gap_left_censored", "gap_right_censored"):
            output[key][start:end] = 0
        edges = np.diff(np.r_[False, ~values, False].astype(np.int8))
        for left, right in zip(np.flatnonzero(edges==1), np.flatnonzero(edges==-1)):
            output["gap_duration_s"][start+left:start+right] = (right-left)/fps
            output["gap_left_censored"][start+left:start+right] = float(left==0)
            output["gap_right_censored"][start+left:start+right] = float(right==len(index))
            gaps.append({"start_index": int(start+left), "end_index": int(start+right),
                         "period_id": int(period_ids[start]), "length_frames": int(right-left),
                         "left_censored": bool(left==0), "right_censored": bool(right==len(index))})
    return output, last_index, gaps
