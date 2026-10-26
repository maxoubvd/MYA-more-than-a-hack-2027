"""Build milestone-3 observation matrices; no possession targets or scores are read."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import traceback

import numpy as np

from src import config
from src.features.activity import fit_context_model
from src.features.builder import FEATURE_VERSION,DEFAULTS,build_features
from src.features.team_assignment import from_external,from_tactical,attack_directions_from_xml
from src.pipeline import _atomic_json,code_provenance
from src.preprocessing.cache_manager import fingerprint
from src.refinement.exporter import sha256_file
from src.utils.external_data import atomic_npz,dataset_root,load_inputs,settings as external_settings
from src.utils.loaders import load_atd,load_homography,load_smart_tagging
from src.utils.official import check_official_revision


def save_matrix(matrix,folder,provenance):
    folder = Path(folder)
    folder.mkdir(parents=True,exist_ok=True)
    archive = folder/'features.npz'
    atomic_npz(archive,values=matrix.values,valid=matrix.valid,names=np.asarray(matrix.names),
               frame_ids=matrix.frame_ids,period_ids=matrix.period_ids)
    _atomic_json(folder/'schema.json',{'version':FEATURE_VERSION,'features':matrix.schema})
    counts = matrix.valid.sum(axis=0)
    _atomic_json(folder/'manifest.json',{'version':FEATURE_VERSION,'shape':list(matrix.values.shape),
        'features_sha256':sha256_file(archive),'schema_sha256':sha256_file(folder/'schema.json'),
        'column_valid_counts':dict(zip(matrix.names,counts.astype(int).tolist())),
        'provenance':provenance,'diagnostics':matrix.diagnostics})
    return archive


def load_matrix(folder):
    """Load only a validated, matching feature/schema pair; no target interface."""
    folder = Path(folder)
    manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    if manifest['version']!=FEATURE_VERSION or sha256_file(folder/'features.npz')!=manifest['features_sha256'] or sha256_file(folder/'schema.json')!=manifest['schema_sha256']:
        raise ValueError('Feature archive/schema signature mismatch')
    with np.load(folder/'features.npz',allow_pickle=False) as archive:
        expected = {'values','valid','names','frame_ids','period_ids'}
        if set(archive.files)!=expected: raise ValueError('Unexpected feature archive fields')
        arrays = {key:archive[key] for key in expected}
    if arrays['values'].shape!=tuple(manifest['shape']) or arrays['valid'].dtype!=bool or arrays['valid'].shape!=arrays['values'].shape or not np.array_equal(np.isfinite(arrays['values']),arrays['valid']) or np.isinf(arrays['values']).any():
        raise ValueError('Invalid feature matrix or masks')
    schema = json.loads((folder/'schema.json').read_text(encoding='utf-8'))
    rows, columns = arrays['values'].shape
    if (arrays['names'].shape != (columns,) or arrays['frame_ids'].shape != (rows,)
            or arrays['period_ids'].shape != (rows,) or schema.get('version') != FEATURE_VERSION
            or not np.issubdtype(arrays['frame_ids'].dtype,np.integer)
            or not np.issubdtype(arrays['period_ids'].dtype,np.integer)
            or (arrays['period_ids']<0).any()
            or arrays['valid'][arrays['period_ids']==0].any()):
        raise ValueError('Invalid feature timeline or schema version')
    if arrays['names'].tolist()!=[f['name'] for f in schema['features']] or len(arrays['names'])!=len(set(arrays['names'].tolist())):
        raise ValueError('Feature names and schema disagree')
    return arrays,manifest,schema


def build_source(source,*,context_model=None,fit_context=False,progress=None):
    check_official_revision()
    setting_path = config.MYA_DIR/'configs/features.json'
    options = json.loads(setting_path.read_text(encoding='utf-8'))['settings']
    code = code_provenance()
    provenance = {'code':code,'settings_sha256':sha256_file(setting_path),'source':source,
                   'ground_truth_used':False,'training_targets_used':False,'fps':config.FPS}
    if source=='external':
        match = external_settings('external_protocol.json')['smoke_match']
        raw = load_inputs(match)
        inputs = from_external(raw)
        provenance.update(match_id=match,split='train',inputs_sha256=sha256_file(dataset_root()/'prepared'/match/'inputs.npz'))
        matrix = build_features(inputs,settings=options,context_model=context_model,progress=progress)
        if fit_context:
            context_model = fit_context_model(matrix.column('collective_median_speed_mps'),matrix.column('ball_acceleration_mps2'),
                match_id=match,contact_quantile=options['contact_quantile'])
            context_model.update(inputs_sha256=provenance['inputs_sha256'],feature_version=FEATURE_VERSION,settings_sha256=provenance['settings_sha256'])
            matrix.apply_context_model(context_model)
            _atomic_json(config.CACHE_DIR/'features/context_model.json',context_model)
        provenance.update(pitch_dims=raw.pitch_dims,optional_sources='Smart Tagging, homography and attack metadata unavailable; columns masked')
    elif source=='tactical':
        if fit_context: raise PermissionError('Do not fit feature context on the competition match')
        raw = load_atd('tactical')
        inputs = from_tactical(raw,intervals=config.EVALUATED_INTERVALS,fps=config.FPS,pitch_dims=config.PITCH_DIMS)
        directions = attack_directions_from_xml(config.TACTICAL_ATD_XML)
        tags = load_smart_tagging()
        _,errors,valid,_ = load_homography('tactical')
        matrix = build_features(inputs,settings=options,smart_tags=tags,homography=(errors,valid),
                                 attack_directions=directions,context_model=context_model,progress=progress)
        provenance.update(atd=raw['provenance'],smart_tagging=fingerprint(config.TACTICAL_SMART_TAGGING_XML),
            homography=fingerprint(config.TACTICAL_HOMOGRAPHY_CSV),pitch_dims=config.PITCH_DIMS,
            attack_direction_convention='first-half XML team metadata; opposite second-half per EPTS/Kloppy convention; projections only',
            supplied_speed_used=False,supplied_speed_documentation_conflict=raw['speed_documentation_conflict'])
    else:
        raise ValueError('Unknown feature source')
    if context_model is not None:
        provenance['context_model'] = context_model
    if code_provenance()['source_files_sha256']!=code['source_files_sha256']:
        raise RuntimeError('Source changed during feature computation; rerun')
    folder = config.CACHE_DIR/'features'/source
    archive = save_matrix(matrix,folder,provenance)
    reloaded,_,_ = load_matrix(folder)
    if not np.array_equal(matrix.values,reloaded['values'],equal_nan=True) or not np.array_equal(matrix.valid,reloaded['valid']):
        raise RuntimeError('Feature archive roundtrip mismatch')
    return {'source':source,'shape':list(matrix.values.shape),'path':str(archive),'context_model':context_model,
            'matrix':matrix,'roundtrip_equal':True}


def run(source='all',*,progress=None):
    model_path = config.CACHE_DIR/'features/context_model.json'
    # A full/external rebuild replaces the descriptor; do not let an old cache
    # prevent its own regeneration after a configuration change.
    model = json.loads(model_path.read_text(encoding='utf-8')) if source=='tactical' and model_path.is_file() else None
    if model is not None and (model.get('feature_version')!=FEATURE_VERSION or model.get('settings_sha256')!=sha256_file(config.MYA_DIR/'configs/features.json')):
        raise ValueError('Stale context model; rebuild external training features first')
    result = []
    if source in ('all','external'):
        external = build_source('external',fit_context=True,progress=progress)
        model = external['context_model']
        result.append({k:v for k,v in external.items() if k!='matrix'})
    if source in ('all','tactical'):
        tactical = build_source('tactical',context_model=model,progress=progress)
        result.append({k:v for k,v in tactical.items() if k!='matrix'})
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--source',choices=('all','tactical','external'),default='all')
    args = parser.parse_args(argv)
    try:
        results = run(args.source,progress=lambda message:print(message,flush=True))
    except Exception as error:
        path = config.CACHE_DIR/'features/feature-error.log'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(traceback.format_exc(),encoding='utf-8')
        print(f'Feature build failed ({type(error).__name__}); inspect .cache/features/feature-error.log locally',file=sys.stderr)
        return 1
    for item in results:
        print(f"{item['source']}: {item['shape'][0]} frames x {item['shape'][1]} features; masks and archive roundtrip verified")
    print('Local artifacts: .cache/features/; no possession targets or scores read')
    return 0


if __name__=='__main__': sys.exit(main())
