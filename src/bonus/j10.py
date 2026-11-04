"""J10 registered short-gap/geometry ablations, using exact independent C0 fits.

python -m src.bonus.j10 --prepare
python -m src.bonus.j10 --fold J03WMX
python -m src.bonus.j10 --report
python -m src.bonus.j10 --all
"""
from __future__ import annotations
import argparse,uuid
from datetime import datetime,timezone
from time import perf_counter,process_time
from contextlib import contextmanager
import numpy as np
from src import config
from src.delivery import read_json,atomic_json,canonical_sha,code_sha,sha256_file,quantize_scores
from src.bonus.protocol import ROOT,protocol,conditions,fold,require_use,validate_fit_sources,aggregate
from src.bonus.preflight import register as preflight,training_inputs
from src.bonus.budget import BudgetLedger
from src.bonus.degradation import degrade,observation_digest
from src.bonus.ball_bridges import impute_ball
from src.bonus.geometry_layer import Geometry,append_control,bridge_scores,control_scores
from src.bonus import j9,j9_models
from src.models.dataset import FeatureBlock,training_examples
from src.models.tabular import fit_logistic
from src.experiments.batch import decode_batch
from src.experiments.design import scaled_costs
from src.utils.external_data import atomic_npz,dataset_root,settings
from src.external_benchmark import degrade as degrade_v1
from src.sequential_pipeline import score_sequence
from src.utils.official import load_official_metrics

OUT=config.CACHE_DIR/'bonus_v2/j10'
GRID=read_json(ROOT/'j10_grid.json');VARIANTS=GRID['variants']
IDS=['C0-OOF']+[v['id'] for v in VARIANTS]
OPTIONS=VARIANTS[0]['options']


@contextmanager
def charged(name):
    ledger=BudgetLedger();ledger.can_start();t=process_time();wall=perf_counter();job='J10-'+name+'-'+uuid.uuid4().hex
    try:yield
    finally:
        cost={'job_id':job,'cpu_seconds':process_time()-t,'wall_seconds':perf_counter()-wall}
        atomic_json(OUT/'jobs'/f'{job}.json',cost);ledger.record_cost(job,cpu_seconds=cost['cpu_seconds'])


def register():
    old=preflight();j9reg=read_json(j9.OUT/'registration.json')
    if read_json(ROOT/'j10_grid.json')!=GRID:raise ValueError('Grid changed during execution')
    if sha256_file(config.SUBMISSIONS_DIR/'MYA.csv')!=j9reg['fingerprints']['J2_sha256']:raise ValueError('Historical J2 baseline changed')
    for match,sha in j9reg['fingerprints']['targets_sha256'].items():
        if sha256_file(dataset_root()/'prepared'/match/'targets.npz')!=sha:raise ValueError('Training targets differ from the fixed source')
    # New bonus files are allowed, old experiment dependencies must remain exact.
    for name,sha in j9reg['fingerprints']['code'].items():
        if code_sha(config.MYA_DIR/name)!=sha:raise ValueError('A frozen J9/C0 dependency changed')
    ledger=BudgetLedger();ledger.seal_grid('J10',VARIANTS)
    for v in VARIANTS:ledger.register('J10',v)
    stamp={'J8_experiment_id':old['experiment_id'],'J9_experiment_id':j9reg['experiment_id'],
        'code':{p.relative_to(config.MYA_DIR).as_posix():code_sha(p) for p in sorted(config.SRC_DIR.rglob('*.py'))},
        'grid_sha256':canonical_sha(GRID),'execution_sha256':canonical_sha(read_json(ROOT/'j10_execution.json')),
        'J9_registration_sha256':sha256_file(j9.OUT/'registration.json'),
        'J9_audit_sha256':sha256_file(config.MYA_DIR/'analysis/JALON_9_AUDIT.json'),
        'inputs':{m:sha256_file(dataset_root()/'prepared'/m/'inputs.npz') for m in protocol()['train_matches']},
        'targets':{m:sha256_file(dataset_root()/'prepared'/m/'targets.npz') for m in protocol()['train_matches']},
        'C0_csv_sha256':sha256_file(config.SUBMISSIONS_DIR/'final/MYA.csv'),
        'J2_csv_sha256':sha256_file(config.SUBMISSIONS_DIR/'MYA.csv'),
        'consumed_test_record_sha256':sha256_file(config.CACHE_DIR/'delivery/final-test/consumed.json')}
    path=OUT/'registration.json'
    if path.exists():
        r=read_json(path)
        if r['fingerprints']!=stamp:raise ValueError('J10 code/data changed after registration')
        return r
    r={'version':'j10-internal-v1','registered_utc':datetime.now(timezone.utc).isoformat(),
       'experiment_id':canonical_sha(stamp),'fingerprints':stamp,'candidates':IDS,
       'public_or_confirmation_or_consumed_test_targets_read':False}
    atomic_json(path,r);return r


