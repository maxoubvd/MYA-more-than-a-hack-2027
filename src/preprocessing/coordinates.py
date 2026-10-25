"""Coordinate conventions: original pitch origin, no inferred attacking direction."""
from __future__ import annotations

import numpy as np

from src import config


def to_metres(observations: np.ndarray) -> np.ndarray:
    """Copy (..., x/y[/speed]) to metres; preserve native scalar speed and NaNs.

    Only positions change units. Consult ATD metadata speed_unit before any
    physical speed calculation: the XML may disagree with the public prose.
    """
    result = np.array(observations, dtype=np.float32, copy=True)
    if result.ndim == 0 or result.shape[-1] not in (2, 3):
        raise ValueError("Expected last dimension x,y or x,y,speed")
    result[..., :2] *= np.asarray(config.PITCH_DIMS, dtype=result.dtype)
    return result


def project(matrix: np.ndarray, points: np.ndarray) -> np.ndarray:
    """Normalised pitch (...,2) -> image pixels; invalid/projective infinity -> NaN."""
    matrix = np.asarray(matrix, dtype=float)
    points = np.asarray(points, dtype=float)
    if matrix.shape != (3, 3) or points.ndim == 0 or points.shape[-1] != 2:
        raise ValueError("Expected a 3x3 matrix and (...,2) points")
    homogeneous = np.concatenate((points, np.ones(points.shape[:-1] + (1,))), axis=-1)
    transformed = homogeneous @ matrix.T
    denominator = transformed[..., 2:3]
    with np.errstate(divide="ignore", invalid="ignore"):
        result = transformed[..., :2] / denominator
    return np.where(np.isfinite(result) & (np.abs(denominator) > 1e-12), result, np.nan)


def unproject(matrix: np.ndarray, pixels: np.ndarray) -> np.ndarray:
    """Image pixels -> normalised pitch; a missing/singular matrix has no inverse."""
    matrix = np.asarray(matrix, dtype=float)
    if matrix.shape != (3, 3):
        raise ValueError("Expected a 3x3 matrix")
    try:
        inverse = np.linalg.inv(matrix)
    except np.linalg.LinAlgError:
        inverse = np.full((3, 3), np.nan)
    return project(inverse, pixels)
