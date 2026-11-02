"""Read immutable J6 results without requiring today's code to be the J6 code.

The historical registry binds archived result bytes; no DFL target is opened.
"""
from pathlib import Path
from src import config
from src.delivery import read_json,sha256_file


def load_archived_j6():
    registry=read_json(config.MYA_DIR/'analysis/jalon6_experiment_registry.json')
    root=config.CACHE_DIR/'experiments'
    values=[]
    for stage in ('internal','validation'):
        path=root/f'{stage}.json'
        if sha256_file(path)!=registry['frozen_artifacts_sha256'][path.name]:
            raise ValueError('Historical J6 result differs from its published fingerprint')
        value=read_json(path)
        if value['experiment_id']!=registry['experiment_id']:
            raise ValueError('Historical J6 experiment identity differs')
        values.append(value)
    candidate=read_json(root/'candidate.json')
    if (candidate['experiment_id']!=registry['experiment_id'] or candidate['export']['sha256']!=registry['csv_sha256']
            or candidate['family']!=registry['candidate']['family']
            or candidate['team_scale']!=registry['candidate']['team_scale']
            or candidate['dead_scale']!=registry['candidate']['dead_scale']
            or candidate['decision']!=registry['decision']):
        raise ValueError('Historical J6 candidate differs')
    return *values,candidate
