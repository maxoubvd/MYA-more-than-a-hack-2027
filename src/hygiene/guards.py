"""Explicit abstention policy; never silently fill an unknown team or cross periods."""
from __future__ import annotations

import numpy as np


def guard_decoded_labels(labels, period_ids, *, allowed_unknown=None):
    result = np.asarray(labels)
    periods = np.asarray(period_ids)
    if result.ndim != 1 or periods.shape != result.shape or not np.isin(result, ['H', 'A', 'D', 'X']).all():
        raise ValueError('Invalid decoded labels/timeline')
    unknown = np.zeros(len(result), dtype=bool) if allowed_unknown is None else np.asarray(allowed_unknown)
    if unknown.shape != result.shape or unknown.dtype != bool:
        raise ValueError('Explicit boolean abstention mask required')
    if (result[periods <= 0] != 'X').any():
        raise ValueError('Non-evaluated frames must remain X')
    if ((result == 'X') & (periods > 0) & ~unknown).any():
        raise ValueError('Unexpected abstention inside an observed period')
    return result.copy()
