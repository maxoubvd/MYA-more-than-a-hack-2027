"""Milestone-3 integration checks on local observations, with no label reads."""
from __future__ import annotations

from dataclasses import replace
import json
import sys
import traceback
from unittest.mock import patch

import numpy as np

from src import config
from src.build_features import load_matrix
from src.features.builder import build_features
from src.features.team_assignment import from_external,from_tactical,attack_directions_from_xml
from src.external_benchmark import degrade
from src.pipeline import _atomic_json,code_provenance
from src.refinement.exporter import sha256_file
from src.utils.external_data import load_inputs,settings
from src.utils.loaders import load_atd


def check(condition,message):
    if not condition:
        raise AssertionError(message)


def sample(inputs,start=0,size=2048):
    end=min(start+size,len(inputs.frame_ids))
    return replace(inputs,players_xy=inputs.players_xy[start:end],ball_xy=inputs.ball_xy[start:end],
                   frame_ids=inputs.frame_ids[start:end],period_ids=inputs.period_ids[start:end])


def invariant_check(inputs,model,options,**kwargs):
    first=build_features(inputs,context_model=model,settings=options,**kwargs)
    order=np.random.default_rng(20261026).permutation(len(inputs.team_mapping))
    second=build_features(replace(inputs,players_xy=inputs.players_xy[:,order],team_mapping=inputs.team_mapping[order]),
                          context_model=model,settings=options,**kwargs)
    check(first.names==second.names,'Permutation changed schema')
    check(np.array_equal(first.valid,second.valid),'Permutation changed validity')
    check(np.allclose(first.values,second.values,rtol=1e-5,atol=1e-4,equal_nan=True),'Permutation changed feature values')
    return True


def run():
    options=json.loads((config.MYA_DIR/'configs/features.json').read_text())['settings']
    model=json.loads((config.CACHE_DIR/'features/context_model.json').read_text())
    report={'version':'milestone-3-validation-v1','code':code_provenance(),'labels_read':False,
            'target_archives_read':False,'held_out_test_accessed':False,'sources':{},'stress_checks':[]}
    protocol=settings('external_protocol.json')
    # A regression tripwire: future feature work must still avoid every target loader.
    with patch('src.utils.external_data.load_targets',side_effect=AssertionError('Feature validation must not read targets')):
        previous_names=None
        for source,rows in (('external',145967),('tactical',config.TOTAL_FRAMES)):
            arrays,manifest,schema=load_matrix(config.CACHE_DIR/'features'/source)
            names=arrays['names'].tolist()
            check(arrays['values'].shape==(rows,len(names)),'Unexpected complete feature shape')
            check(manifest['diagnostics']['settings']==options,'Feature settings mismatch')
            check(manifest['provenance']['code']['source_files_sha256']==code_provenance()['source_files_sha256'],
                  'Stale feature source provenance; rebuild features')
            check(not manifest['provenance']['ground_truth_used'] and not manifest['provenance']['training_targets_used'],
                  'Feature provenance contains a label read')
            check(not set(names)&set(protocol['forbidden_features']),'Forbidden model field')
            check(previous_names is None or previous_names==names,'Sources have different feature schema')
            previous_names=names
            check(not arrays['valid'][arrays['period_ids']==0].any(),'Non-evaluated frames contain features')
            if source=='external':
                for name in ('H_attack_axis','A_attack_axis','tag_active_n','homography_error_pixels'):
                    check(not arrays['valid'][:,names.index(name)].any(),'Unavailable external sensor invented')
            else:
                check(np.array_equal(arrays['frame_ids'],np.arange(rows)),'Tactical feature alignment changed')
                for name in ('H_attack_axis','A_attack_axis','tag_H_support_n','tag_A_support_n'):
                    check(arrays['valid'][:,names.index(name)].any(),'Expected tactical metadata unavailable')
            check(manifest['diagnostics']['raw_positions_imputed'] is False,'Unexpected ball imputation')
            report['sources'][source]={'shape':list(arrays['values'].shape),'finite_masks':True,
                'matching_schema':True,'archive_roundtrip_verified_by_builder':True,
                'complete_rows':True,'no_infinite_values':True}
            del arrays
        external=load_inputs(protocol['smoke_match'])
        small=replace(external,players_xy_normalized=external.players_xy_normalized[:2048],
            ball_xy_normalized=external.ball_xy_normalized[:2048],players_observed=external.players_observed[:2048],
            ball_observed=external.ball_observed[:2048],frame_ids=external.frame_ids[:2048],period_ids=external.period_ids[:2048])
        for scenario in protocol['scenarios']:
            for seed in protocol['scenario_seeds'][:1 if scenario['kind']=='clean' else None]:
                degraded,_=degrade(small,scenario,seed)
                inputs=from_external(degraded)
                matrix=build_features(inputs,context_model=model,settings=options)
                missing=~np.isfinite(inputs.ball_xy).all(axis=1)
                check(np.isnan(matrix.column('H_nearest_1_m')[missing]).all(),'Missing ball became zero-distance')
                check(np.array_equal(np.isfinite(matrix.values),matrix.valid),'Stress feature mask mismatch')
                check(not np.isinf(matrix.values).any(),'Infinite stress feature')
                invariant_check(inputs,model,options)
                report['stress_checks'].append({'scenario':scenario['name'],'seed':seed,'frames':len(inputs.frame_ids),
                    'permutation_invariant':True,'missingness_preserved':True})
        tactical=load_atd('tactical')
        inputs=from_tactical(tactical,intervals=config.EVALUATED_INTERVALS,fps=config.FPS,pitch_dims=config.PITCH_DIMS)
        report['tactical_permutation_invariant']=invariant_check(sample(inputs,config.EVALUATED_INTERVALS[0][0]),model,options,
            attack_directions=attack_directions_from_xml(config.TACTICAL_ATD_XML))
    baseline=config.SUBMISSIONS_DIR/'MYA.csv'
    reference=json.loads((config.MYA_DIR/'configs/baseline_reference.json').read_text())
    expected=reference.get('competition_csv_sha256')
    check(expected is not None,'Missing frozen baseline signature')
    check(sha256_file(baseline)==expected,'Frozen baseline changed')
    report['baseline_unchanged']=True
    _atomic_json(config.CACHE_DIR/'features/validation.json',report)
    return report


def main():
    try:
        result=run()
    except Exception as error:
        folder=config.CACHE_DIR/'features'
        folder.mkdir(parents=True,exist_ok=True)
        (folder/'validation-error.log').write_text(traceback.format_exc(),encoding='utf-8')
        print(f'Feature validation failed ({type(error).__name__}); inspect .cache/features/validation-error.log locally',file=sys.stderr)
        return 1
    print(f"Feature validation passed: both full matrices, {len(result['stress_checks'])} fixed scenario/seed checks, permutation invariance, baseline unchanged")
    print('No target archives or BAR-ATH labels read; held-out test untouched')
    return 0


if __name__=='__main__': sys.exit(main())
