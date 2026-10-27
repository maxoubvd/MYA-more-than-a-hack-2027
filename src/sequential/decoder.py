"""Period-local decoding, explicit unknowns and conditional boundary uncertainty."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from src.features.team_assignment import period_runs
from src.hygiene.guards import guard_decoded_labels
from src.models.observations import ObservationScores
from src.sequential.dynamic_matrix import CLASSES
from src.sequential.viterbi import viterbi


@dataclass(frozen=True)
class SequenceResult:
    labels: np.ndarray
    state_path: np.ndarray  # -1 outside periods; before explicit unknown masking
    margin: np.ndarray
    allowed_unknown: np.ndarray
    boundaries: list[dict]
    periods: list[dict]


def _timeline(frames, periods, n):
    frames, periods = np.asarray(frames), np.asarray(periods)
    if (frames.shape != (n,) or periods.shape != (n,)
            or not np.issubdtype(frames.dtype, np.integer)
            or not np.issubdtype(periods.dtype, np.integer) or (periods < 0).any()):
        raise ValueError('Integer frame and nonnegative period timelines required')
    for start, end in period_runs(periods):
        if (np.diff(frames[start:end]) != 1).any():
            raise ValueError('Frames must be contiguous inside each decoded period')
    return frames, periods


def boundary_profiles(path, emissions, costs, frames, *, radius_frames, near_optimal_gap):
    """Single-boundary score profiles with neighbouring states held fixed.

    Envelopes are conditional near-optimal alternatives, not statistical confidence
    intervals. No boundary is moved after Viterbi and no short segment is deleted.
    """
    path = np.asarray(path)
    if type(radius_frames) is not int or radius_frames < 1 or not np.isfinite(near_optimal_gap) or near_optimal_gap < 0:
        raise ValueError('Invalid boundary-profile settings')
    edges = np.r_[0, np.flatnonzero(path[1:] != path[:-1])+1, len(path)]
    result = []
    for index in range(1, len(edges)-1):
        t = int(edges[index])
        a, b = int(path[t-1]), int(path[t])
        low = max(int(edges[index-1])+1, t-radius_frames)
        high = min(int(edges[index+1])-1, t+radius_frames)
        left, right = low-1, high+1
        candidates = np.arange(low, high+1)
        score = []
        for switch in candidates:
            value = emissions[left:switch, a].sum() + emissions[switch:right, b].sum()
            if costs.ndim == 2:
                value -= (switch-left-1)*costs[a, a] + (right-switch-1)*costs[b, b] + costs[a, b]
            else:
                value -= costs[left+1:switch, a, a].sum() + costs[switch+1:right, b, b].sum() + costs[switch, a, b]
            score.append(float(value))
        score = np.asarray(score)
        gap = np.maximum(0., score.max()-score)
        near = candidates[gap <= near_optimal_gap+1e-10]
        result.append({'frame': int(frames[t]), 'from': str(CLASSES[a]), 'to': str(CLASSES[b]),
            'candidate_frames': frames[candidates].astype(int).tolist(),
            'candidate_log_gaps': [float(value) if np.isfinite(value) else None for value in gap],
            'near_optimal_frames': frames[near].astype(int).tolist(),
            'envelope_start_frame': int(frames[near[0]]), 'envelope_end_frame': int(frames[near[-1]]),
            'envelope_not_statistical_interval': True})
    return result


def decode(scores, frame_ids, period_ids, costs, options, *, allowed_states=None, fps=25.):
    if not isinstance(scores, ObservationScores):
        raise TypeError('Decoder accepts frozen ObservationScores, never targets')
    scores.validate()
    n = len(scores.active)
    frames, periods = _timeline(frame_ids, period_ids, n)
    if not np.array_equal(scores.active, periods > 0) or not np.isfinite(fps) or fps <= 0:
        raise ValueError('Score activity and period masks disagree')
    cost = np.asarray(costs, dtype=float)
    if cost.shape not in ((3, 3), (n, 3, 3)) or not np.isfinite(cost).all() or (cost < 0).any():
        raise ValueError('Invalid decoding transition costs')
    allowed = np.ones((n, 3), dtype=bool) if allowed_states is None else np.asarray(allowed_states)
    if allowed.shape != (n, 3) or allowed.dtype != bool or not allowed[scores.active].any(axis=1).all():
        raise ValueError('Each active frame requires at least one allowed state')
    floor, weight = options['probability_floor'], options['emission_weight']
    if not np.isfinite([floor, weight]).all() or not 0 < floor < 1./3. or weight <= 0:
        raise ValueError('Invalid emission scale/floor')
    labels = np.full(n, 'X', dtype='<U1')
    path = np.full(n, -1, dtype=np.int8)
    margins = np.full(n, np.nan)
    unknown = np.zeros(n, dtype=bool)
    boundaries, diagnostics = [], []
    for start, end in period_runs(periods):
        p = scores.probabilities[start:end]
        emissions = weight*np.log(np.maximum(p, floor))
        emissions[~allowed[start:end]] = -np.inf
        local_cost = cost if cost.ndim == 2 else cost[start:end]
        result = viterbi(emissions, local_cost)
        path[start:end] = result.path
        margins[start:end] = result.max_marginal_gap
        informative = ((p.max(axis=1)-p.min(axis=1) > 1e-10) &
                       ((scores.state_support[start:end] > 0) | (scores.team_support[start:end] > 0))).any()
        if informative:
            labels[start:end] = CLASSES[result.path]
            profile = boundary_profiles(result.path, emissions, local_cost, frames[start:end],
                radius_frames=max(1, int(round(fps*options['boundary_profile_radius_s']))),
                near_optimal_gap=options['boundary_near_optimal_log_gap'])
            for entry in profile:
                entry['period_id'] = int(periods[start])
            boundaries.extend(profile)
        else:
            # A complete blind period must not become D simply because D has
            # longer training dwell. Explicit published constraints remain known.
            singleton = allowed[start:end].sum(axis=1) == 1
            local_labels = labels[start:end]
            local_labels[singleton] = CLASSES[allowed[start:end][singleton].argmax(axis=1)]
            unknown[start:end] = ~singleton
            margins[start:end] = np.where(singleton, np.inf, np.nan)
        diagnostics.append({'period_id': int(periods[start]), 'start_frame': int(frames[start]),
            'end_frame_exclusive': int(frames[end-1]+1), 'objective': result.objective,
            'changes_in_optimal_path': result.changes, 'informative_observations': bool(informative)})
    labels = guard_decoded_labels(labels, periods, allowed_unknown=unknown)
    return SequenceResult(labels, path, margins, unknown, boundaries, diagnostics)
