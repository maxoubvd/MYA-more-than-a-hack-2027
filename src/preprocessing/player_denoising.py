"""Conservative fragments, local smoothing and coordinate-derived kinematics.

No missing position is imputed; no value is clipped. Link speed gates flag
possible tracking breaks, not physiological impossibility or player identities.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np


@dataclass
class Kinematics:
    positions: np.ndarray
    velocity: np.ndarray
    acceleration: np.ndarray
    backward_velocity: np.ndarray
    observed: np.ndarray
    link_valid: np.ndarray
    fragment_start: np.ndarray


def track_kinematics(xy_metres, period_ids, frame_ids, fps, *, max_link_speed_mps):
    points = np.asarray(xy_metres, dtype=np.float32)
    if points.ndim not in (2,3) or points.shape[-1] != 2 or np.isinf(points).any():
        raise ValueError("Expected finite-or-NaN metric positions ending in x/y")
    if fps <= 0 or not np.isfinite(fps) or max_link_speed_mps <= 0 or not np.isfinite(max_link_speed_mps):
        raise ValueError("Positive finite kinematics settings required")
    observed = np.isfinite(points).all(axis=-1)
    active = np.asarray(period_ids) > 0
    active_shape = active.reshape((len(points),)+(1,)*(observed.ndim-1))
    observed &= active_shape
    positions = points.copy()
    positions[~observed] = np.nan
    links = np.zeros_like(observed)
    temporal = (np.asarray(period_ids)[1:]==np.asarray(period_ids)[:-1]) & active[1:] & (np.diff(frame_ids)==1)
    temporal = temporal.reshape((len(points)-1,)+(1,)*(observed.ndim-1))
    step = np.linalg.norm(positions[1:]-positions[:-1], axis=-1)*fps
    links[1:] = observed[1:] & observed[:-1] & temporal & (step <= max_link_speed_mps)
    starts = observed & ~links
    central = links[1:-1] & links[2:]
    # Symmetric 3-point mean only when the complete window stays in one fragment.
    mean = (positions[:-2]+positions[1:-1]+positions[2:])/3
    positions[1:-1] = np.where(central[...,None], mean, positions[1:-1])
    velocity = np.full_like(points, np.nan)
    acceleration = np.full_like(points, np.nan)
    backward = np.full_like(points, np.nan)
    velocity[1:-1] = np.where(central[...,None], (positions[2:]-positions[:-2])*(fps/2), np.nan)
    acceleration[1:-1] = np.where(central[...,None], (positions[2:]-2*positions[1:-1]+positions[:-2])*(fps*fps), np.nan)
    # Last visible sample before a gap needs a backward estimate, marked separately.
    backward[1:] = np.where(links[1:][...,None], (points[1:]-points[:-1])*fps, np.nan)
    return Kinematics(positions, velocity, acceleration, backward, observed, links, starts)


def duplicate_weights(players_metres, teams, *, radius_m=.15, batch_size=512):
    """Symmetric within-team near-duplicate diagnostics, never identity correction.

    Equal locations share total weight one; close legitimate players are not
    declared invalid. Weighted collective features remain permutation invariant.
    """
    players = np.asarray(players_metres)
    n, slots, _ = players.shape
    weights = np.zeros((n,slots), dtype=np.float32)
    candidates = np.zeros((n,slots), dtype=bool)
    if radius_m < 0 or batch_size < 1:
        raise ValueError("Invalid duplicate diagnostic settings")
    for team in ("H","A"):
        selected = np.flatnonzero(np.asarray(teams)==team)
        for start in range(0,n,batch_size):
            end = min(n,start+batch_size)
            p = players[start:end,selected]
            finite = np.isfinite(p).all(axis=-1)
            delta = p[:,:,None,:]-p[:,None,:,:]
            close = np.sum(delta*delta,axis=-1) <= radius_m*radius_m
            close &= finite[:,:,None] & finite[:,None,:]
            density = close.sum(axis=-1)
            weights[start:end,selected] = np.divide(1.,density,out=np.zeros_like(density,dtype=np.float32),where=density>0)
            candidates[start:end,selected] = density>1
    return weights, candidates
