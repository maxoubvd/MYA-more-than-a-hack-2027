"""Registered J9 internal experiment runner. No confirmation or competition targets.

Run: python -m src.bonus.j9 --all
Caches are local. Every outer fold refits all preprocessing/context/priors. Inner
OOF calibration refits two training matches, never the outer held-out match.
"""
from __future__ import annotations
import argparse, json, os, uuid
from datetime import datetime, timezone
from time import perf_counter,process_time
from pathlib import Path
import numpy as np
from src import config
from src.delivery import read_json,atomic_json,canonical_sha,code_sha,sha256_file,quantize_scores
from src.bonus.protocol import ROOT,protocol,conditions,fold,require_use,validate_fit_sources,aggregate
from src.bonus.preflight import register as preflight,training_inputs
from src.bonus.budget import BudgetLedger
from src.bonus.degradation import degrade
from src.bonus import j9_models as models
from src.features.builder import build_features,FeatureMatrix
from src.features.team_assignment import from_external
from src.features.activity import fit_context_model
from src.build_features import save_matrix,load_matrix
from src.utils.external_data import load_targets,settings,dataset_root,atomic_npz
from src.external_benchmark import degrade as degrade_v1
from src.sequential.dynamic_matrix import fit_transition_prior
from src.experiments.design import scaled_costs
from src.experiments.batch import decode_batch
from src.sequential_pipeline import score_sequence
from src.utils.official import load_official_metrics

OUT=config.CACHE_DIR/'bonus_v2/j9'
TRAIN_SCENARIOS=['S0','S2','S6']; SEED=20261102
VARIANTS=read_json(ROOT/'j9_grid.json')['variants']
CANDIDATES=['C0-OOF']+[v['id'] for v in VARIANTS]


def source_signature():
    # Include every implementation dependency, not just the three entry points.
    return {p.relative_to(config.MYA_DIR).as_posix():code_sha(p)
            for p in sorted(config.SRC_DIR.rglob('*.py'))}


def register():
    reference=preflight(); ledger=BudgetLedger()
    ledger.seal_grid('J9',VARIANTS)
    for variant in VARIANTS: ledger.register('J9',variant)
    stamp={'version':'j9-internal-v1','J8_experiment_id':reference['experiment_id'],
           'grid_sha256':canonical_sha(read_json(ROOT/'j9_grid.json')),
           'implementation_sha256':canonical_sha(read_json(ROOT/'j9_execution.json')),
           'code':source_signature(),
           'targets_sha256':{m:sha256_file(dataset_root()/'prepared'/m/'targets.npz') for m in protocol()['train_matches']},
           'C0_sha256':sha256_file(config.SUBMISSIONS_DIR/'final/MYA.csv'),
           'J2_sha256':sha256_file(config.SUBMISSIONS_DIR/'MYA.csv'),
           'consumed_test_record_sha256':reference['consumed_J03WR9_record_sha256']}
    path=OUT/'registration.json'
    if path.exists():
        if read_json(path)['fingerprints']!=stamp: raise ValueError('J9 code/data changed after first fit; do not overwrite experiment')
        return read_json(path)
    record={'registered_utc':datetime.now(timezone.utc).isoformat(),'fingerprints':stamp,
            'experiment_id':canonical_sha(stamp),'candidates':CANDIDATES,
            'public_or_confirmation_or_test_targets_read':False}
    atomic_json(path,record); return record


def matrix(match,scenario,seed=SEED,*,v1=False):
    require_use(match,'setup_observations')
    folder=OUT/'features'/match/f'{"V1" if v1 else "V2"}_{scenario}_{seed}'
    stamp={'match_id':match,'scenario':scenario,'seed':seed,'v1':v1,
           'input_sha256':sha256_file(dataset_root()/'prepared'/match/'inputs.npz'),
           'features_settings':canonical_sha(settings('features.json')),
           'J8_protocol':canonical_sha(protocol()),'code':{p:code_sha(config.MYA_DIR/p) for p in
           ['src/bonus/degradation.py','src/features/builder.py']}}
    if (folder/'manifest.json').exists():
        a,manifest,schema=load_matrix(folder)
        if manifest['provenance']!=stamp: raise ValueError('J9 feature cache changed')
        return FeatureMatrix(a['values'],a['valid'],tuple(a['names'].tolist()),schema['features'],
                             a['frame_ids'],a['period_ids'],manifest['diagnostics'])
    inputs=training_inputs(match)
    observed=(degrade_v1(inputs,next(s for s in settings('external_protocol.json')['scenarios'] if s['name']==scenario),seed)[0]
              if v1 else degrade(inputs,scenario,seed).observations)
    result=build_features(from_external(observed),settings=settings('features.json')['settings'])
    result.diagnostics.update(fps=inputs.fps,delivered_slots=int(len(inputs.team_mapping)))
    # Cache training conditions only; held-out-only conditions are used once.
    if v1 or scenario in TRAIN_SCENARIOS and seed==SEED: save_matrix(result,folder,stamp)
    return result


