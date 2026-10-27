"""Conservative state-only evidence: no player-ball proximity or team attribution."""
from __future__ import annotations

import numpy as np
from src.features.builder import FeatureMatrix
from src.models.tabular import sigmoid


def state_rule_evidence(matrix):
    if not isinstance(matrix, FeatureMatrix):
        raise TypeError('State rules require observation features')
    boundary = matrix.column('ball_boundary_distance_m')
    speed = matrix.column('ball_speed_mps')
    low_motion = matrix.column('ball_low_motion_score')
    duration = matrix.column('ball_low_motion_run_s')
    collective = matrix.column('collective_median_speed_mps')
    since = matrix.column('since_observation_s')
    exit_gap = matrix.column('ball_gap_after_boundary_exit')

    # Every term requires physical context. Missingness alone contributes zero.
    outside = np.clip((-boundary-.5)/2., 0., 1.)
    placed = low_motion*np.clip(duration, 0., 1.)*np.exp(-collective)
    exit_context = exit_gap*np.exp(-since/3.)
    moving_inside = ((boundary > .5).astype(float)*np.clip(speed/3., 0., 1.))
    moving_inside[~np.isfinite(boundary)] = np.nan
    evidence = (2.5*np.nan_to_num(outside, nan=0.) + 2.5*np.nan_to_num(placed, nan=0.)
                + 2.*np.nan_to_num(exit_context, nan=0.) - 1.5*np.nan_to_num(moving_inside, nan=0.))
    support = np.column_stack((np.isfinite(outside), np.isfinite(placed),
                               np.isfinite(exit_context), np.isfinite(moving_inside))).sum(axis=1)
    active = matrix.period_ids > 0
    evidence[~active] = np.nan
    # No evidence => equal H/A/D once factored with conditional H=.5.
    p_dead = sigmoid(-np.log(2.)+evidence)
    return evidence, p_dead, support
