"""Observation-only designs and split-checked external supervision for milestone 4."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from src.features.builder import FeatureMatrix
from src.utils.external_data import ExternalTargets, match_role


@dataclass(frozen=True)
class FeatureBlock:
    values: np.ndarray
    names: tuple[str, ...]
    symmetric_team: bool = False


@dataclass(frozen=True)
class ObservationDesign:
    state: FeatureBlock
    visible_team: FeatureBlock
    collective_team: FeatureBlock
    active: np.ndarray
    ball_visible: np.ndarray
    both_teams: np.ndarray


@dataclass(frozen=True)
class TrainingExamples:
    match_id: str
    scenario: str
    state: FeatureBlock
    visible_team: FeatureBlock
    collective_team: FeatureBlock
    labels: np.ndarray
    ball_visible: np.ndarray
    both_teams: np.ndarray
    frame_ids: np.ndarray


def observation_design(matrix):
    """Explicit allowlists: state never sees team control, proximity or identity.

    All team columns change sign when H/A are exchanged. A zero-centred, no-
    intercept team model can therefore preserve team-exchange equivariance.
    """
    if not isinstance(matrix, FeatureMatrix):
        raise TypeError('Observation design accepts FeatureMatrix only')
    n = len(matrix.frame_ids)

    def get(name):
        return matrix.column(name).astype(np.float64, copy=False)

    def positive_log(value):
        return np.log1p(np.maximum(value, 0))

    state = {}
    for name in ('ball_speed_mps', 'ball_acceleration_mps2',
                 'ball_backward_speed_mps', 'collective_median_speed_mps',
                 'ball_speed_past_mean_mps', 'ball_speed_future_mean_mps',
                 'collective_speed_past_mean_mps', 'collective_speed_future_mean_mps'):
        state[f'log1p_{name}'] = positive_log(get(name))
    for name in ('ball_low_motion_score', 'collective_low_activity_score',
                 'ball_speed_past_support', 'ball_speed_future_support',
                 'collective_speed_past_support', 'collective_speed_future_support'):
        state[name] = get(name)
    boundary = get('ball_boundary_distance_m')
    state['boundary_signed_tanh'] = np.tanh(boundary / 5.)
    state['boundary_outside_beyond_margin_m'] = np.clip(-boundary - .5, 0., 5.)
    state['low_motion_duration_capped_s'] = np.minimum(get('ball_low_motion_run_s'), 5.)
    state['stationary_and_slow_collective'] = (
        get('ball_low_motion_score') * np.exp(-get('collective_median_speed_mps')))
    state['recent_exit_then_gap'] = (get('ball_gap_after_boundary_exit') *
                                    np.exp(-get('since_observation_s') / 3.))
    state['ball_speed_change_mps'] = get('ball_speed_future_minus_past_mps')
    state['collective_speed_change_mps'] = get('collective_speed_future_minus_past_mps')

    collective = {}
    for suffix in ('centroid_x_m', 'centroid_y_m', 'spread_x_m', 'spread_y_m',
                   'extent_x_m', 'extent_y_m', 'mean_vx_mps', 'mean_vy_mps',
                   'observed_n', 'effective_n', 'velocity_observed_n'):
        collective[f'H_minus_A_{suffix}'] = get(f'H_{suffix}') - get(f'A_{suffix}')
    visible = dict(collective)
    for rank in (1, 2, 3):
        visible[f'log_distance_A_minus_H_{rank}'] = (
            positive_log(get(f'A_nearest_{rank}_m')) - positive_log(get(f'H_nearest_{rank}_m')))
    for suffix in ('distance_kernel', 'motion_distance_kernel',
                   'nearest_closing_speed_mps', 'velocity_coherence',
                   'within_1m_effective_n', 'within_2m_effective_n', 'within_5m_effective_n'):
        visible[f'H_minus_A_{suffix}'] = get(f'H_{suffix}') - get(f'A_{suffix}')
    visible['log_relative_speed_A_minus_H'] = (
        positive_log(get('A_nearest_relative_speed_mps')) - positive_log(get('H_nearest_relative_speed_mps')))

    def block(columns, team=False):
        values = np.column_stack(list(columns.values()))
        if values.shape[0] != n or np.isinf(values).any():
            raise ValueError('Invalid observation design')
        return FeatureBlock(values, tuple(columns), team)

    return ObservationDesign(block(state), block(visible, True), block(collective, True),
        np.asarray(matrix.period_ids) > 0, get('ball_observed') == 1,
        (get('H_observed_n') > 0) & (get('A_observed_n') > 0))


def aligned_labels(matrix, targets):
    if not isinstance(targets, ExternalTargets):
        raise TypeError('Supervision must use the separate ExternalTargets interface')
    if (not np.array_equal(matrix.frame_ids, targets.frame_ids)
            or not np.array_equal(matrix.period_ids, targets.period_ids)
            or targets.labels.shape != matrix.frame_ids.shape
            or not np.isin(targets.labels, ['H', 'A', 'D', 'X']).all()):
        raise ValueError('Observations and external targets are not exactly aligned')
    return targets.labels


def training_examples(match_id, scenario, matrix, targets, *, maximum_rows):
    if match_role(match_id) != 'train':
        raise PermissionError('Training examples require a frozen training match')
    if type(maximum_rows) is not int or maximum_rows < 1:
        raise ValueError('Positive integer training sample limit required')
    labels = aligned_labels(matrix, targets)
    design = observation_design(matrix)
    eligible = np.flatnonzero(design.active & np.isin(labels, ['H', 'A', 'D']))
    if not len(eligible):
        raise ValueError('No known training targets')
    # Deterministic coverage across the complete match, never a random frame split.
    rows = eligible[np.linspace(0, len(eligible)-1, min(len(eligible), maximum_rows), dtype=int)]

    def subset(block):
        return FeatureBlock(block.values[rows].copy(), block.names, block.symmetric_team)

    return TrainingExamples(match_id, scenario, subset(design.state), subset(design.visible_team),
        subset(design.collective_team), labels[rows].copy(), design.ball_visible[rows].copy(),
        design.both_teams[rows].copy(), matrix.frame_ids[rows].copy())