def reference(held):
    fold(held)
    audit=read_json(config.MYA_DIR/'analysis/JALON_9_AUDIT.json')
    entry=next(x for x in audit['folds'] if x['held_out']==held)
    folder=j9.OUT/'outer'/held
    if sha256_file(folder/'models.json')!=entry['models_sha256'] or sha256_file(folder/'frozen.json')!=entry['snapshot_sha256']:
        raise ValueError('Frozen C0-OOF reference changed')
    data=read_json(folder/'models.json');pack=data['packs']['C0-OOF']
    validate_fit_sources(held,pack['provenance'])
    return pack,data['prior'],entry


def native_scenario(match,name):
    require_use(match,'setup_observations')
    s=next(s for s in settings('external_protocol.json')['scenarios'] if s['name']==name)
    return degrade_v1(training_inputs(match),s,20261026)[0]


def prepare(progress=print):
    experiment=register()
    for m in protocol()['train_matches']:
        for scenario in ('clean','long_gaps','combined'):
            path=OUT/'training'/m/scenario/'control.npz';meta=path.with_suffix('.json')
            stamp={'experiment_id':experiment['experiment_id'],'match_id':m,'scenario':scenario}
            if path.exists() and meta.exists():
                d=read_json(meta)
                if d['provenance']!=stamp or sha256_file(path)!=d['sha256']:raise ValueError('Control cache changed')
                continue
            progress(f'Prepare observation-only local control: {m} {scenario}',flush=True)
            raw=j9.matrix(m,scenario,20261026,v1=True)
            geom=Geometry(native_scenario(m,scenario),raw,OPTIONS)
            atomic_npz(path,control=geom.control,frame_ids=raw.frame_ids,period_ids=raw.period_ids)
            atomic_json(meta,{'provenance':stamp,'sha256':sha256_file(path),'labels_read':False})
    return experiment


def fit_control(held,experiment,progress=print):
    pack,prior,entry=reference(held);training=fold(held)['training_matches']
    path=OUT/'outer'/held/'model.json'
    if path.exists():
        r=read_json(path)
        if r['experiment_id']!=experiment['experiment_id']:raise ValueError('Control head belongs to another experiment')
        validate_fit_sources(held,r['provenance']);return pack,prior,r['head']
    blocks=[];targets=[]
    for match in training:
        require_use(match,'fit',held_out=held);labels=j9.target(match,training)
        for scenario in ('clean','long_gaps','combined'):
            raw=j9.matrix(match,scenario,20261026,v1=True)
            batch=training_examples(match,scenario,raw,labels,maximum_rows=12000)
            archive=OUT/'training'/match/scenario/'control.npz';meta=read_json(archive.with_suffix('.json'))
            if sha256_file(archive)!=meta['sha256'] or meta['provenance']['experiment_id']!=experiment['experiment_id']:
                raise ValueError('Unregistered local-control training features')
            with np.load(archive,allow_pickle=False) as a:
                if not np.array_equal(a['frame_ids'],raw.frame_ids) or not np.array_equal(a['period_ids'],raw.period_ids):raise ValueError('Control training alignment')
                selected=np.searchsorted(raw.frame_ids,batch.frame_ids);control=a['control'][selected]
            known=np.isin(batch.labels,['H','A'])&batch.ball_visible&batch.both_teams
            augmented=append_control(batch.visible_team,control)
            blocks.append(augmented.values[known]);targets.append(batch.labels[known]=='H')
    x=np.concatenate(blocks);y=np.concatenate(targets)
    old=pack['model']['heads']['visible_team']
    if list(augmented.names[:-1])!=old['feature_names'] or len(y)!=old['rows'] or int(y.sum())!=old['positive_rows']:
        raise ValueError('Control and C0 visible heads must use the same training sample')
    progress(f'Fit one 23-feature odd control head excluding {held}',flush=True)
    head=fit_logistic(FeatureBlock(x,augmented.names,True),y)
    provenance={**pack['provenance'],'calibration_matches':[]}
    validate_fit_sources(held,provenance)
    atomic_json(path,{'experiment_id':experiment['experiment_id'],'head':head,'provenance':provenance,
        'C0_models_sha256':entry['models_sha256'],'C0_snapshot_sha256':entry['snapshot_sha256'],
        'same_training_rows_as_C0':True,'state_retrained_or_changed':False})
    return pack,prior,head


