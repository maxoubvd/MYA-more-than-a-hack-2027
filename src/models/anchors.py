"""Auditable last-control candidate; no manually labelled or purity-claimed anchors."""
from __future__ import annotations

import numpy as np
from src.features.team_assignment import period_runs


def hold_control(direct_logits, p_dead, period_ids, fps, *, decay_s=2., minimum_abs_logit=1.):
    direct = np.asarray(direct_logits, dtype=float)
    dead = np.asarray(p_dead, dtype=float)
    if (direct.ndim != 1 or direct.shape != dead.shape or direct.shape != np.asarray(period_ids).shape
            or np.isinf(direct).any() or not np.isfinite([fps, decay_s, minimum_abs_logit]).all()
            or min(fps, decay_s, minimum_abs_logit) <= 0):
        raise ValueError('Invalid control memory inputs')
    result = direct.copy()
    age = np.full(len(direct), np.nan)
    carried = np.zeros(len(direct), dtype=bool)
    for start, end in period_runs(period_ids):
        last_logit, last_frame = None, None
        for frame in range(start, end):
            # Strong state evidence can invalidate a previous control candidate.
            if np.isfinite(dead[frame]) and dead[frame] >= .8:
                last_logit, last_frame = None, None
            if np.isfinite(direct[frame]):
                age[frame] = 0.
                if abs(direct[frame]) >= minimum_abs_logit and dead[frame] < .5:
                    last_logit, last_frame = direct[frame], frame
                else:
                    # Weak or contradictory fresh evidence cancels the old anchor.
                    last_logit, last_frame = None, None
            elif last_frame is not None:
                age[frame] = (frame-last_frame)/fps
                result[frame] = last_logit*np.exp(-age[frame]/decay_s)
                carried[frame] = True
    result[np.asarray(period_ids) <= 0] = np.nan
    return result, carried, age
