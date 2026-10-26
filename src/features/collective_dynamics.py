"""Anonymous collective geometry; velocity is averaged over valid track fragments."""
from __future__ import annotations
import warnings
import numpy as np


def weighted_mean(values,weights):
    finite = np.isfinite(values)
    effective = np.where(finite,weights,0)
    total = effective.sum(axis=1)
    return np.divide((np.where(finite,values,0)*effective).sum(axis=1),total,
                     out=np.full(total.shape,np.nan,dtype=float),where=total>0)


def collective_features(players, velocity, teams, weights, duplicates, *, period_ids, pitch_dims, attack_directions=None):
    result = {}
    attack_directions = attack_directions or {}
    for team in ('H','A'):
        slots = np.flatnonzero(np.asarray(teams)==team)
        p, v, w = players[:,slots], velocity[:,slots], weights[:,slots]
        observed = np.isfinite(p).all(axis=-1)
        result[f'{team}_observed_n'] = observed.sum(axis=1)
        result[f'{team}_effective_n'] = w.sum(axis=1)
        result[f'{team}_near_duplicate_n'] = duplicates[:,slots].sum(axis=1)
        result[f'{team}_velocity_observed_n'] = np.isfinite(v).all(axis=-1).sum(axis=1)
        for axis,label in ((0,'x'),(1,'y')):
            centre = weighted_mean(p[...,axis],w)
            result[f'{team}_centroid_{label}_m'] = centre
            variance = weighted_mean((p[...,axis]-centre[:,None])**2,w)
            result[f'{team}_spread_{label}_m'] = np.sqrt(variance)
            with warnings.catch_warnings():
                warnings.simplefilter('ignore',RuntimeWarning)
                extent = np.nanmax(p[...,axis],axis=1,initial=-np.inf)-np.nanmin(p[...,axis],axis=1,initial=np.inf)
            result[f'{team}_extent_{label}_m'] = np.where(observed.any(axis=1),extent,np.nan)
            result[f'{team}_mean_v{label}_mps'] = weighted_mean(v[...,axis],w)
        direction = np.full(len(players),np.nan)
        for period in set(np.asarray(period_ids).tolist())-{0}:
            value = attack_directions.get((period,team))
            if value is not None and value not in (-1,1):
                raise ValueError("Attack axis must be +1 or -1")
            if value is not None:
                direction[np.asarray(period_ids)==period] = value
        result[f'{team}_attack_axis'] = direction
        result[f'{team}_attack_velocity_mps'] = direction*result[f'{team}_mean_vx_mps']
        x = result[f'{team}_centroid_x_m']
        result[f'{team}_distance_to_opponent_goal_m'] = np.where(direction==1,pitch_dims[0]-x,np.where(direction==-1,x,np.nan))
    result['inter_centroid_distance_m'] = np.hypot(result['H_centroid_x_m']-result['A_centroid_x_m'],
                                                   result['H_centroid_y_m']-result['A_centroid_y_m'])
    speeds = np.linalg.norm(velocity,axis=-1)
    finite = np.isfinite(speeds)
    order = np.argsort(np.where(finite,speeds,np.inf),axis=1)
    ordered_speed = np.take_along_axis(speeds,order,axis=1)
    ordered_weights = np.take_along_axis(np.where(finite,weights,0),order,axis=1)
    cumulative = np.cumsum(ordered_weights,axis=1)
    effective_n = ordered_weights.sum(axis=1)
    middle = np.argmax(cumulative>=effective_n[:,None]/2,axis=1)
    median = ordered_speed[np.arange(len(players)),middle]
    count = np.isfinite(speeds).sum(axis=1)
    result['collective_velocity_observed_n'] = count
    result['collective_effective_velocity_n'] = effective_n
    result['collective_median_speed_mps'] = np.where(effective_n>=4,median,np.nan)
    return result
