"""Deterministic regularized logistic models using the existing NumPy runtime.

State and conditional team classifiers are independent. Team-visible and
team-collective heads preserve H/A exchange symmetry. No probability calibration
is claimed; preprocessing is fitted on external training rows only.
"""
from __future__ import annotations

import numpy as np

from src.models.dataset import FeatureBlock, TrainingExamples
from src.utils.external_data import match_role

MODEL_VERSION = 'factorized-logistic-v1'


def sigmoid(value):
    value = np.asarray(value, dtype=float)
    return np.exp(-np.logaddexp(0., -value))


def transform(block, model):
    if not isinstance(block, FeatureBlock) or list(block.names) != model['feature_names']:
        raise ValueError('Logistic feature schema mismatch')
    values = np.asarray(block.values, dtype=float)
    if values.ndim != 2 or values.shape[1] != len(block.names) or np.isinf(values).any():
        raise ValueError('Invalid logistic observation block')
    missing = ~np.isfinite(values)
    locations = np.asarray(model['location'], dtype=float)
    scales = np.asarray(model['scale'], dtype=float)
    if (locations.shape != (values.shape[1],) or scales.shape != locations.shape
            or not np.isfinite(np.r_[locations, scales, model['clip']]).all()
            or (scales <= 0).any() or model['clip'] <= 0
            or block.symmetric_team != model['symmetric_team']):
        raise ValueError('Invalid logistic preprocessing')
    x = np.where(missing, locations, values)
    x = np.clip((x-locations)/scales, -model['clip'], model['clip'])
    if not model['symmetric_team']:
        x = np.column_stack((np.ones(len(x)), x, missing.astype(float)))
    return x


def fit_logistic(block, target, *, l2=.01, max_iterations=50, tolerance=1e-6, clip=8.):
    if not isinstance(block, FeatureBlock):
        raise TypeError('A named observation block is required')
    values = np.asarray(block.values, dtype=float)
    y = np.asarray(target, dtype=float)
    if (values.ndim != 2 or len(values) < 2 or values.shape[1] != len(block.names)
            or np.isinf(values).any() or y.shape != (len(values),)
            or not np.isin(y, [0., 1.]).all() or len(np.unique(y)) != 2
            or not np.isfinite([l2, tolerance, clip]).all() or min(l2, tolerance, clip) <= 0
            or type(max_iterations) is not int or max_iterations < 1):
        raise ValueError('Invalid binary logistic training data/settings')
    missing = ~np.isfinite(values)
    location = np.zeros(values.shape[1])
    if not block.symmetric_team:
        for index in range(values.shape[1]):
            known = values[~missing[:, index], index]
            location[index] = float(np.median(known)) if len(known) else 0.
    filled = np.where(missing, location, values)
    # Odd team features must remain zero-centred: use RMS instead of centring.
    scale = np.sqrt(np.mean(filled**2, axis=0)) if block.symmetric_team else np.std(filled, axis=0)
    scale = np.where(np.isfinite(scale) & (scale > 1e-6), scale, 1.)
    model = {'feature_names': list(block.names), 'symmetric_team': block.symmetric_team,
             'location': location.tolist(), 'scale': scale.tolist(), 'clip': float(clip),
             'l2': float(l2), 'calibrated': False}
    x = transform(block, model)
    coefficients = np.zeros(x.shape[1])
    penalty = np.ones(x.shape[1]) * l2
    if not block.symmetric_team:
        coefficients[0] = np.log(y.mean()/(1.-y.mean()))
        penalty[0] = 0.

    def objective(beta):
        logits = x @ beta
        return float(np.mean(np.logaddexp(0., logits)-y*logits) + .5*np.sum(penalty*beta*beta))

    converged = False
    for iteration in range(max_iterations):
        p = sigmoid(x @ coefficients)
        gradient = x.T @ (p-y)/len(y) + penalty*coefficients
        if np.max(np.abs(gradient)) <= tolerance:
            converged = True
            break
        weight = np.maximum(p*(1.-p), 1e-8)
        hessian = (x.T*weight) @ x/len(y) + np.diag(penalty+1e-8)
        step = np.linalg.solve(hessian, gradient)
        before = objective(coefficients)
        factor = 1.
        for _ in range(25):
            candidate = coefficients-factor*step
            if objective(candidate) <= before-1e-4*factor*float(gradient@step):
                coefficients = candidate
                break
            factor *= .5
        else:
            raise RuntimeError('Logistic optimization line search failed')
    final_gradient = x.T @ (sigmoid(x @ coefficients)-y)/len(y) + penalty*coefficients
    converged = converged or np.max(np.abs(final_gradient)) <= tolerance
    if not converged or not np.isfinite(coefficients).all():
        raise RuntimeError('Logistic model did not converge to the fixed tolerance')
    model.update(coefficients=coefficients.tolist(), rows=len(y), positive_rows=int(y.sum()),
        iterations=iteration+1, converged=True, gradient_max=float(np.max(np.abs(final_gradient))),
        training_log_loss=float(np.mean(np.logaddexp(0., x@coefficients)-y*(x@coefficients))))
    return model


def predict_logistic(block, model):
    coefficients = np.asarray(model['coefficients'], dtype=float)
    x = transform(block, model)
    if coefficients.shape != (x.shape[1],) or not np.isfinite(coefficients).all():
        raise ValueError('Invalid logistic coefficients')
    return sigmoid(x @ coefficients)


def fit_factorized(examples, options):
    if not examples or any(not isinstance(batch, TrainingExamples) for batch in examples):
        raise TypeError('Split-checked external training examples required')
    for batch in examples:
        if match_role(batch.match_id) != 'train':
            raise PermissionError('A validation/test match cannot enter training')
        if not np.isin(batch.labels, ['H', 'A', 'D']).all():
            raise ValueError('Unknown targets must be excluded before training')
    labels = np.concatenate([batch.labels for batch in examples])
    visible = np.concatenate([batch.ball_visible for batch in examples])
    teams = np.concatenate([batch.both_teams for batch in examples])

    def combine(name):
        blocks = [getattr(batch, name) for batch in examples]
        if any(block.names != blocks[0].names or block.symmetric_team != blocks[0].symmetric_team for block in blocks):
            raise ValueError('Training schemas disagree')
        return FeatureBlock(np.concatenate([block.values for block in blocks]), blocks[0].names,
                            blocks[0].symmetric_team)

    alive = np.isin(labels, ['H', 'A'])
    models = {}
    for name, rows, target in (
        ('state', np.ones(len(labels), dtype=bool), labels == 'D'),
        ('visible_team', alive & visible & teams, labels == 'H'),
        ('collective_team', alive & teams, labels == 'H')):
        block = combine(name)
        subset = FeatureBlock(block.values[rows], block.names, block.symmetric_team)
        models[name] = fit_logistic(subset, target[rows], l2=options['l2'],
            max_iterations=options['max_iterations'], tolerance=options['gradient_tolerance'],
            clip=options['standardized_clip'])
    return {'version': MODEL_VERSION, 'heads': models,
            'training_matches': sorted(set(batch.match_id for batch in examples)),
            'training_scenarios': sorted(set(batch.scenario for batch in examples)),
            'calibration': 'none; uncalibrated logistic estimates',
            'competition_labels_used': False, 'validation_labels_used_for_fit': False}
