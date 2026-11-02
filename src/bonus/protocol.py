"""Frozen V2 configuration and data-use gates; confirmation is not a J8 action."""
from pathlib import Path
import numpy as np
from src import config
from src.delivery import read_json,canonical_sha

ROOT=config.MYA_DIR/'configs/bonus_v2'


def protocol():
    p=read_json(ROOT/'protocol.json')
    if (p['version']!='bonus-v2-j8' or p['fps']!=25. or p['seeds']!=[20261102,20261103,20261104]
            or p['excluded_matches']!=['J03WR9'] or p['novel_test_matches']
            or [s['id'] for s in p['scenarios']]!=[f'S{i}' for i in range(8)]
            or [s['missing_fraction'] for s in p['scenarios']]!=[0,.2,.41,.41,.6,0,.41,.6]):
        raise ValueError('V2 protocol differs from the registered J8 design')
    if (len(set(p['train_matches']))!=4 or len(set(p['confirmation_matches']))!=2
            or set(p['train_matches'])&set(p['confirmation_matches'])
            or set(p['excluded_matches'])&set(p['train_matches']+p['confirmation_matches'])):
        raise ValueError('Invalid match split')
    for s in p['scenarios']:
        if s['missing_fraction'] and (not s['gap_frames'] or not 1<=s['gap_frames'][0]<=s['gap_frames'][1]):
            raise ValueError('Invalid gap duration')
    return p


def conditions():
    p=protocol()
    return [(s,seed) for s in p['scenarios'] for seed in (p['seeds'][:1] if s['id']=='S0' else p['seeds'])]


def fold(held_out):
    p=protocol()
    if held_out not in p['train_matches']: raise PermissionError('Only four training matches can be internal holdouts')
    return {'held_out':held_out,'training_matches':[m for m in p['train_matches'] if m!=held_out]}


def require_use(match,purpose,*,held_out=None):
    p=protocol()
    if match not in p['train_matches']:
        raise PermissionError('J8-J17 cannot read confirmation, consumed test, public labels or unadmitted sources')
    if purpose=='setup_observations': return
    spec=fold(held_out)
    if purpose in ('fit','context','preprocessing','prior','calibration') and match in spec['training_matches']: return
    if purpose=='internal_evaluation' and match==held_out: return
    raise PermissionError('Match/purpose does not respect the outer fold')


def validate_fit_sources(held_out,provenance):
    allowed=set(fold(held_out)['training_matches'])
    for key in ('fit_matches','context_matches','preprocessing_matches','prior_matches','calibration_matches'):
        if key not in provenance or not set(provenance[key])<=allowed:
            raise PermissionError('Outer holdout or forbidden match entered fitting/calibration')
    if set(provenance['fit_matches'])!=allowed:
        raise ValueError('Internal C0/bonus fit must use exactly the other three matches')
    return True


def aggregate(rows):
    """One candidate, complete 22-condition coverage; no frame slicing/concatenation."""
    p=protocol(); expected={(s['id'],seed) for s,seed in conditions()}
    matches=sorted({r['match_id'] for r in rows})
    if not matches or not set(matches)<=set(p['train_matches']+p['confirmation_matches']):
        raise PermissionError('Only registered development/confirmation identities can be aggregated')
    output=[]
    for match in matches:
        group=[r for r in rows if r['match_id']==match]
        keys={(r['scenario_id'],r['seed']) for r in group}
        if keys!=expected or len(group)!=len(expected): raise ValueError('Incomplete/duplicate V2 coverage')
        if any(not np.isfinite(r['spell_f1']) or not 0<=r['spell_f1']<=1 for r in group): raise ValueError('Invalid spellF1')
        per_scenario={s['id']:float(np.mean([r['spell_f1'] for r in group if r['scenario_id']==s['id']])) for s in p['scenarios']}
        per_level={str(level):float(np.mean([per_scenario[s['id']] for s in p['scenarios'] if s['missing_fraction']==level])) for level in p['robustness_metric']['levels']}
        output.append({'match_id':match,'S41':float(np.mean([per_scenario[s] for s in p['primary_metric']['scenario_ids']])),
            'R4':float(np.mean(list(per_level.values()))),'per_scenario':per_scenario,'per_level':per_level})
    return {'matches':output,'S41':float(np.mean([r['S41'] for r in output])),'R4':float(np.mean([r['R4'] for r in output]))}
