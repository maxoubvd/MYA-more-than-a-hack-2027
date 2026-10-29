"""Exact path-only Viterbi for independent experiments evaluated in one loop.

Candidates are independent. Scores and tie-breaking match the reference decoder.
Uncertainty profiles remain available in the final inference path.
"""
import numpy as np
from src.features.team_assignment import period_runs
from src.sequential.decoder import _timeline


def decode_batch(scores, frames, periods, costs, *, floor=1e-12):
    if not scores:
        raise ValueError('At least one observation candidate required')
    for score in scores:
        score.validate()
    n, m = len(scores[0].active), len(scores)
    frames, periods = _timeline(frames, periods, n)
    if any(not np.array_equal(score.active, periods > 0) for score in scores):
        raise ValueError('Candidate timelines disagree')
    c = np.asarray(costs, dtype=float)
    if c.shape != (m, 3, 3) or not np.isfinite(c).all() or (c < 0).any() or not 0 < floor < 1/3:
        raise ValueError('One finite nonnegative static cost matrix per candidate required')
    output = np.full((m, n), 'X', dtype='<U1')
    mi, ki = np.arange(m)[:, None], np.arange(3)[None, :]
    changes_indicator = (np.arange(3)[:, None] != np.arange(3)[None, :]).astype(np.int64)
    for start, end in period_runs(periods):
        p = np.stack([score.probabilities[start:end] for score in scores])
        e = np.log(np.maximum(p, floor))
        forward, changes = e[:, 0]-np.log(3.), np.zeros((m, 3), dtype=np.int64)
        previous = np.zeros((end-start, m, 3), dtype=np.uint8)
        for t in range(1, end-start):
            candidates = forward[:, :, None]-c
            best = candidates.max(axis=1)
            count = changes[:, :, None]+changes_indicator
            chosen = np.where(candidates == best[:, None, :], count, np.iinfo(np.int64).max).argmin(axis=1)
            previous[t] = chosen
            forward = best+e[:, t]
            changes = count[mi, chosen, ki]
        last = np.where(forward == forward.max(axis=1)[:, None], changes, np.iinfo(np.int64).max).argmin(axis=1)
        path = np.empty((end-start, m), dtype=np.uint8)
        path[-1] = last
        for t in range(end-start-1, 0, -1):
            path[t-1] = previous[t, np.arange(m), path[t]]
        for index, score in enumerate(scores):
            informative = ((p[index].max(axis=1)-p[index].min(axis=1) > 1e-10)
                & ((score.state_support[start:end] > 0) | (score.team_support[start:end] > 0))).any()
            if informative:
                output[index, start:end] = np.array(['H', 'A', 'D'])[path[:, index]]
    return output
