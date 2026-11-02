"""Reproduce fixed J9 decoded quality strata after the full internal grid.

Diagnostic aggregates only, no fitting, candidate selection or submission export.
All framewise archives remain private; the output is a safe aggregate JSON.
"""
from pathlib import Path
import sys,uuid
import numpy as np
from time import process_time
repo=Path(__file__).resolve().parents[1];sys.path.insert(0,str(repo))
from src.bonus import j9
from src.bonus.protocol import protocol,require_use
from src.delivery import read_json,atomic_json,sha256_file
j9.BudgetLedger().can_start(); experiment=j9.register()
start=process_time(); rows=[]
assert (j9.OUT/'results.json').exists()
for match in protocol()['train_matches']:
    require_use(match,'internal_evaluation',held_out=match)
    gt=j9.target(match,[match]).labels
    snapshot=read_json(j9.OUT/'outer'/match/'frozen.json')
    for entry in snapshot['predictions']:
        scenario,seed=entry['scenario_id'],entry['seed']
        if scenario not in ('S2','S3','S6'):continue
        path=j9.OUT/'outer'/match/f'{scenario}_{seed}'/'predictions.npz'
        assert sha256_file(path)==entry['sha256']
        with np.load(path,allow_pickle=False) as a:
            active=(a['period_ids']>0)&np.isin(gt,['H','A','D'])
            masks={'all':active,'visible':active&a['ball_visible'],'invisible':active&~a['ball_visible'],
                   'stationary_visible':active&(a['ball_speed']<.5),
                   'moving_visible':active&(a['ball_speed']>=1.),
                   'visible_bad_link':active&a['ball_visible']&~a['link_valid']}
            for i,candidate in enumerate(j9.CANDIDATES):
                pred=a['labels'][i]
                for stratum,mask in masks.items():
                    alive=mask&np.isin(gt,['H','A']); dead=mask&(gt=='D'); predicted_dead=mask&(pred=='D')
                    rows.append({'candidate':candidate,'match_id':match,'scenario_id':scenario,'seed':seed,'stratum':stratum,
                      'n_known':int(mask.sum()),'n_alive':int(alive.sum()),'n_dead':int(dead.sum()),
                      'false_dead_on_alive':float(np.mean(pred[alive]=='D')) if alive.any() else None,
                      'missed_dead':float(np.mean(np.isin(pred[dead],['H','A']))) if dead.any() else None,
                      'dead_recall':float(np.mean(pred[dead]=='D')) if dead.any() else None})
fields=['n_known','n_alive','n_dead','false_dead_on_alive','missed_dead','dead_recall']
summary=[]
for candidate in j9.CANDIDATES:
    for stratum in sorted({r['stratum'] for r in rows}):
        group=[r for r in rows if r['candidate']==candidate and r['stratum']==stratum]
        item={'candidate':candidate,'stratum':stratum}
        for field in fields:
            match_means=[]; used=0
            for match in protocol()['train_matches']:
                scenario_means=[]
                for scenario in ('S2','S3','S6'):
                    values=[r[field] for r in group if r['match_id']==match and r['scenario_id']==scenario and r[field] is not None]
                    used+=len(values)
                    if values:scenario_means.append(float(np.mean(values)))
                if scenario_means:match_means.append(float(np.mean(scenario_means)))
            item[field]=float(np.mean(match_means)) if match_means else None
            item[field+'_conditions_used']=used
        summary.append(item)
result={'version':'j9-decoded-strata-v1','experiment_id':experiment['experiment_id'],
        'diagnostic_code_sha256':sha256_file(Path(__file__)),'selection_metric_changed':False,'diagnostic_only':True,
        'scope':'S41 only; 36 match/scenario/seed conditions, weights seed then scenario then match; empty denominators excluded explicitly',
        'count_definition':'mean frames per match-condition, not unique events or independent samples',
        'summary':summary,'rows':rows}
atomic_json(repo/'analysis/JALON_9_STRATA.json',result)
j9.BudgetLedger().record_cost('J9-decoded-strata-'+uuid.uuid4().hex,cpu_seconds=process_time()-start)
print('Strata diagnostic saved; no fitting or selection performed')