def old_predictions(held,scenario,seed):
    snapshot=read_json(j9.OUT/'outer'/held/'frozen.json')
    item=next(x for x in snapshot['predictions'] if x['scenario_id']==scenario and x['seed']==seed)
    path=j9.OUT/'outer'/held/f'{scenario}_{seed}'/'predictions.npz'
    if sha256_file(path)!=item['sha256']:raise ValueError('C0 prediction archive changed')
    with np.load(path,allow_pickle=False) as a:
        return {'labels':a['labels'][0],'dead':a['p_dead'][0],'home':a['p_home'][0],
                'frame_ids':a['frame_ids'],'period_ids':a['period_ids']}


def freeze(held,pack,prior,head,experiment,progress=print):
    require_use(held,'internal_evaluation',held_out=held)
    raw_inputs=training_inputs(held);native_digest=observation_digest(raw_inputs)
    costs=scaled_costs(prior,1.,2.);frozen=[]
    for scenario,seed in conditions():
        sid=scenario['id'];name=f'{sid}_{seed}';path=OUT/'outer'/held/name/'predictions.npz';meta=path.with_suffix('.json')
        stamp={'experiment_id':experiment['experiment_id'],'held_out':held,'scenario_id':sid,'seed':seed,
            'model_sha256':sha256_file(OUT/'outer'/held/'model.json'),'candidates':IDS,
            'possession_targets_used_for_prediction':False,'synthetic_truth_used_for_prediction':False}
        if path.exists() and meta.exists():
            entry=read_json(meta)
            if entry['provenance']!=stamp or sha256_file(path)!=entry['sha256']:raise ValueError('Frozen J10 predictions changed')
        else:
            progress(f'Predict {held} {name}: C0 + eight J10 ablations',flush=True)
            stressed=degrade(raw_inputs,sid,seed).observations
            matrix=j9.matrix(held,sid,seed).apply_context_model(pack['context'])
            base=quantize_scores(j9_models.scores(matrix,pack['model'],len(stressed.team_mapping)))
            old=old_predictions(held,sid,seed)
            for values,key in ((base.p_dead,'dead'),(base.p_home_given_alive,'home'),(matrix.frame_ids,'frame_ids'),(matrix.period_ids,'period_ids')):
                if not np.array_equal(values,old[key],equal_nan=True):raise ValueError('C0 observation replay is not exact')
            geometry=Geometry(stressed,matrix,OPTIONS)
            controlled=control_scores(geometry,base,head)
            bridges={};scores=[base]
            for v in VARIANTS:
                if v['method'] is None:
                    score=controlled
                else:
                    key=(v['method'],v['maximum_frames'])
                    if key not in bridges:bridges[key]=impute_ball(stressed,*key,OPTIONS['bridge'])
                    score=bridge_scores(geometry,controlled if v['control'] else base,bridges[key],
                        head if v['control'] else pack['model']['heads']['visible_team'],control=v['control'])
                scores.append(score)
            # Exact unchanged candidates share the same object, avoiding redundant paths.
            unique=[];mapping=[]
            for score in scores:
                if not np.array_equal(score.p_dead,base.p_dead,equal_nan=True):raise RuntimeError('D observation changed')
                index=next((i for i,s in enumerate(unique) if s is score),None)
                if index is None:index=len(unique);unique.append(score)
                mapping.append(index)
            decoded=decode_batch(unique,matrix.frame_ids,matrix.period_ids,[costs]*len(unique))
            prediction=np.stack([decoded[i] for i in mapping])
            if not np.array_equal(prediction[0],old['labels']):raise ValueError('C0 decoded replay differs from registered J9 reference')
            ordered=[bridges[(v['method'],v['maximum_frames'])] for v in VARIANTS[:6]]
            encoded=np.full(prediction.shape,3,dtype=np.uint8)
            for k,label in enumerate(['H','A','D']):encoded[prediction==label]=k
            atomic_npz(path,labels=encoded,p_dead=base.p_dead,p_home=np.stack([s.p_home_given_alive for s in scores]),
                frame_ids=matrix.frame_ids,period_ids=matrix.period_ids,
                imputed_xy=np.stack([b.layers.imputed_xy for b in ordered]),
                uncertainty_m=np.stack([b.layers.uncertainty_m for b in ordered]),
                age_s=np.stack([b.age_s for b in ordered]),gap_frames=np.stack([b.gap_frames for b in ordered]))
            entry={'provenance':stamp,'sha256':sha256_file(path),'C0_replayed_exactly':True,
                   'all_state_observations_identical':True,'unique_decodes':len(unique),
                   'bridges':{v['id']:b.audit for v,b in zip(VARIANTS[:6],ordered)}}
            atomic_json(meta,entry)
        frozen.append({'scenario_id':sid,'seed':seed,'sha256':entry['sha256']})
    if observation_digest(raw_inputs)!=native_digest:raise RuntimeError('Original observations mutated')
    atomic_json(OUT/'outer'/held/'frozen.json',{'experiment_id':experiment['experiment_id'],'predictions':frozen,
        'possession_and_hidden_position_targets_scored_after_snapshot':True})


