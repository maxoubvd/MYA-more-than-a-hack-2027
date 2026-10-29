"""Explicit feature-family ablations; state and team evidence remain separate."""
from dataclasses import replace
import numpy as np

from src.models.dataset import FeatureBlock, observation_design
from src.models.observations import factor_scores
from src.models.tabular import predict_logistic
from src.imputation.deadball_detector import state_rule_evidence

FAMILIES = ('base', 'motion', 'temporal', 'full')
TEMPORAL = ('past_', 'future_', 'recent_exit', 'duration_capped', 'speed_change')
MOTION = ('motion_distance', 'closing_speed', 'velocity_coherence', 'relative_speed',
          'mean_vx', 'mean_vy', 'velocity_observed')


def select_block(block, family):
    if family not in FAMILIES:
        raise ValueError('Unknown registered feature family')
    keep = [i for i, name in enumerate(block.names)
            if (family in ('temporal', 'full') or not any(t in name for t in TEMPORAL))
            and (family in ('motion', 'full') or not any(t in name for t in MOTION))]
    if not keep:
        raise ValueError('Empty ablation block')
    if len(keep) == len(block.names):
        return block
    return FeatureBlock(block.values[:, keep], tuple(block.names[i] for i in keep), block.symmetric_team)


def family_examples(examples, family):
    return [replace(batch, **{key: select_block(getattr(batch, key), family)
                            for key in ('state', 'visible_team', 'collective_team')}) for batch in examples]


def family_scores(matrix, model, *, ablation=None):
    family = model['feature_family']
    design = observation_design(matrix)
    blocks = {name: select_block(getattr(design, name), family)
              for name in ('state', 'visible_team', 'collective_team')}
    dead = predict_logistic(blocks['state'], model['heads']['state'])
    # Availability counters are not physical evidence.
    physical = [i for i, name in enumerate(blocks['state'].names) if not name.endswith('_support')]
    support = np.isfinite(blocks['state'].values[:, physical]).sum(axis=1)
    dead[support == 0] = 1./3.
    visible = predict_logistic(blocks['visible_team'], model['heads']['visible_team'])
    collective = predict_logistic(blocks['collective_team'], model['heads']['collective_team'])
    geometry = (design.ball_visible & np.isfinite(matrix.column('H_nearest_1_m'))
                & np.isfinite(matrix.column('A_nearest_1_m')))
    home = np.where(geometry, visible, collective)
    source = np.where(design.both_teams, np.where(geometry, 1, 2), 0)
    team_support = np.where(geometry, np.isfinite(blocks['visible_team'].values).sum(axis=1),
                            np.isfinite(blocks['collective_team'].values).sum(axis=1))
    home[~design.both_teams] = .5
    team_support[~design.both_teams] = 0
    if ablation == 'no_collective':
        # Intervention on the fallback head only; visible-ball predictions fixed.
        home[~geometry], source[~geometry], team_support[~geometry] = .5, 0, 0
    elif ablation == 'physical_state':
        _, dead, support = state_rule_evidence(matrix)
    elif ablation is not None:
        raise ValueError('Unknown registered intervention')
    return factor_scores(dead, home, design.active, state_support=support,
                         team_support=team_support, team_source=source)


def scaled_costs(prior, team_scale, dead_scale):
    from src.sequential.dynamic_matrix import base_costs
    if not np.isfinite([team_scale, dead_scale]).all() or min(team_scale, dead_scale) <= 0:
        raise ValueError('Positive finite transition scales required')
    costs = base_costs(prior).copy()
    costs[0, 1] *= team_scale
    costs[1, 0] *= team_scale
    costs[:2, 2] *= dead_scale
    costs[2, :2] *= dead_scale
    return costs


def choose_family(rows, tolerance):
    summary = []
    for family in FAMILIES:
        group = [r for r in rows if r['candidate'] == family]
        if len(group) != 12 or len({(r['match_id'], r['scenario']) for r in group}) != 12:
            raise ValueError('Four complete held-out matches and three conditions required')
        summary.append({'family': family, 'mean_spell_f1': float(np.mean([r['spell_f1'] for r in group])),
                        'columns': group[0]['columns']})
    best = max(r['mean_spell_f1'] for r in summary)
    eligible = [r for r in summary if r['mean_spell_f1'] >= best-tolerance]
    selected = min(eligible, key=lambda r: (r['columns'], -r['mean_spell_f1'], r['family']))['family']
    return selected, summary


def choose_temporal(rows, scales, tolerance):
    summary = []
    for i, team in enumerate(scales):
        for j, dead in enumerate(scales):
            group = [r for r in rows if r['team_scale'] == team and r['dead_scale'] == dead]
            if len(group) != 12 or len({(r['match_id'], r['scenario']) for r in group}) != 12:
                raise ValueError('Incomplete internal temporal grid')
            summary.append({'team_scale': team, 'dead_scale': dead, 'grid_i': i, 'grid_j': j,
                'mean_spell_f1': float(np.mean([r['spell_f1'] for r in group])),
                'mean_short_recall': float(np.mean([r['short_segments']['possession']['recall_iou05'] for r in group]))})
    for row in summary:
        neighbours = [r for r in summary if abs(r['grid_i']-row['grid_i'])+abs(r['grid_j']-row['grid_j']) <= 1]
        row['neighbourhood_mean_spell_f1'] = float(np.mean([r['mean_spell_f1'] for r in neighbours]))
        row['neighbourhood_min_spell_f1'] = min(r['mean_spell_f1'] for r in neighbours)
    best = max(r['neighbourhood_mean_spell_f1'] for r in summary)
    eligible = [r for r in summary if r['neighbourhood_mean_spell_f1'] >= best-tolerance]
    selected = min(eligible, key=lambda r: (-r['mean_short_recall'], r['team_scale']+r['dead_scale'],
                                           r['team_scale'], r['dead_scale']))
    return selected, summary


def adoption(summary, gate):
    matches = sorted({r['match_id'] for r in summary})
    if len(matches) != 2:
        raise ValueError('Both confirmation matches are required')
    deltas = []
    for match in matches:
        selected = next(r for r in summary if r['match_id'] == match and r['candidate'] == 'selected')
        ref = next(r for r in summary if r['match_id'] == match and r['candidate'] == gate['reference'])
        deltas.append({'match_id': match, 'spell_delta': selected['mean_spell_f1']-ref['mean_spell_f1'],
                      'short_recall_delta': selected['mean_short_recall']-ref['mean_short_recall']})
    accepted = (np.mean([r['spell_delta'] for r in deltas]) >= gate['minimum_mean_spell_delta']
        and min(r['spell_delta'] for r in deltas) >= gate['minimum_each_match_spell_delta']
        and np.mean([r['short_recall_delta'] for r in deltas]) >= gate['minimum_mean_short_recall_delta'])
    return {'candidate': 'selected' if accepted else gate['fallback'], 'accepted_internal_candidate': bool(accepted),
            'deltas': deltas, 'rule': gate}