def context_for(training):
    m=sorted(training)[0]; raw=matrix(m,'S0')
    return fit_context_model(raw.column('collective_median_speed_mps'),raw.column('ball_acceleration_mps2'),match_id=m)


def target(match,allowed):
    if match not in allowed or not set(allowed)<=set(protocol()['train_matches']):
        raise PermissionError('Target is outside the explicit fold allowlist')
    return load_targets(match,purpose='training')


def training_batches(training,context,quality=False,v1=False):
    batches=[]
    scenarios=['clean','long_gaps','combined'] if v1 else TRAIN_SCENARIOS
    for m in training:
        labels=target(m,training)
        for s in scenarios:
            raw=matrix(m,s,20261026 if v1 else SEED,v1=v1).apply_context_model(context)
            batches.append(models.examples(m,s,raw,labels,int(raw.diagnostics['delivered_slots']),quality))
    return batches


def fit_pack(training,kind,progress=print):
    training=sorted(training)
    if len(training) not in (2,3) or not set(training)<=set(protocol()['train_matches']):
        raise PermissionError('Only two inner or three outer training matches may fit')
    path=OUT/'fits'/('-'.join(training))/f'{kind}.json'
    if path.exists():
        result=read_json(path)
        if result['model']['training_matches']!=training: raise ValueError('Fit provenance mismatch')
        return result
    progress(f'Fit {kind}: {", ".join(training)}',flush=True)
    context=context_for(training)
    quality=kind.startswith('quality'); balanced=kind.endswith('balanced'); v1=kind=='c0'
    shared=None
    if kind in ('balanced','quality','quality_balanced'):
        plain=fit_pack(training,'plain',progress)
        shared=plain['model']['heads']
    batches=training_batches(training,context,quality,v1)
    model=models.fit(batches,balanced=balanced,shared_teams=shared)
    result={'model':model,'context':context,'kind':kind,'fit_matches':training,
            'context_matches':[context['training_match']],'preprocessing_matches':training}
    atomic_json(path,result); return result


def inner_calibration(training,quality,progress=print):
    kind='quality' if quality else 'plain'
    path=OUT/'calibration'/('-'.join(sorted(training)))/f'{kind}.npz'
    if path.exists():
        with np.load(path,allow_pickle=False) as a: return {k:a[k] for k in a.files}
    collected=[]
    for inner in training:
        inner_training=[m for m in training if m!=inner]
        pack=fit_pack(inner_training,kind,progress)
        if inner in pack['fit_matches'] or not set(pack['fit_matches'])<set(training):
            raise PermissionError('Calibration prediction saw its target match')
        for scenario in TRAIN_SCENARIOS:
            raw=matrix(inner,scenario).apply_context_model(pack['context'])
            scores=models.scores(raw,pack['model'],int(raw.diagnostics['delivered_slots']))
            labels=target(inner,training)
            if not np.array_equal(raw.frame_ids,labels.frame_ids) or not np.array_equal(raw.period_ids,labels.period_ids):
                raise ValueError('Inner calibration timeline mismatch')
            eligible=np.flatnonzero(scores.active & np.isin(labels.labels,['H','A','D']))
            rows=eligible[np.linspace(0,len(eligible)-1,min(len(eligible),12000),dtype=int)]
            collected.append({'dead':scores.p_dead[rows],'home':scores.p_home_given_alive[rows],
                'labels':labels.labels[rows],'state_supported':scores.state_support[rows]>0,
                'team_supported':scores.team_support[rows]>0,'match_id':np.full(len(rows),inner)})
    combined={k:np.concatenate([c[k] for c in collected]) for k in collected[0]}
    atomic_npz(path,**combined); return combined