def position_accuracy(imputed,sigma,removed,native,pitch,gap_frames):
    eligible=np.isfinite(imputed).all(axis=1)&removed&np.isfinite(native).all(axis=1)
    error=np.linalg.norm((imputed[eligible].astype(float)-native[eligible])*np.asarray(pitch),axis=1)
    row={'n_removed':int(removed.sum()),'n_imputed_hidden':int(eligible.sum()),
         'hidden_filled_fraction':float(eligible.sum()/removed.sum()) if removed.any() else None,
         'rmse_m':float(np.sqrt(np.mean(error**2))) if len(error) else None,
         'mae_m':float(error.mean()) if len(error) else None,
         'p90_error_m':float(np.quantile(error,.9)) if len(error) else None,
         'within_2sigma_fraction':float(np.mean(error<=2*sigma[eligible])) if len(error) else None,
         'by_duration':{}}
    for lo,hi in [(1,5),(6,10),(11,25)]:
        rows=eligible&(gap_frames>=lo)&(gap_frames<=hi)
        e=np.linalg.norm((imputed[rows].astype(float)-native[rows])*np.asarray(pitch),axis=1)
        row['by_duration'][f'{lo}-{hi}']={'n':int(rows.sum()),'squared_error_sum_m2':float(np.sum(e*e)),
                                       'rmse_m':float(np.sqrt(np.mean(e*e))) if len(e) else None}
    return row


