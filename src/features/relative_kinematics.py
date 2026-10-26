"""Relative velocity at the same physical track, never derivatives of a rank."""
from __future__ import annotations
import numpy as np


def finite_mean(values,axis=1):
    valid = np.isfinite(values)
    count = valid.sum(axis=axis)
    return np.divide(np.where(valid,values,0).sum(axis=axis),count,
                     out=np.full(count.shape,np.nan,dtype=float),where=count>0)


def relative_features(distances, delta, player_velocity, ball_velocity, teams,
                      *, velocity_sigma_mps=5.):
    if velocity_sigma_mps <= 0:
        raise ValueError("Positive velocity kernel scale required")
    relative = player_velocity-ball_velocity[:,None,:]
    relative_speed = np.linalg.norm(relative,axis=-1)
    closing = np.divide(-np.sum(delta*relative,axis=-1),distances,
                        out=np.full_like(distances,np.nan),where=distances>1e-6)
    result = {}
    for team in ('H','A'):
        slots = np.flatnonzero(np.asarray(teams)==team)
        d = distances[:,slots]
        minimum = np.min(np.where(np.isfinite(d),d,np.inf),axis=1,initial=np.inf)
        # Average equal-distance ties rather than choosing a slot by its index.
        tied = np.isfinite(d) & (np.abs(d-minimum[:,None])<=1e-5)
        speed = finite_mean(np.where(tied,relative_speed[:,slots],np.nan))
        result[f'{team}_nearest_relative_speed_mps'] = speed
        result[f'{team}_nearest_closing_speed_mps'] = finite_mean(np.where(tied,closing[:,slots],np.nan))
        result[f'{team}_nearest_velocity_support_n'] = (tied & np.isfinite(relative_speed[:,slots])).sum(axis=1)
        result[f'{team}_velocity_coherence'] = np.exp(-.5*(speed/velocity_sigma_mps)**2)
    return result
