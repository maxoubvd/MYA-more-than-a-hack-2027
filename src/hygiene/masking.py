"""Official half-open video periods, independent of any ground-truth file."""
from __future__ import annotations

import numpy as np

from src import config
from src.hygiene.validator import validate_labels


def checked_intervals(n_frames, intervals):
    result = tuple(intervals)
    previous_end = 0
    for start, end in result:
        if (type(start) is not int or type(end) is not int
                or not 0 <= previous_end <= start < end <= n_frames):
            raise ValueError("Periods must be ordered, disjoint, nonempty and within the video")
        previous_end = end
    return result


def evaluated_mask(n_frames=config.TOTAL_FRAMES, intervals=config.EVALUATED_INTERVALS):
    mask = np.zeros(n_frames, dtype=bool)
    for start, end in checked_intervals(n_frames, intervals):
        mask[start:end] = True
    return mask


def apply_official_masks(labels, *, intervals=config.EVALUATED_INTERVALS,
                         dead_zone=config.DEAD_ZONE_2HT_INTERVAL):
    """Copy labels, use X outside periods and D in the published pre-kickoff zone.

    X outside the periods is our convention; those frames are ignored officially.
    No manually inspected match boundaries or private tracking offsets are used.
    """
    labels = validate_labels(labels)
    mask = evaluated_mask(len(labels), intervals)
    result = labels.copy()
    result[~mask] = "X"
    if dead_zone is not None:
        start, end = checked_intervals(len(labels), (dead_zone,))[0]
        if not mask[start:end].all():
            raise ValueError("Published dead zone must lie inside an evaluated period")
        result[start:end] = "D"
    return result
