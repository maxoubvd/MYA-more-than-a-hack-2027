"""Permutation-invariant proximity features in physical metres."""
from __future__ import annotations
import numpy as np


def proximity_features(players, ball, teams, weights, *, control_offset_m=.5, control_sigma_m=1.5):
    if control_sigma_m <= 0 or control_offset_m < 0:
        raise ValueError("Invalid geometric kernel settings")
    delta = np.asarray(players)-np.asarray(ball)[:,None,:]
    distances = np.linalg.norm(delta,axis=-1)
    result = {}
    for team in ("H","A"):
        slots = np.flatnonzero(np.asarray(teams)==team)
        values = distances[:,slots]
        ordered = np.sort(np.where(np.isfinite(values),values,np.inf),axis=1)
        for rank in (1,2,3):
            selected = ordered[:,rank-1] if ordered.shape[1]>=rank else np.full(len(ball),np.inf)
            result[f'{team}_nearest_{rank}_m'] = np.where(np.isfinite(selected),selected,np.nan)
        supported = np.isfinite(values).any(axis=1)
        for radius in (1,2,5):
            count = ((values<=radius)*weights[:,slots]).sum(axis=1)
            result[f'{team}_within_{radius}m_effective_n'] = np.where(supported,count,np.nan)
        nearest = result[f'{team}_nearest_1_m']
        result[f'{team}_distance_kernel'] = np.exp(-.5*(np.maximum(nearest-control_offset_m,0)/control_sigma_m)**2)
    result['nearest_distance_A_minus_H_m'] = result['A_nearest_1_m']-result['H_nearest_1_m']
    result['distance_kernel_H_minus_A'] = result['H_distance_kernel']-result['A_distance_kernel']
    return result, distances, delta
