"""Frozen CPU inference: supplied tactical tracking plus a self-contained model.

No training, external targets, official checkout, development registry or network.
The float32 observation boundary reproduces the J4/J6 numerical contract.
"""
from __future__ import annotations
import argparse
from dataclasses import replace
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path, PurePosixPath
import platform
import sys
import tempfile
from time import perf_counter
import traceback
import numpy as np

from src import config
from src.features.builder import build_features
from src.features.team_assignment import from_tactical
from src.hygiene.guards import guard_decoded_labels
from src.hygiene.masking import apply_official_masks
from src.models.observations import model_scores
from src.sequential.decoder import decode
from src.sequential.dynamic_matrix import base_costs
from src.utils.loaders import load_atd

VERSION = 'mya-delivery-v1'


def sha256_file(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()


def code_sha(path):
    # Git checkouts may use CRLF. Line endings and a UTF-8 BOM are not code changes.
    text=Path(path).read_text(encoding='utf-8-sig').replace('\r\n','\n')
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def read_json(path):
    def reject(value): raise ValueError('Non-finite JSON value')
    return json.loads(Path(path).read_text(encoding='utf-8-sig'),parse_constant=reject)


def atomic_json(path,value):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.stem+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:
            json.dump(value,f,sort_keys=True,indent=2,allow_nan=False); f.write('\n')
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def load_release(root=None, *, check_runtime=True):
    root=Path(root or config.MYA_DIR).resolve()
    manifest=read_json(root/'release/manifest.json')
    package=read_json(root/'release/model.json')
    if (manifest.get('version')!=VERSION or package.get('version')!=VERSION
            or canonical_sha(package)!=manifest['model_canonical_sha256']
            or manifest['expected_csv_sha256']!=package['origin']['expected_csv_sha256']):
        raise ValueError('Frozen model package integrity differs')
    for name,expected in manifest['code_files'].items():
        rel=PurePosixPath(name)
        if rel.is_absolute() or '..' in rel.parts or not rel.parts or '\\' in name:
            raise ValueError('Unsafe release code path')
        path=(root/Path(*rel.parts)).resolve()
        if not path.is_relative_to(root) or code_sha(path)!=expected:
            raise ValueError('Frozen inference code differs')
    game=package['game']
    if (game['frames']!=config.TOTAL_FRAMES or game['fps']!=config.FPS
            or tuple(game['pitch_dims'])!=tuple(config.PITCH_DIMS)
            or [list(x) for x in config.EVALUATED_INTERVALS]!=game['intervals']
            or list(config.DEAD_ZONE_2HT_INTERVAL)!=game['dead_zone']):
        raise ValueError('Game timeline/geometry differs from final freeze')
    if check_runtime:
        if platform.python_version()!=package['runtime']['python']:
            raise RuntimeError('Use the pinned Python version from release/model.json')
        for name,version in package['runtime']['packages'].items():
            if importlib.metadata.version(name)!=version:
                raise RuntimeError('Install requirements-inference.txt in a clean environment')
    if (package['model']['training_matches']!=['J03WMX','J03WN1','J03WOH','J03WOY']
            or package['prior']['training_matches']!=package['model']['training_matches']
            or package['context']['training_match'] not in package['model']['training_matches']
            or package['context']['labels_used'] is not False
            or package['origin']['public_labels_used'] is not False
            or package['origin']['test_used_for_fit_or_selection'] is not False
            or package['team_scale']!=1. or package['dead_scale']!=2.):
        raise ValueError('Final training provenance or selected configuration differs')
    return package,manifest


def quantize_scores(scores):
    return replace(scores,**{name:np.asarray(getattr(scores,name),dtype=np.float32)
        for name in ('probabilities','p_dead','p_home_given_alive','confidence','hold_age_s')}).validate()


def final_costs(package):
    costs=base_costs(package['prior']).copy()
    costs[0,1]*=package['team_scale']; costs[1,0]*=package['team_scale']
    costs[:2,2]*=package['dead_scale']; costs[2,:2]*=package['dead_scale']
    return costs


def observation_scores(matrix, package):
    return quantize_scores(model_scores(matrix,package['model']))


def validate_csv(path, expected_rows):
    import csv
    count=0
    with Path(path).open(encoding='utf-8',newline='') as handle:
        rows=csv.reader(handle)
        if next(rows,None)!=['frame','label']: raise ValueError('Invalid CSV header')
        for index,row in enumerate(rows):
            if len(row)!=2 or row[0]!=str(index) or row[1] not in ('H','A','D','X'):
                raise ValueError('Invalid CSV timeline or labels')
            count+=1
    if count!=expected_rows: raise ValueError('Incomplete CSV')
    return count


def export_csv(path,labels,expected_sha256):
    labels=np.asarray(labels)
    if labels.ndim!=1 or not len(labels) or not np.isin(labels,['H','A','D','X']).all():
        raise ValueError('Invalid final labels')
    path=Path(path).resolve(); path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix=path.stem+'.',suffix='.csv',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as handle:
            handle.write('frame,label\n')
            handle.writelines(f'{i},{label}\n' for i,label in enumerate(labels))
            handle.flush(); os.fsync(handle.fileno())
        count=validate_csv(tmp,len(labels)); checksum=sha256_file(tmp)
        if checksum!=expected_sha256:
            raise RuntimeError('CSV differs from the frozen J6 candidate; existing output preserved')
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return {'rows':count,'sha256':checksum,'path':str(path)}


def run(data_dir,output=None, *, cache_dir=None,fresh=False,progress=print):
    started=perf_counter()
    package,manifest=load_release()
    data_dir=Path(data_dir).expanduser().resolve()
    tactical=data_dir/'tactical' if (data_dir/'tactical').is_dir() else data_dir
    txt=tactical/'BAR-ATH_tactical_atd.txt'; xml=tactical/'BAR-ATH_tactical_atd.xml'
    if not txt.is_file() or not xml.is_file(): raise FileNotFoundError('Both tactical ATD files are required')
    output=Path(output or config.SUBMISSIONS_DIR/'final/MYA.csv').resolve()
    if output in (txt.resolve(),xml.resolve()): raise ValueError('Output must differ from input')
    cache=Path(cache_dir or config.CACHE_DIR/'delivery/inference').resolve()
    progress('Reading supplied tactical tracking; no labels or external dataset required')
    atd=load_atd('tactical',use_cache=not fresh,save_cache=True,path=txt,xml_path=xml,cache_path=cache/'tracking.npz')
    inputs=from_tactical(atd,intervals=package['game']['intervals'],fps=package['game']['fps'],pitch_dims=package['game']['pitch_dims'])
    progress('Building observation features with frozen external context')
    matrix=build_features(inputs,settings=package['features'],context_model=package['context'])
    scores=observation_scores(matrix,package)
    allowed=np.ones((len(scores.active),3),dtype=bool)
    start,end=package['game']['dead_zone']; allowed[start:end,:2]=False
    progress('Decoding each half with the frozen static costs')
    result=decode(scores,matrix.frame_ids,matrix.period_ids,final_costs(package),package['decoder'],
                  allowed_states=allowed,fps=package['game']['fps'])
    guard_decoded_labels(result.labels,matrix.period_ids,allowed_unknown=result.allowed_unknown)
    if not np.array_equal(apply_official_masks(result.labels),result.labels):
        raise RuntimeError('Official timeline constraints differ')
    artifact=export_csv(output,result.labels,manifest['expected_csv_sha256'])
    report={'version':VERSION,'output':artifact,'fresh_tracking_parse':bool(fresh),
        'tracking_cache_hit':bool(atd['cache_hit']),'input_sha256':{'atd':sha256_file(txt),'xml':sha256_file(xml)},
        'model_canonical_sha256':manifest['model_canonical_sha256'],'release_sha256':canonical_sha(manifest),
        'elapsed_seconds':perf_counter()-started,'runtime':package['runtime'],
        'external_labels_or_training_caches_used':False,'official_repository_required':False,
        'published_dead_zone_all_D':bool((result.labels[start:end]=='D').all()),
        'outside_periods_all_X':bool((result.labels[~scores.active]=='X').all())}
    atomic_json(cache/'inference.json',report)
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--data-dir',type=Path,help='Supplied bundle folder, or its tactical subfolder')
    p.add_argument('--output',type=Path,default=config.SUBMISSIONS_DIR/'final/MYA.csv')
    p.add_argument('--cache-dir',type=Path,default=config.CACHE_DIR/'delivery/inference')
    p.add_argument('--fresh',action='store_true',help='Reparse raw tracking instead of reusing the tracking cache')
    p.add_argument('--verify',action='store_true',help='Check the frozen model, code and installed runtime only')
    args=p.parse_args(argv)
    if not args.verify and args.data_dir is None: p.error('--data-dir is required for inference')
    try:
        if args.verify:
            _,manifest=load_release()
            print(f"Frozen delivery verified; expected CSV SHA256 {manifest['expected_csv_sha256']}")
        else:
            report=run(args.data_dir,args.output,cache_dir=args.cache_dir,fresh=args.fresh,
                       progress=lambda text:print(text,flush=True))
            print(f"Final CSV validated: {report['output']['rows']} rows; SHA256 {report['output']['sha256']}")
        return 0
    except Exception as error:
        args.cache_dir.mkdir(parents=True,exist_ok=True)
        (args.cache_dir/'error.log').write_text(traceback.format_exc(),encoding='utf-8')
        print(f'Delivery failed ({type(error).__name__}); inspect the local cache error.log',file=sys.stderr)
        return 1
