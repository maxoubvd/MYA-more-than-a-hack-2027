"""Strict internal labels plus the authoritative local official CSV validator."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from src import config
from src.utils.official import load_official_metrics


def validate_labels(labels, n_expected=None):
    """Check before converting dtype: never silently truncate 'HOME' into 'H'."""
    array = np.asarray(labels)
    if array.ndim != 1 or (n_expected is not None and len(array) != n_expected):
        raise ValueError("Prediction labels must be a one-dimensional array of the expected length")
    if not np.isin(array, config.LABELS).all():
        raise ValueError("Prediction labels must contain only exact H, A, D or X values")
    return array.astype("<U1", copy=False)


def validate_submission_file(path: Path, n_expected=config.TOTAL_FRAMES):
    """Validate the actual written file without opening any ground truth."""
    metrics = load_official_metrics()
    table = metrics.read_label_csv(str(path))
    if list(table.columns) != ["frame", "label"]:
        raise ValueError("Expected exactly frame,label columns")
    reason = metrics.validate_submission(table, n_expected)
    if reason is not None:
        # Do not echo malformed private contents from a third-party error.
        raise ValueError("Official submission validation failed")
    return {"rows": len(table), "official_validation": "passed"}
