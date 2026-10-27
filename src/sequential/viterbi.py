"""Exact finite-state max-sum decoding with soft costs and max-marginal gaps.

Transition convention: costs[t, previous, current] applies when entering frame t.
Exact ties minimize the number of changes, then use stable state-index order.
Margins describe the specified objective, not calibrated correctness probabilities.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class ViterbiResult:
    path: np.ndarray
    objective: float
    max_marginal_gap: np.ndarray
    changes: int


def _validated(emissions, costs, initial):
    e = np.asarray(emissions, dtype=float)
    if e.ndim != 2 or not len(e) or e.shape[1] < 2 or e.shape[1] > 255:
        raise ValueError('Nonempty N by K emissions with 2..255 states required')
    if np.isnan(e).any() or np.isposinf(e).any() or not np.isfinite(e).any(axis=1).all():
        raise ValueError('Each frame needs at least one finite allowed emission')
    n, k = e.shape
    c = np.asarray(costs, dtype=float)
    if c.shape not in ((k, k), (n, k, k)) or not np.isfinite(c).all() or (c < 0).any():
        raise ValueError('Finite nonnegative static or frame-dependent costs required')
    start = np.full(k, -np.log(k)) if initial is None else np.asarray(initial, dtype=float)
    if start.shape != (k,) or not np.isfinite(start).all():
        raise ValueError('Finite initial state log-potentials required')
    return e, c, start


def path_objective(path, emissions, costs, initial=None):
    e, c, start = _validated(emissions, costs, initial)
    p = np.asarray(path)
    if p.shape != (len(e),) or not np.issubdtype(p.dtype, np.integer) or (p < 0).any() or (p >= e.shape[1]).any():
        raise ValueError('Invalid state path')
    total = start[p[0]] + e[np.arange(len(e)), p].sum()
    if len(p) > 1:
        total -= (c[p[:-1], p[1:]] if c.ndim == 2 else c[np.arange(1, len(p)), p[:-1], p[1:]]).sum()
    return float(total)


def viterbi(emissions, costs, initial=None):
    e, c, start = _validated(emissions, costs, initial)
    n, k = e.shape
    forward = np.full((n, k), -np.inf)
    previous = np.zeros((n, k), dtype=np.uint8)
    forward[0] = start + e[0]
    changes = np.zeros(k, dtype=np.int64)
    indices = np.arange(k)
    change_indicator = (indices[:, None] != indices[None, :]).astype(np.int64)
    for t in range(1, n):
        candidates = forward[t-1, :, None] - (c if c.ndim == 2 else c[t])
        best = candidates.max(axis=0)
        count = changes[:, None] + change_indicator
        # No tolerance is used for score ties: the objective remains exact.
        tied_count = np.where(candidates == best[None, :], count, np.iinfo(np.int64).max)
        chosen = tied_count.argmin(axis=0)
        previous[t] = chosen
        forward[t] = best + e[t]
        changes = count[chosen, indices]
    best_final = forward[-1].max()
    final_options = np.where(forward[-1] == best_final, changes, np.iinfo(np.int64).max)
    end = int(final_options.argmin())
    path = np.empty(n, dtype=np.uint8)
    path[-1] = end
    for t in range(n-1, 0, -1):
        path[t-1] = previous[t, path[t]]

    # Backward max-sum: the gap between the best and second state-constrained
    # complete paths locates ambiguity without a second label smoothing pass.
    backward = np.zeros(k)
    gaps = np.zeros(n)
    for t in range(n-1, -1, -1):
        values = np.sort(forward[t] + backward)
        gaps[t] = max(0., float(values[-1]-values[-2]))
        if t:
            transition = c if c.ndim == 2 else c[t]
            backward = (e[t][None, :] + backward[None, :] - transition).max(axis=1)
    return ViterbiResult(path, float(best_final), gaps, int(changes[end]))