def outer_packs(held,progress):
    training=fold(held)['training_matches']
    for m in training: require_use(m,'fit',held_out=held)
    prior=fit_transition_prior({m:target(m,training) for m in training})
    packs={'C0-OOF':fit_pack(training,'c0',progress)}
    calibrations={}
    for v in VARIANTS:
        kind=('quality' if v['quality_features'] else 'plain')
        if v['state_loss']=='balanced_dead': kind='quality_balanced' if kind=='quality' else 'balanced'
        base=fit_pack(training,kind,progress)
        calibration=None
        if v['calibration']!='none':
            quality=bool(v['quality_features'])
            if quality not in calibrations: calibrations[quality]=inner_calibration(training,quality,progress)
            rows=calibrations[quality]
            if set(rows['match_id'])!=set(training) or held in rows['match_id']:
                raise PermissionError('Invalid inner calibration match provenance')
            calibration=models.calibrator(**{k:rows[k] for k in ('dead','home','labels','state_supported','team_supported')},
                                          mode=v['calibration'],matches=training)
        packs[v['id']]={**base,'calibration':calibration}
    for candidate,pack in packs.items():
        provenance={k:pack[k] for k in ('fit_matches','context_matches','preprocessing_matches')}
        provenance.update(prior_matches=training,
            calibration_matches=pack.get('calibration',{}).get('training_matches',[]) if pack.get('calibration') else [])
        validate_fit_sources(held,provenance)
        pack['provenance']=provenance
    atomic_json(OUT/'outer'/held/'models.json',{'held_out':held,'packs':packs,'prior':prior})
    return packs,prior


def freeze_outer(held,packs,prior,experiment,progress):
    frozen=[]; costs=scaled_costs(prior,1.,2.); inputs=training_inputs(held)
    for scenario,seed in conditions():
        ident=f'{scenario["id"]}_{seed}'; path=OUT/'outer'/held/ident/'predictions.npz'
        meta=path.with_suffix('.json')
        stamp={'experiment_id':experiment['experiment_id'],'held_out':held,'scenario_id':scenario['id'],'seed':seed,
               'models_sha256':sha256_file(OUT/'outer'/held/'models.json'),'candidates':CANDIDATES,
               'held_out_targets_used_for_prediction':False}
        if path.exists() and meta.exists():
            stored=read_json(meta)
            if stored['provenance']!=stamp or sha256_file(path)!=stored['sha256']:
                raise ValueError('Frozen prediction cache mismatch')
        else:
            progress(f'Predict {held} {ident}: 9 candidates',flush=True)
            raw=matrix(held,scenario['id'],seed)
            scores=[]
            for name in CANDIDATES:
                pack=packs[name]; raw.apply_context_model(pack['context'])
                scores.append(quantize_scores(models.scores(raw,pack['model'],len(inputs.team_mapping),pack.get('calibration'))))
            predictions=decode_batch(scores,raw.frame_ids,raw.period_ids,[costs]*len(scores))
            # Private archives only; safe reports contain aggregate numbers.
            atomic_npz(path,labels=predictions,p_dead=np.stack([s.p_dead for s in scores]),
                       p_home=np.stack([s.p_home_given_alive for s in scores]),
                       frame_ids=raw.frame_ids,period_ids=raw.period_ids,
                       ball_visible=raw.column('ball_observed')==1,
                       ball_speed=raw.column('ball_speed_mps'),
                       link_valid=raw.column('ball_link_valid')==1)
            atomic_json(meta,{'provenance':stamp,'sha256':sha256_file(path)})
        frozen.append({'scenario_id':scenario['id'],'seed':seed,'sha256':sha256_file(path)})
    atomic_json(OUT/'outer'/held/'frozen.json',{'experiment_id':experiment['experiment_id'],'predictions':frozen,
                'held_out_targets_opened_for_scoring_after_snapshot':True})
    return frozen


