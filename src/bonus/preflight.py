"""J8 preflight: freeze protocol, profile observations and validate stress inputs.

Never fits a predictor or opens possession targets, public labels, confirmation
archives or the consumed test. No candidate metric is computed here.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import importlib.metadata
from pathlib import Path
import platform,subprocess,sys,traceback
from time import perf_counter,process_time
import numpy as np
from src import config
from src.delivery import (load_release,canonical_sha,code_sha,sha256_file,read_json,atomic_json)
from src.bonus.protocol import ROOT,protocol,conditions,require_use
from src.bonus.degradation import degrade,observation_digest
from src.bonus.profiling import observation_profile
from src.bonus.budget import BudgetLedger
from src.utils.external_data import load_inputs,dataset_root
from src.utils.loaders import load_atd
from src.features.team_assignment import from_tactical
from src.utils.external_data import ExternalInputs

OUT=config.CACHE_DIR/'bonus_v2'


def fingerprints():
    _,release=load_release()
    return {'release_sha256':canonical_sha(release),'model_sha256':release['model_canonical_sha256'],
        'expected_C0_csv_sha256':release['expected_csv_sha256'],
        'configurations':{p.name:canonical_sha(read_json(p)) for p in sorted(ROOT.glob('*.json'))},
        'J8_code':{p.relative_to(config.MYA_DIR).as_posix():code_sha(p) for p in sorted((config.SRC_DIR/'bonus').glob('*.py'))},
        'development_inputs':{m:sha256_file(dataset_root()/'prepared'/m/'inputs.npz') for m in protocol()['train_matches']}}


def register():
    stamps=fingerprints(); path=OUT/'registration.json'
    consumed=config.CACHE_DIR/'delivery/final-test/consumed.json'
    if sha256_file(config.SUBMISSIONS_DIR/'final/MYA.csv')!=stamps['expected_C0_csv_sha256'] or not consumed.exists():
        raise ValueError('Frozen C0 CSV or consumed-test marker changed')
    if path.exists():
        record=read_json(path)
        old=record['fingerprints']
        if sha256_file(consumed)!=record['consumed_J03WR9_record_sha256']:
            raise ValueError('Consumed-test record changed')
        # Future stages may ADD modules/config grids, but cannot edit a J8 sealed dependency.
        for group in ('configurations','J8_code'):
            if any(stamps[group].get(k)!=v for k,v in old[group].items()):
                raise ValueError('Registered J8 code/configuration changed; preserve the old experiment')
        for key in ('release_sha256','model_sha256','expected_C0_csv_sha256','development_inputs'):
            if stamps[key]!=old[key]: raise ValueError('Reference or training input changed')
        return record
    tag=subprocess.run(['git','rev-parse','delivery-v1'],cwd=config.MYA_DIR,capture_output=True,text=True,check=True).stdout.strip()
    if tag!='e5d40baa352ef70feacb7125e5ca667629da58ca': raise ValueError('C0 tag differs')
    if sha256_file(config.SUBMISSIONS_DIR/'final/MYA.csv')!=stamps['expected_C0_csv_sha256']:
        raise ValueError('Frozen C0 CSV changed')
    consumed=config.CACHE_DIR/'delivery/final-test/consumed.json'
    if not consumed.exists(): raise ValueError('Expected consumed-test record must remain present')
    record={'version':'bonus-v2-j8','registered_utc':datetime.now(timezone.utc).isoformat(),
        'experiment_id':canonical_sha(stamps),'fingerprints':stamps,'reference_tag':'delivery-v1','reference_commit':tag,
        'consumed_J03WR9_record_sha256':sha256_file(consumed),'new_blind_test_admitted':False,
        'training_or_selection_performed':False,'public_labels_read':False,'target_archives_opened':False}
    atomic_json(path,record)
    return record


def training_inputs(match):
    require_use(match,'setup_observations')
    return load_inputs(match)


def profile(progress):
    registration=register(); rows=[]
    for match in protocol()['train_matches']:
        progress(f'Observation profile, training match {match}')
        rows.append({'source':match,'role':'train_observations_only',**observation_profile(training_inputs(match))})
    progress('Observation profile, complete BAR-ATH evaluated periods; no labels or public-window slicing')
    atd=load_atd('tactical')
    f=from_tactical(atd,intervals=config.EVALUATED_INTERVALS,fps=config.FPS,pitch_dims=config.PITCH_DIMS)
    inputs=ExternalInputs(f.players_xy,f.ball_xy,np.isfinite(f.players_xy).all(axis=-1),np.isfinite(f.ball_xy).all(axis=-1),
        f.team_mapping,f.frame_ids,f.period_ids,f.fps,f.pitch_dims)
    rows.append({'source':'BAR-ATH','role':'unlabelled_sensor_profile_only',**observation_profile(inputs)})
    result={'experiment_id':registration['experiment_id'],'profiles':rows,'target_archives_opened':False}
    atomic_json(OUT/'observation_profiles.json',result)
    return result


def validate_suite(progress):
    registration=register(); rows=[]
    for match in protocol()['train_matches']:
        inputs=training_inputs(match); native=observation_digest(inputs)
        repeat_hash=None
        for scenario,seed in conditions():
            progress(f'Validate observations: {match} {scenario["id"]} seed {seed}')
            result=degrade(inputs,scenario['id'],seed)
            output=result.observations
            if (not np.array_equal(output.frame_ids,inputs.frame_ids) or not np.array_equal(output.period_ids,inputs.period_ids)
                    or not np.array_equal(output.team_mapping,inputs.team_mapping)):
                raise RuntimeError('Degradation changed source identities or timeline')
            digest=observation_digest(output)
            if scenario['id']=='S0' and digest!=native: raise RuntimeError('Native condition differs')
            if scenario['id']=='S6' and seed==protocol()['seeds'][0]: repeat_hash=digest
            durations=[]
            from src.features.team_assignment import period_runs
            for a,b in period_runs(inputs.period_ids):
                miss=~output.ball_observed[a:b]
                edges=np.diff(np.r_[False,miss,False].astype(np.int8))
                durations.extend(((np.flatnonzero(edges==-1)-np.flatnonzero(edges==1))/inputs.fps).tolist())
            from src.bonus.profiling import summarize
            rows.append({'match_id':match,'scenario_id':scenario['id'],'seed':seed,'observations_sha256':digest,
                'quality':result.audit.quality,'actual_ball_gap_duration_s':summarize(durations)})
            del result,output
        repeated=degrade(inputs,'S6',protocol()['seeds'][0])
        if observation_digest(repeated.observations)!=repeat_hash: raise RuntimeError('Real-match degradation is not deterministic')
        if observation_digest(inputs)!=native: raise RuntimeError('Raw observations were modified')
        progress(f'{match}: all 22 conditions valid; repeatable; native arrays unchanged')
    if len(rows)!=88: raise RuntimeError('Incomplete four-match setup validation')
    result={'experiment_id':registration['experiment_id'],'runs':rows,'conditions_per_match':22,'matches':4,
        'model_fits':0,'candidate_scores_computed':0,'labels_read':False,'confirmation_opened':False,'consumed_test_opened':False}
    atomic_json(OUT/'suite-validation.json',result)
    return result


def hardware():
    return {'cpu':read_json(OUT/'cpu.json'),'memory':read_json(OUT/'memory.json'),'display':read_json(OUT/'display.json'),
        'cuda_gpu_verified':False,'cuda_note':'only Intel Iris Xe detected; nvidia-smi unavailable; GPU trials conditional',
        'python':platform.python_version(),'packages':{n:importlib.metadata.version(n) for n in ('numpy','pandas')},
        'extra_dependencies_installed':False}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for key in ('register','profile','validate-suite','all'): p.add_argument('--'+key,action='store_true')
    args=p.parse_args(argv)
    if not any(vars(args).values()): p.error('Choose --all or explicit stages')
    start,cpu=perf_counter(),process_time()
    try:
        progress=lambda message:print(message,flush=True)
        registration=register()
        ledger=BudgetLedger()
        ledger.seal_grid('J9',read_json(ROOT/'j9_grid.json')['variants'])
        ledger.can_start()
        if args.profile or args.all: profile(progress)
        if args.validate_suite or args.all: validate_suite(progress)
        register()  # Detect source/settings/input changes during setup.
        cost=process_time()-cpu
        ledger.record_cost('J8-'+datetime.now(timezone.utc).isoformat(),cpu_seconds=cost)
        output={'experiment_id':registration['experiment_id'],'completed_utc':datetime.now(timezone.utc).isoformat(),
            'setup_wall_seconds':perf_counter()-start,'setup_cpu_seconds':cost,'hardware':hardware(),
            'new_blind_test_admitted':False,'J9_grid_sealed':True,'bonus_configurations_started':0,'model_fits':0,
            'C0_unchanged':True,'labels_read':False,'next_stage':'J9; new stage code/configuration must be registered before fitting'}
        atomic_json(OUT/'preflight.json',output)
        print('J8 setup ready: frozen C0 preserved; V2 suite registered; no predictor fitted or target scored',flush=True)
        return 0
    except Exception as error:
        OUT.mkdir(parents=True,exist_ok=True)
        (OUT/'error.log').write_text(traceback.format_exc(),encoding='utf-8')
        print(f'J8 preflight failed ({type(error).__name__}); inspect .cache/bonus_v2/error.log locally',file=sys.stderr)
        return 1


if __name__=='__main__': raise SystemExit(main())
