"""Training-only symmetric Markov priors and observation-only soft boundary cues."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from src.features.builder import FeatureMatrix
from src.features.team_assignment import period_runs
from src.features.context_features import temporal_context
from src.models.observations import ObservationScores
from src.utils.external_data import ExternalTargets, match_role

CLASSES = np.array(['H', 'A', 'D'])
CUE_NAMES = ('H_to_A', 'A_to_H', 'enter_D', 'leave_D')


@dataclass(frozen=True)
class BoundaryCues:
    values: np.ndarray  # NaN is unavailable; 0 is observed absence of a cue
    names: tuple[str, ...] = CUE_NAMES


def count_transitions(targets):
    if not isinstance(targets, ExternalTargets):
        raise TypeError('Separate external targets required for transition fitting')
    labels, frames, periods = targets.labels, targets.frame_ids, targets.period_ids
    if (labels.ndim != 1 or frames.shape != labels.shape or periods.shape != labels.shape
            or not np.isin(labels, ['H', 'A', 'D', 'X']).all()
            or not np.issubdtype(frames.dtype, np.integer) or not np.issubdtype(periods.dtype, np.integer)):
        raise ValueError('Invalid external transition timeline')
    counts = np.zeros((3, 3), dtype=np.int64)
    for start, end in period_runs(periods):
        if (np.diff(frames[start:end]) != 1).any():
            raise ValueError('Frames must remain contiguous within each period')
        local = labels[start:end]
        known = np.isin(local, CLASSES)
        pairs = known[:-1] & known[1:]
        for i, a in enumerate(CLASSES):
            for j, b in enumerate(CLASSES):
                counts[i, j] += np.count_nonzero(pairs & (local[:-1] == a) & (local[1:] == b))
    return counts


def fit_transition_prior(training_targets, *, pseudocount=.5):
    if not training_targets or not np.isfinite(pseudocount) or pseudocount <= 0:
        raise ValueError('Training matches and a positive pseudocount required')
    total, per_match = np.zeros((3, 3), dtype=np.int64), {}
    for match, targets in training_targets.items():
        if match_role(match) != 'train':
            raise PermissionError('Transition priors may fit frozen training matches only')
        counts = count_transitions(targets)
        per_match[match] = counts.tolist()
        total += counts
    if not (total.sum(axis=1) > 0).all():
        raise ValueError('All three states need observed adjacent training targets')
    exchange = np.array([1, 0, 2])
    pooled = .5*(total + total[np.ix_(exchange, exchange)])
    adjusted = pooled + pseudocount
    probability = adjusted / adjusted.sum(axis=1, keepdims=True)
    return {'version': 'symmetric-markov-v1', 'class_order': CLASSES.tolist(),
        'training_matches': sorted(training_targets), 'raw_counts': total.tolist(),
        'per_match_counts': per_match, 'pseudocount': float(pseudocount),
        'transition_probability': probability.tolist(), 'initial_prior': 'uniform',
        'minimum_duration_frames': None, 'competition_labels_used': False,
        'validation_labels_used': False, 'interpretation': 'soft geometric dwell prior, no fixed minimum duration'}


def base_costs(prior):
    if prior.get('version') != 'symmetric-markov-v1' or prior.get('class_order') != CLASSES.tolist():
        raise ValueError('Unsupported transition prior')
    p = np.asarray(prior['transition_probability'], dtype=float)
    if p.shape != (3, 3) or not np.isfinite(p).all() or (p <= 0).any() or (p > 1).any() or not np.allclose(p.sum(axis=1), 1.):
        raise ValueError('Invalid learned transition matrix')
    return -np.log(p)


def _available_max(*values):
    stack = np.column_stack(values)
    valid = np.isfinite(stack)
    result = np.max(np.where(valid, stack, -np.inf), axis=1)
    return np.where(valid.any(axis=1), result, np.nan)


def _contact_window(values, periods, radius):
    result = np.asarray(values, dtype=float).copy()
    for start, end in period_runs(periods):
        for offset in range(1, min(radius+1, end-start)):
            result[start:end-offset] = np.fmax(result[start:end-offset], values[start+offset:end])
            result[start+offset:end] = np.fmax(result[start+offset:end], values[start:end-offset])
    return result


def boundary_cues(matrix, scores, options):
    if not isinstance(matrix, FeatureMatrix) or not isinstance(scores, ObservationScores):
        raise TypeError('Boundary cues accept observations and scores, never targets')
    scores.validate()
    if len(matrix.frame_ids) != len(scores.active) or not np.array_equal(matrix.period_ids > 0, scores.active):
        raise ValueError('Boundary observations and scores are misaligned')
    get = matrix.column
    fps = float(matrix.diagnostics.get('fps', 25.))
    window = max(1, int(round(fps*options['control_context_s'])))
    control = np.where(scores.team_support > 0, scores.p_home_given_alive, np.nan)
    context = temporal_context(control, matrix.period_ids, window)
    past, future = context['past_mean'], context['future_mean']
    peak = get('contact_acceleration_candidate')
    proximity = get('contact_window_nearest_player_m')
    contact = peak*np.exp(-.5*(proximity/options['contact_distance_scale_m'])**2)
    contact = _contact_window(contact, matrix.period_ids, int(options['contact_half_window_frames']))
    delta = np.clip(np.abs(future-past)*2., 0., 1.)
    support = np.isfinite(past) & np.isfinite(future)
    # A brief deflection alone is not enough: require opposing context on the
    # two sides. Contact only strengthens this soft reduction, never forces it.
    combined = delta*(.25+.75*np.nan_to_num(contact, nan=0.))
    h_to_a = np.where(support, np.where((past > .5) & (future < .5), combined, 0.), np.nan)
    a_to_h = np.where(support, np.where((past < .5) & (future > .5), combined, 0.), np.nan)

    boundary = get('ball_boundary_distance_m')
    outside = np.clip((-boundary-options['boundary_margin_m'])/2., 0., 1.)
    exit_gap = get('ball_gap_after_boundary_exit')*np.exp(-get('since_observation_s')/options['exit_memory_s'])
    stationary = get('ball_low_motion_score')*np.clip(get('ball_low_motion_run_s'), 0., 1.)*np.exp(-get('collective_median_speed_mps'))
    enter = _available_max(outside, exit_gap, stationary)
    ball_change = get('ball_speed_future_mean_mps')-get('ball_speed_past_mean_mps')
    collective_change = get('collective_speed_future_mean_mps')-get('collective_speed_past_mean_mps')
    leave = np.clip(ball_change/3., 0., 1.)*np.clip(collective_change, 0., 1.)
    leave *= np.where(np.isfinite(boundary), boundary > options['boundary_margin_m'], np.nan)
    # A restart tag alone cannot turn an entire interval into dead ball.
    for name, distances in (('enter', get('restart_until_next_start_s')),
                            ('leave', get('restart_since_last_end_s'))):
        near = np.exp(-distances/options['restart_context_s'])
        if name == 'enter':
            enter = np.minimum(1., enter*(1.+.15*np.nan_to_num(near, nan=0.)))
        else:
            leave = np.minimum(1., leave*(1.+.15*np.nan_to_num(near, nan=0.)))
    values = np.column_stack((h_to_a, a_to_h, enter, leave))
    values[~scores.active] = np.nan
    return BoundaryCues(values)


def transition_costs(prior, cues=None, *, reduction=.5):
    base = base_costs(prior)
    if cues is None:
        return base
    if not isinstance(cues, BoundaryCues) or cues.names != CUE_NAMES:
        raise TypeError('Named observation-only boundary cues required')
    values = np.asarray(cues.values, dtype=float)
    if (values.ndim != 2 or values.shape[1] != 4 or np.isinf(values).any()
            or ((values[np.isfinite(values)] < 0) | (values[np.isfinite(values)] > 1)).any()
            or not np.isfinite(reduction) or not 0 <= reduction < 1):
        raise ValueError('Invalid soft transition cues or reduction')
    cost = np.broadcast_to(base, (len(values), 3, 3)).copy()
    strength = np.nan_to_num(values, nan=0.)
    cost[:, 0, 1] *= 1.-reduction*strength[:, 0]
    cost[:, 1, 0] *= 1.-reduction*strength[:, 1]
    cost[:, :2, 2] *= (1.-reduction*strength[:, 2])[:, None]
    cost[:, 2, :2] *= (1.-reduction*strength[:, 3])[:, None]
    return cost