def probability_metrics(dead,home,labels,mask):
    rows=mask & np.isin(labels,['H','A','D'])
    if not rows.any(): return {'n':0,'log_loss':None,'brier':None,'dead_ece_10':None}
    d=dead[rows]; h=home[rows]; y=labels[rows]; p=np.column_stack([(1-d)*h,(1-d)*(1-h),d])
    truth=np.column_stack([y=='H',y=='A',y=='D'])
    chosen=np.sum(p*truth,axis=1)
    ece=0.
    for i in range(10):
        local=(d>=i/10)&(d<(i+1)/10 if i<9 else d<=1)
        if local.any(): ece+=local.mean()*abs(d[local].mean()-(y[local]=='D').mean())
    return {'n':int(rows.sum()),'log_loss':float(-np.log(np.maximum(chosen,1e-12)).mean()),
            'brier':float(np.mean(np.sum((p-truth)**2,axis=1))),
            'dead_brier':float(np.mean((d-(y=='D'))**2)),
            'dead_ece_10':float(ece)}


def additional_short(pm,targets,pred,inputs):
    from src.sequential_pipeline import period_intervals
    gt,pred=pm.label_codes(targets.labels),pm.label_codes(pred)
    boundaries=[end for _,end in period_intervals(inputs)[:-1]]
    gt,pred=np.insert(gt,boundaries,pm.X),np.insert(pred,boundaries,pm.X)
    runs=pm.valid_runs(gt); pred=pm.fill_abstentions(pred,runs); result={}
    for name,states in [('possession',(pm.H,pm.A)),('dead',(pm.D,))]:
        actual=[x for x in pm.segments(gt,runs) if x[2] in states]
        proposed=[x for x in pm.segments(pred,runs) if x[2] in states]
        flags=pm.matched_gt_flags(pm.spell_overlaps(actual,proposed),len(actual),.5)
        for seconds in (1.,2.,5.):
            short=np.array([b-a<seconds*inputs.fps for a,b,k in actual],bool)
            n=int(short.sum())
            result[f'{name}_lt_{seconds:g}s']={'n_gt':n,'n_matched':int(flags[short].sum()),
                                           'recall':float(flags[short].mean()) if n else None}
    return result


def score_outer(held,experiment,progress):
    # This function is deliberately unreachable until all 22 nine-way predictions exist.
    snapshot=read_json(OUT/'outer'/held/'frozen.json')
    if len(snapshot['predictions'])!=22 or snapshot['experiment_id']!=experiment['experiment_id']:
        raise ValueError('Complete pre-target prediction snapshot required')
    require_use(held,'internal_evaluation',held_out=held)
    targets=target(held,[held]); inputs=training_inputs(held); pm=load_official_metrics(); rows=[]
    for entry in snapshot['predictions']:
        scenario,seed=entry['scenario_id'],entry['seed']; path=OUT/'outer'/held/f'{scenario}_{seed}'/'predictions.npz'
        if sha256_file(path)!=entry['sha256']: raise ValueError('Predictions changed before scoring')
        with np.load(path,allow_pickle=False) as a:
            if not np.array_equal(a['frame_ids'],targets.frame_ids) or not np.array_equal(a['period_ids'],targets.period_ids):
                raise ValueError('Outer scoring timeline mismatch')
            active=inputs.period_ids>0
            for i,name in enumerate(CANDIDATES):
                metrics=score_sequence(pm,targets,a['labels'][i],inputs,2.)
                masks={'all':active,'visible':active&a['ball_visible'],'invisible':active&~a['ball_visible'],
                       'stationary_visible':active&(a['ball_speed']<.5),
                       'moving_visible':active&(a['ball_speed']>=1.),
                       'visible_bad_link':active&a['ball_visible']&~a['link_valid']}
                probability={k:probability_metrics(a['p_dead'][i],a['p_home'][i],targets.labels,mask) for k,mask in masks.items()}
                rows.append({'match_id':held,'candidate':name,'scenario_id':scenario,'seed':seed,**metrics,
                    'short_duration_diagnostics':additional_short(pm,targets,a['labels'][i],inputs),
                    'probability_metrics':probability})
        progress(f'Scored {held} {scenario}_{seed}',flush=True)
    atomic_json(OUT/'outer'/held/'metrics.json',{'experiment_id':experiment['experiment_id'],'rows':rows})
    return rows