def score(held,experiment,progress=print):
    snapshot=read_json(OUT/'outer'/held/'frozen.json')
    if snapshot['experiment_id']!=experiment['experiment_id'] or len(snapshot['predictions'])!=22:
        raise ValueError('All 22 predictions must be frozen before targets')
    require_use(held,'internal_evaluation',held_out=held)
    targets=j9.target(held,[held]);native=training_inputs(held);pm=load_official_metrics();rows=[]
    for entry in snapshot['predictions']:
        sid,seed=entry['scenario_id'],entry['seed'];path=OUT/'outer'/held/f'{sid}_{seed}'/'predictions.npz'
        if sha256_file(path)!=entry['sha256']:raise ValueError('Frozen J10 archive hash mismatch')
        stressed=degrade(native,sid,seed)
        with np.load(path,allow_pickle=False) as a:
            if not np.array_equal(a['frame_ids'],targets.frame_ids) or not np.array_equal(a['period_ids'],targets.period_ids):raise ValueError('J10 targets misaligned')
            labels=np.array(['H','A','D','X'])[a['labels']]
            metric_cache={}
            accuracy=[position_accuracy(a['imputed_xy'][i],a['uncertainty_m'][i],stressed.audit.ball_removed,
                        native.ball_xy_normalized,native.pitch_dims,a['gap_frames'][i]) for i in range(6)]
            for i,candidate in enumerate(IDS):
                key=a['labels'][i].tobytes()
                if key not in metric_cache:
                    metric_cache[key]=(score_sequence(pm,targets,labels[i],native,2.),j9.additional_short(pm,targets,labels[i],native))
                metrics,short=metric_cache[key]
                position=None if i in (0,7) else accuracy[i-1 if i<=6 else 2]
                rows.append({'candidate':candidate,'match_id':held,'scenario_id':sid,'seed':seed,**metrics,
                    'position_accuracy':position,'short_duration_diagnostics':short,
                    'probability_metrics':{'all':j9.probability_metrics(a['p_dead'],a['p_home'][i],targets.labels,native.period_ids>0)}})
        progress(f'Scored {held} {sid}_{seed}',flush=True)
    atomic_json(OUT/'outer'/held/'metrics.json',{'experiment_id':experiment['experiment_id'],'rows':rows})
    return rows


def run_fold(held,progress=print):
    with charged('fold-'+held):
        experiment=register();pack,prior,head=fit_control(held,experiment,progress)
        freeze(held,pack,prior,head,experiment,progress)
        path=OUT/'outer'/held/'metrics.json'
        if path.exists():
            result=read_json(path)
            if result['experiment_id']!=experiment['experiment_id']:raise ValueError('J10 stale metrics')
        else:score(held,experiment,progress)
        register()


