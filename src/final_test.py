"""One final external test after the delivery package is frozen.

The ordinary development loaders keep J03WR9 locked. This separate entry point
permits only the frozen release, baseline, and the 19 pre-existing conditions.
Results never feed model fitting, a fallback choice or another parameter search.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
from time import perf_counter
import traceback
import numpy as np

from src import config
from src.delivery import (load_release,read_json,canonical_sha,sha256_file,atomic_json,
                          observation_scores,final_costs)
from src.experiments.batch import decode_batch
from src.external_benchmark import degrade,predict_external
from src.features.builder import build_features
from src.features.team_assignment import from_external
from src.sequential_pipeline import score_sequence
from src.source_policy import require_use
from src.utils.external_data import (settings,match_role,download_asset,parse_match,atomic_npz,
    ExternalInputs,ExternalTargets,INPUT_KEYS,PARSER_VERSION)
from src.utils.official import load_official_metrics

ROOT=config.CACHE_DIR/'delivery/final-test'
MATCH='J03WR9'


def conditions():
    protocol=settings('external_protocol.json')
    if protocol['splits']['test']!=[MATCH]: raise PermissionError('Unexpected final test split')
    return [(s,seed) for s in protocol['scenarios'] for seed in
        (protocol['scenario_seeds'][:1] if s['kind']=='clean' else protocol['scenario_seeds'])]


def begin(root=None):
    root=Path(root or ROOT)
    package,manifest=load_release()
    if match_role(MATCH,allow_final_test=True)!='test': raise PermissionError('Not the locked final match')
    require_use('dfl_'+MATCH,'external_validation')
    if len(conditions())!=19: raise ValueError('Final conditions differ from registered coverage')
    stamp={'release_sha256':canonical_sha(manifest),'model_canonical_sha256':manifest['model_canonical_sha256'],
        'expected_competition_csv_sha256':manifest['expected_csv_sha256'],
        'protocol_sha256':canonical_sha(settings('external_protocol.json')),
        'data_manifest_sha256':canonical_sha(settings('dfl_manifest.json')),
        'match_id':MATCH,'methods':['baseline','candidate'],'conditions':[{'scenario':s,'seed':seed} for s,seed in conditions()]}
    root.mkdir(parents=True,exist_ok=True)
    if (root/'result.json').exists() or (root/'consumed.json').exists():
        raise PermissionError('Final test already completed; read the archived result, do not rerun it')
    if (root/'started.json').exists():
        if read_json(root/'started.json')['freeze']!=stamp:
            raise PermissionError('Cannot resume final test with changed model, code, protocol or data')
    else:
        atomic_json(root/'started.json',{'freeze':stamp,'started_utc':datetime.now(timezone.utc).isoformat(),
            'policy':'single frozen evaluation; deterministic interrupted run may resume unchanged; no selection on results'})
    return package,stamp


def prepare(root,stamp,progress):
    """Provider XML includes both observations and labels; write separate archives.

    The parser necessarily sees provider status fields. No targets are returned
    to inference; the target NPZ is opened for scoring only after all predictions.
    """
    root=Path(root); folder=root/'prepared'
    if not (folder/'manifest.json').exists():
        assets=settings('dfl_manifest.json')['matches'][MATCH]
        paths={kind:download_asset(asset,root/'raw',progress=progress) for kind,asset in assets.items()}
        progress('Parsing final-match provider XML into separate observations and targets')
        inputs,targets,report=parse_match(paths['metadata'],paths['positions'],MATCH)
        atomic_npz(folder/'inputs.npz',**inputs.feature_dict())
        atomic_npz(folder/'targets.npz',labels=targets.labels,frame_ids=targets.frame_ids,period_ids=targets.period_ids)
        atomic_json(folder/'manifest.json',{'freeze':stamp,'parser_version':PARSER_VERSION,
            'inputs_sha256':sha256_file(folder/'inputs.npz'),'targets_sha256':sha256_file(folder/'targets.npz'),
            'source_sha256':{k:sha256_file(p) for k,p in paths.items()},'frames':len(inputs.frame_ids),
            'slots':len(inputs.team_mapping),'pitch_dims':inputs.pitch_dims,'ingestion_report':report})
    meta=read_json(folder/'manifest.json')
    if meta['freeze']!=stamp or meta['parser_version']!=PARSER_VERSION or sha256_file(folder/'inputs.npz')!=meta['inputs_sha256']:
        raise ValueError('Final observations differ from the frozen input archive')
    with np.load(folder/'inputs.npz',allow_pickle=False) as a:
        if set(a.files)!=INPUT_KEYS: raise ValueError('Unexpected observation fields')
        inputs=ExternalInputs(**{k:tuple(a[k].tolist()) if k=='pitch_dims' else float(a[k]) if k=='fps' else a[k] for k in INPUT_KEYS})
    return inputs,meta


def verify_snapshot(root,stamp):
    root=Path(root)
    snapshot=read_json(root/'predictions-frozen.json')
    if snapshot['freeze']!=stamp or len(snapshot['predictions'])!=19:
        raise ValueError('Final target access requires all 19 frozen conditions')
    expected={(s['name'],seed) for s,seed in conditions()}
    if {(r['scenario'],r['seed']) for r in snapshot['predictions']}!=expected:
        raise ValueError('Final prediction scenario coverage differs')
    for row in snapshot['predictions']:
        path=root/'predictions'/f"{row['scenario']}_{row['seed']}.npz"
        if sha256_file(path)!=row['sha256']: raise ValueError('Final predictions changed after freeze')
    return snapshot


def scoring_targets(root,stamp):
    root=Path(root)
    verify_snapshot(root,stamp)  # Never open target NPZ without a complete frozen snapshot.
    meta=read_json(root/'prepared/manifest.json')
    path=root/'prepared/targets.npz'
    if meta['freeze']!=stamp or sha256_file(path)!=meta['targets_sha256']:
        raise ValueError('Final scoring targets differ')
    atomic_json(root/'targets-opened.json',{'freeze':stamp,'snapshot_sha256':sha256_file(root/'predictions-frozen.json')})
    with np.load(path,allow_pickle=False) as archive:
        if set(archive.files)!={'labels','frame_ids','period_ids'}: raise ValueError('Unexpected target fields')
        return ExternalTargets(**{k:archive[k] for k in archive.files})


def run(progress=print):
    started=perf_counter()
    pm=load_official_metrics()
    package,stamp=begin()
    inputs,meta=prepare(ROOT,stamp,progress)
    if not (ROOT/'predictions-frozen.json').exists():
        snapshots=[]
        protocol=settings('external_protocol.json')
        for scenario,seed in conditions():
            progress(f'Final test predictions: {MATCH} {scenario["name"]} seed {seed}')
            start=perf_counter()
            observations,quality=degrade(inputs,scenario,seed)
            matrix=build_features(from_external(observations),settings=package['features'],context_model=package['context'])
            scores=observation_scores(matrix,package)
            candidate=decode_batch([scores],matrix.frame_ids,matrix.period_ids,[final_costs(package)])[0]
            baseline=predict_external(observations,half_width=protocol['baseline']['half_width'],missing_label=protocol['baseline']['missing_label'])
            path=ROOT/'predictions'/f'{scenario["name"]}_{seed}.npz'
            atomic_npz(path,labels=np.stack([baseline,candidate]),names=np.array(['baseline','candidate']),
                frame_ids=matrix.frame_ids,period_ids=matrix.period_ids)
            snapshots.append({'scenario':scenario['name'],'seed':seed,'sha256':sha256_file(path),
                'prediction_seconds':perf_counter()-start,'quality':quality})
        atomic_json(ROOT/'predictions-frozen.json',{'freeze':stamp,'predictions':snapshots,
            'frozen_utc':datetime.now(timezone.utc).isoformat(),'semantic_target_archive_opened_for_scoring':False})
    snapshot=verify_snapshot(ROOT,stamp)
    progress('All 19 final conditions frozen; opening separate targets for this single evaluation')
    targets=scoring_targets(ROOT,stamp)
    if not np.array_equal(targets.frame_ids,inputs.frame_ids) or not np.array_equal(targets.period_ids,inputs.period_ids):
        raise ValueError('Final target alignment differs')
    rows=[]
    for row in snapshot['predictions']:
        with np.load(ROOT/'predictions'/f"{row['scenario']}_{row['seed']}.npz",allow_pickle=False) as a:
            if a['names'].tolist()!=['baseline','candidate'] or not np.array_equal(a['frame_ids'],targets.frame_ids) or not np.array_equal(a['period_ids'],targets.period_ids):
                raise ValueError('Frozen final prediction alignment differs')
            labels=a['labels']
        for name,pred in zip(('baseline','candidate'),labels):
            rows.append({'match_id':MATCH,'candidate':name,**row,**score_sequence(pm,targets,pred,inputs,2.)})
    _,manifest_after=load_release()
    if canonical_sha(manifest_after)!=stamp['release_sha256']: raise RuntimeError('Release changed during final evaluation')
    summary=[]
    for name in ('baseline','candidate'):
        group=[r for r in rows if r['candidate']==name]
        summary.append({'candidate':name,'runs':len(group),'mean_spell_f1':float(np.mean([r['spell_f1'] for r in group])),
            'mean_macro_f1':float(np.mean([r['macro_f1'] for r in group])),
            'mean_short_recall':float(np.mean([r['short_segments']['possession']['recall_iou05'] for r in group])),
            'mean_boundary_f1_25f':float(np.mean([r['transitions']['25']['f1'] for r in group]))})
    report={'version':'final-test-v1','freeze':stamp,'summary':summary,'runs':rows,
        'data':{k:meta[k] for k in ('inputs_sha256','targets_sha256','source_sha256','frames','slots','pitch_dims')},
        'official_revision':(config.MYA_DIR/'official-revision.txt').read_text().strip(),
        'completed_utc':datetime.now(timezone.utc).isoformat(),'elapsed_seconds':perf_counter()-started,
        'public_competition_labels_used':False,'test_used_for_fit_or_selection':False,
        'candidate_changed_after_test':False,'snapshot_sha256':sha256_file(ROOT/'predictions-frozen.json')}
    atomic_json(ROOT/'result.json',report)
    atomic_json(ROOT/'consumed.json',{'freeze':stamp,'report_sha256':sha256_file(ROOT/'result.json')})
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--run',action='store_true'); p.add_argument('--show',action='store_true')
    args=p.parse_args(argv)
    if args.run==args.show: p.error('Choose exactly --run or --show')
    try:
        report=run(progress=lambda value:print(value,flush=True)) if args.run else read_json(ROOT/'result.json')
        for row in report['summary']:
            print(f"{MATCH} {row['candidate']}: spellF1={row['mean_spell_f1']:.4f}, macroF1={row['mean_macro_f1']:.4f}",flush=True)
        return 0
    except Exception as error:
        ROOT.mkdir(parents=True,exist_ok=True)
        (ROOT/'error.log').write_text(traceback.format_exc(),encoding='utf-8')
        print(f'Final test stopped ({type(error).__name__}); inspect local final-test/error.log',file=sys.stderr)
        return 1


if __name__=='__main__': raise SystemExit(main())