def summarize(rows):
    summaries=[]
    def s41(group,getter):
        return float(np.mean([np.mean([getter(r) for r in group if r['match_id']==m and r['scenario_id']==s])
                              for m in protocol()['train_matches'] for s in ('S2','S3','S6')]))
    for name in CANDIDATES:
        group=[r for r in rows if r['candidate']==name]
        item={'candidate':name,**aggregate(group),
              'macro_S41':s41(group,lambda r:r['macro_f1']),
              'dead_f1_S41':s41(group,lambda r:r['per_class']['D']['f1']),
              'dead_recall_S41':s41(group,lambda r:r['per_class']['D']['recall']),
              'short_recall_S41':s41(group,lambda r:r['short_segments']['possession']['recall_iou05']),
              'log_loss_S41':s41(group,lambda r:r['probability_metrics']['all']['log_loss']),
              'brier_S41':s41(group,lambda r:r['probability_metrics']['all']['brier']),
              'dead_ece_S41':s41(group,lambda r:r['probability_metrics']['all']['dead_ece_10'])}
        summaries.append(item)
    ref=summaries[0]; gates=protocol()['adoption']
    for item in summaries:
        item['delta_S41']=item['S41']-ref['S41']
        item['delta_R4']=item['R4']-ref['R4']
        item['match_S41_deltas']={m['match_id']:m['S41']-next(r['S41'] for r in ref['matches'] if r['match_id']==m['match_id']) for m in item['matches']}
        item['internal_gate_checks']={
            'S41_gain':item['delta_S41']>=gates['min_mean_S41_gain'],
            'each_match':min(item['match_S41_deltas'].values())>=-gates['max_match_S41_loss'],
            'R4':item['delta_R4']>=-gates['max_R4_loss'],
            **{key:item[key]-ref[key]>=-gates[gate] for key,gate in [
                ('macro_S41','max_macro_S41_loss'),('dead_f1_S41','max_dead_f1_S41_loss'),
                ('dead_recall_S41','max_dead_recall_S41_loss'),('short_recall_S41','max_short_recall_S41_loss')]}}
        item['passes_internal_gates']=all(item['internal_gate_checks'].values())
    return {'version':'j9-internal-summary-v1','candidates':summaries,
            'ranking_internal_only':[r['candidate'] for r in sorted(summaries[1:],key=lambda r:-r['S41'])],
            'confirmation_required_at_J18':True,'C0_replaced':False,
            'public_labels_read':False,'confirmation_targets_read':False,'consumed_test_reopened':False}


def run(progress=print):
    start=perf_counter(); cpu=process_time(); ledger=BudgetLedger(); ledger.can_start()
    job='J9-'+uuid.uuid4().hex
    try:
        experiment=register(); rows=[]
        for held in protocol()['train_matches']:
            ledger.can_start(); progress(f'Outer holdout: {held}',flush=True)
            packs,prior=outer_packs(held,progress)
            freeze_outer(held,packs,prior,experiment,progress)
            report=OUT/'outer'/held/'metrics.json'
            if report.exists():
                record=read_json(report)
                if record['experiment_id']!=experiment['experiment_id']: raise ValueError('Old metrics mismatch')
                rows.extend(record['rows'])
            else: rows.extend(score_outer(held,experiment,progress))
        result={'experiment_id':experiment['experiment_id'],'rows':rows,**summarize(rows)}
        if len(rows)!=792: raise ValueError('Expected 9 candidates x 4 matches x 22 conditions')
        register() # End-to-end code, data and C0 invariance.
        atomic_json(OUT/'results.json',result)
        atomic_json(config.MYA_DIR/'analysis/JALON_9_RESULTS.json',result)
        return result
    finally:
        cost={'job_id':job,'wall_seconds':perf_counter()-start,'cpu_seconds':process_time()-cpu}
        atomic_json(OUT/'jobs'/f'{job}.json',cost)
        ledger.record_cost(job,cpu_seconds=cost['cpu_seconds'])


def main():
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--all',action='store_true')
    args=p.parse_args()
    if not args.all: p.error('Use --all to execute the sealed eight-configuration internal grid')
    result=run()
    print(json.dumps({k:result[k] for k in ('ranking_internal_only','C0_replaced')},indent=2))

if __name__=='__main__': main()