def summarize(rows):
    def mean41(group,getter):
        return float(np.mean([np.mean([getter(r) for r in group if r['match_id']==m and r['scenario_id']==s])
                              for m in protocol()['train_matches'] for s in ('S2','S3','S6')]))
    summary=[]
    for candidate in IDS:
        group=[r for r in rows if r['candidate']==candidate]
        s={'candidate':candidate,**aggregate(group),
           'macro_S41':mean41(group,lambda r:r['macro_f1']),
           'dead_f1_S41':mean41(group,lambda r:r['per_class']['D']['f1']),
           'dead_recall_S41':mean41(group,lambda r:r['per_class']['D']['recall']),
           'short_recall_S41':mean41(group,lambda r:r['short_segments']['possession']['recall_iou05']),
           'boundary_f1_12_S41':mean41(group,lambda r:r['transitions']['12']['f1']),
           'boundary_f1_25_S41':mean41(group,lambda r:r['transitions']['25']['f1']),
           'log_loss_S41':mean41(group,lambda r:r['probability_metrics']['all']['log_loss']),
           'brier_S41':mean41(group,lambda r:r['probability_metrics']['all']['brier']),
           'dead_ece_S41':mean41(group,lambda r:r['probability_metrics']['all']['dead_ece_10'])}
        positional=[r for r in group if r['position_accuracy'] is not None]
        s['position_accuracy']=None
        if positional:
            n=sum(r['position_accuracy']['n_imputed_hidden'] for r in positional)
            removed=sum(r['position_accuracy']['n_removed'] for r in positional)
            squared=sum((r['position_accuracy']['rmse_m'] or 0.)**2*r['position_accuracy']['n_imputed_hidden'] for r in positional)
            s['position_accuracy']={'n_imputed_hidden':n,'n_removed':removed,'filled_fraction':n/removed if removed else None,
                                   'pooled_rmse_m':float(np.sqrt(squared/n)) if n else None,'per_scenario':{}}
            for scenario in protocol()['scenarios']:
                sub=[r['position_accuracy'] for r in positional if r['scenario_id']==scenario['id']]
                k=sum(r['n_imputed_hidden'] for r in sub);removed_s=sum(r['n_removed'] for r in sub)
                error=sum((r['rmse_m'] or 0.)**2*r['n_imputed_hidden'] for r in sub)
                s['position_accuracy']['per_scenario'][scenario['id']]={'n_imputed_hidden':k,'n_removed':removed_s,
                    'filled_fraction':k/removed_s if removed_s else None,'pooled_rmse_m':float(np.sqrt(error/k)) if k else None}
        summary.append(s)
    ref=summary[0];gate=protocol()['adoption']
    for item in summary:
        item['delta_S41']=item['S41']-ref['S41'];item['delta_R4']=item['R4']-ref['R4']
        item['match_S41_deltas']={m['match_id']:m['S41']-next(r['S41'] for r in ref['matches'] if r['match_id']==m['match_id']) for m in item['matches']}
        item['internal_gate_checks']={'S41_gain':item['delta_S41']>=gate['min_mean_S41_gain'],
            'each_match':min(item['match_S41_deltas'].values())>=-gate['max_match_S41_loss'],
            'R4':item['delta_R4']>=-gate['max_R4_loss'],
            **{key:item[key]-ref[key]>=-gate[g] for key,g in [('macro_S41','max_macro_S41_loss'),
                ('dead_f1_S41','max_dead_f1_S41_loss'),('dead_recall_S41','max_dead_recall_S41_loss'),
                ('short_recall_S41','max_short_recall_S41_loss')]}}
        item['passes_internal_gates']=all(item['internal_gate_checks'].values())
    return {'version':'j10-internal-results-v1','candidates':summary,
            'ranking_internal_only':[r['candidate'] for r in sorted(summary[1:],key=lambda r:-r['S41'])],
            'C0_replaced':False,'confirmation_required_at_J18':True,'public_labels_read':False,
            'confirmation_targets_read':False,'consumed_test_reopened':False,'rows':rows}


def report():
    with charged('aggregate'):
        experiment=register();rows=[]
        for held in protocol()['train_matches']:
            data=read_json(OUT/'outer'/held/'metrics.json')
            if data['experiment_id']!=experiment['experiment_id']:raise ValueError('Cannot mix experiments')
            rows.extend(data['rows'])
        if len(rows)!=792 or len({(r['candidate'],r['match_id'],r['scenario_id'],r['seed']) for r in rows})!=792:
            raise ValueError('Expected complete nine-candidate, four-match, 22-condition coverage')
        old=read_json(j9.OUT/'results.json')
        for row in [r for r in rows if r['candidate']=='C0-OOF']:
            ref=next(r for r in old['rows'] if r['candidate']=='C0-OOF' and all(r[k]==row[k] for k in ('match_id','scenario_id','seed')))
            if any(row[k]!=ref[k] for k in ('spell_f1','macro_f1','n_pred_spells','n_pred_segments')):raise ValueError('C0 benchmark changed')
        result={'experiment_id':experiment['experiment_id'],**summarize(rows)}
        atomic_json(OUT/'results.json',result);atomic_json(config.MYA_DIR/'analysis/JALON_10_RESULTS.json',result)
        atomic_json(config.MYA_DIR/'analysis/JALON_10_REGISTRATION.json',experiment)
        return result


def main():
    p=argparse.ArgumentParser(description=__doc__);g=p.add_mutually_exclusive_group(required=True)
    g.add_argument('--prepare',action='store_true');g.add_argument('--fold',choices=protocol()['train_matches'])
    g.add_argument('--report',action='store_true');g.add_argument('--all',action='store_true');args=p.parse_args()
    if args.prepare or args.all:
        with charged('prepare'):prepare()
    if args.fold:run_fold(args.fold)
    if args.all:
        for held in protocol()['train_matches']:run_fold(held)
    if args.report or args.all:
        result=report();print(result['ranking_internal_only'])

if __name__=='__main__':main()
