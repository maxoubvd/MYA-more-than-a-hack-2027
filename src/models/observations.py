"""Factorized H/A/D observation scores, uncertainty and independent rule reference."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from src.features.builder import FeatureMatrix
from src.imputation.deadball_detector import state_rule_evidence
from src.models.anchors import hold_control
from src.models.dataset import observation_design
from src.models.tabular import MODEL_VERSION, predict_logistic, sigmoid


@dataclass(frozen=True)
class ObservationScores:
    probabilities: np.ndarray  # fixed order H, A, D
    p_dead: np.ndarray
    p_home_given_alive: np.ndarray
    active: np.ndarray
    state_support: np.ndarray
    team_support: np.ndarray
    team_source: np.ndarray  # 0 unavailable/prior, 1 geometry, 2 collective, 3 hold
    confidence: np.ndarray  # 1-normalized entropy, not an accuracy guarantee
    hold_age_s: np.ndarray

    def validate(self):
        n = len(self.active)
        if self.probabilities.shape != (n, 3) or self.active.dtype != bool:
            raise ValueError('Observation score shape mismatch')
        for item in (self.p_dead, self.p_home_given_alive, self.state_support,
                     self.team_support, self.team_source, self.confidence, self.hold_age_s):
            if item.shape != (n,):
                raise ValueError('Observation metadata shape mismatch')
        p = self.probabilities[self.active]
        dead = self.p_dead[self.active]
        home = self.p_home_given_alive[self.active]
        if (not np.isfinite(p).all() or (p < 0).any() or (p > 1).any()
                or not np.allclose(p.sum(axis=1), 1., atol=1e-7)
                or not np.isnan(self.probabilities[~self.active]).all()
                or not np.isfinite(home).all() or ((home < 0) | (home > 1)).any()
                or not np.isfinite(dead).all() or ((dead < 0) | (dead > 1)).any()
                or not np.allclose(p[:, 2], dead, atol=1e-7)
                or not np.allclose(p[:, 0], (1.-dead)*home, atol=1e-7)
                or not np.allclose(p[:, 1], (1.-dead)*(1.-home), atol=1e-7)
                or not np.isfinite(self.confidence[self.active]).all()
                or ((self.confidence[self.active] < 0) | (self.confidence[self.active] > 1)).any()):
            raise ValueError('Invalid factored observation probabilities')
        return self

    def labels(self):
        """Frame-only diagnostic, never a temporal decoder or adopted submission."""
        result = np.full(len(self.active), 'X', dtype='<U1')
        rows = np.flatnonzero(self.active)
        p = self.probabilities[rows]
        maximum = p.max(axis=1)
        unique = (np.abs(p-maximum[:, None]) <= 1e-10).sum(axis=1) == 1
        result[rows[unique]] = np.array(['H', 'A', 'D'])[p[unique].argmax(axis=1)]
        return result


def factor_scores(p_dead, p_home, active, *, state_support, team_support, team_source, hold_age=None):
    active = np.asarray(active, dtype=bool)
    dead, home = np.asarray(p_dead, dtype=float).copy(), np.asarray(p_home, dtype=float).copy()
    n = len(active)
    if dead.shape != (n,) or home.shape != (n,):
        raise ValueError('Binary head timeline mismatch')
    if (not np.isfinite(dead[active]).all() or not np.isfinite(home[active]).all()
            or ((dead[active] < 0) | (dead[active] > 1)).any()
            or ((home[active] < 0) | (home[active] > 1)).any()):
        raise ValueError('Binary head probabilities must lie in [0,1]')
    probabilities = np.column_stack(((1.-dead)*home, (1.-dead)*(1.-home), dead))
    probabilities[~active] = np.nan
    confidence = np.full(n, np.nan)
    p = probabilities[active]
    confidence[active] = np.clip(1.+np.sum(p*np.log(np.maximum(p, 1e-15)), axis=1)/np.log(3.), 0., 1.)
    dead[~active], home[~active] = np.nan, np.nan
    return ObservationScores(probabilities, dead, home, active,
        np.asarray(state_support).copy(), np.asarray(team_support).copy(), np.asarray(team_source, dtype=np.uint8),
        confidence, np.full(n, np.nan) if hold_age is None else np.asarray(hold_age).copy()).validate()


def rule_scores(matrix, *, with_hold=False, hold_decay_s=2., hold_minimum_abs_logit=1.):
    if not isinstance(matrix, FeatureMatrix):
        raise TypeError('Rules require observation features only')
    _, p_dead, state_support = state_rule_evidence(matrix)
    home = matrix.column('H_distance_kernel')
    away = matrix.column('A_distance_kernel')
    supported = np.isfinite(home) & np.isfinite(away) & (matrix.column('ball_observed') == 1)
    logits = np.where(supported, 6.*(home-away), np.nan)
    # Tactical tags can contradict/support control but never enter the state score.
    tag = matrix.column('tag_H_minus_A')
    logits += np.where(supported & np.isfinite(tag), .35*np.tanh(tag), 0.)
    source = np.where(supported, 1, 0).astype(np.uint8)
    age = np.full(len(logits), np.nan)
    if with_hold:
        logits, carried, age = hold_control(logits, p_dead, matrix.period_ids,
            matrix.diagnostics.get('fps', 25.), decay_s=hold_decay_s,
            minimum_abs_logit=hold_minimum_abs_logit)
        source[carried] = 3
    p_home = sigmoid(np.where(np.isfinite(logits), logits, 0.))
    return factor_scores(p_dead, p_home, matrix.period_ids > 0,
        state_support=state_support, team_support=np.isfinite(logits).astype(int), team_source=source, hold_age=age)


def model_scores(matrix, model):
    if model.get('version') != MODEL_VERSION:
        raise ValueError('Unsupported observation model version')
    design = observation_design(matrix)
    dead = predict_logistic(design.state, model['heads']['state'])
    visible = predict_logistic(design.visible_team, model['heads']['visible_team'])
    collective = predict_logistic(design.collective_team, model['heads']['collective_team'])
    # Known absence is not physical state evidence. Empty temporal windows have
    # support=0 (finite), which must not make a fully blind frame look observed.
    physical = [index for index, name in enumerate(design.state.names) if not name.endswith('_support')]
    state_support = np.isfinite(design.state.values[:, physical]).sum(axis=1)
    dead[state_support == 0] = 1./3.
    # A visible ball without two geometric candidates uses the collective head.
    geometry = design.ball_visible & np.isfinite(matrix.column('H_nearest_1_m')) & np.isfinite(matrix.column('A_nearest_1_m'))
    home = np.where(geometry, visible, collective)
    home[~design.both_teams] = .5
    source = np.where(design.both_teams, np.where(geometry, 1, 2), 0)
    team_support = np.where(geometry, np.isfinite(design.visible_team.values).sum(axis=1),
                            np.isfinite(design.collective_team.values).sum(axis=1))
    team_support[~design.both_teams] = 0
    return factor_scores(dead, home, design.active, state_support=state_support,
                         team_support=team_support, team_source=source)
