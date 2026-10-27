"""Milestone 4: external training, held-out validation and local observation scores."""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import traceback

import numpy as np

from src import config
from src.build_features import load_matrix
from src.external_benchmark import degrade, period_intervals, predict_external
from src.features.builder import FEATURE_VERSION, FeatureMatrix, build_features
from src.features.team_assignment import from_external
from src.models.dataset import aligned_labels, training_examples
from src.models.observations import ObservationScores, model_scores, rule_scores
from src.models.tabular import MODEL_VERSION, fit_factorized
from src.pipeline import _atomic_json, code_provenance
from src.refinement.exporter import sha256_file
from src.utils.external_data import (atomic_npz, dataset_root, load_inputs, load_targets,
                                     match_role, prepare_match, settings)
from src.utils.official import check_official_revision, load_official_metrics

SCORE_VERSION = 'observation-scores-v1'
ROOT = config.CACHE_DIR / 'observations'


def options():
    result = settings('observation_model.json')
    protocol = settings('external_protocol.json')
    if (result['version'] != SCORE_VERSION or result['train_matches'] != protocol['splits']['train']
            or result['validation_matches'] != protocol['splits']['validation']
            or result['training_seed'] not in protocol['scenario_seeds']
            or not set(result['training_scenarios']) <= {s['name'] for s in protocol['scenarios']}):
        raise ValueError('Observation experiment disagrees with the frozen external protocol')
    return result


def signature():
    return {'experiment_sha256': sha256_file(config.MYA_DIR/'configs/observation_model.json'),
            'external_protocol_sha256': sha256_file(config.MYA_DIR/'configs/external_protocol.json'),
            'feature_settings_sha256': sha256_file(config.MYA_DIR/'configs/features.json'),
            'context_model_sha256': sha256_file(config.CACHE_DIR/'features/context_model.json')}


def context_model():
    value = json.loads((config.CACHE_DIR/'features/context_model.json').read_text())
    if (value.get('feature_version') != FEATURE_VERSION
            or value.get('settings_sha256') != sha256_file(config.MYA_DIR/'configs/features.json')
            or value.get('labels_used') is not False or match_role(value['training_match']) != 'train'):
        raise ValueError('Missing/stale external observation context; run milestone-3 construction')
    return value


def prepare(progress=print):
    opt = options()
    for match in opt['train_matches']+opt['validation_matches']:
        path = dataset_root()/'prepared'/match/'manifest.json'
        if path.is_file():
            load_inputs(match)
            progress(f'{match}: existing input archive verified')
        else:
            progress(f'{match}: downloading/preparing pinned external sources')
            prepare_match(match, progress=progress)


def matrix_for_external(inputs, scenario, seed, context, feature_options):
    observations, quality = degrade(inputs, scenario, seed)
    matrix = build_features(from_external(observations), settings=feature_options, context_model=context)
    matrix.diagnostics['fps'] = inputs.fps
    return observations, matrix, quality


def train(progress=print):
    opt, protocol = options(), settings('external_protocol.json')
    check_official_revision()
    before, stamps = code_provenance(), signature()
    context, feature_options = context_model(), settings('features.json')['settings']
    batches, provenance = [], []
    for match in opt['train_matches']:
        if match_role(match) != 'train':
            raise PermissionError('Training match is not in the frozen training split')
        inputs = load_inputs(match)
        targets = None
        folder = dataset_root()/'prepared'/match
        source = {'match_id': match, 'inputs_sha256': sha256_file(folder/'inputs.npz'),
                  'targets_sha256': sha256_file(folder/'targets.npz'), 'scenarios': []}
        for scenario_name in opt['training_scenarios']:
            scenario = next(s for s in protocol['scenarios'] if s['name'] == scenario_name)
            progress(f'Training observations: {match}, {scenario_name}')
            _, matrix, _ = matrix_for_external(inputs, scenario, opt['training_seed'], context, feature_options)
            # The model-facing feature builder has finished before labels enter.
            if targets is None:
                targets = load_targets(match, purpose='training')
            batch = training_examples(match, scenario_name, matrix, targets,
                maximum_rows=opt['maximum_rows_per_match_scenario'])
            batches.append(batch)
            source['scenarios'].append({'name': scenario_name, 'rows': len(batch.labels),
                'sampling': 'evenly spaced eligible rows over complete match; no frame split'})
            del matrix
        provenance.append(source)
    progress('Fitting three fixed regularized logistic heads on external training rows')
    model = fit_factorized(batches, opt)
    model.update(signatures=stamps, training_inputs=provenance, code=before,
                 feature_version=FEATURE_VERSION, ground_truth_origin='external training matches only')
    if code_provenance()['source_files_sha256'] != before['source_files_sha256'] or signature() != stamps:
        raise RuntimeError('Code/settings changed during training; rebuild the model')
    _atomic_json(ROOT/'model.json', model)
    progress('External model frozen locally; no validation or competition labels used for fitting')
    return model


def load_model():
    model = json.loads((ROOT/'model.json').read_text())
    if model.get('version') != MODEL_VERSION or model.get('signatures') != signature():
        raise ValueError('Observation model/settings/context signatures disagree')
    opt = options()
    if model.get('training_matches') != sorted(opt['train_matches']):
        raise ValueError('Model was not fitted on exactly the frozen training matches')
    for match in model['training_matches']:
        if match_role(match) != 'train':
            raise PermissionError('Model provenance contains a non-training match')
    return model


def save_scores(scores, matrix, folder, provenance):
    scores.validate()
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder/'scores.npz'
    atomic_npz(path, probabilities=scores.probabilities.astype(np.float32),
        p_dead=scores.p_dead.astype(np.float32), p_home_given_alive=scores.p_home_given_alive.astype(np.float32),
        active=scores.active, state_support=scores.state_support, team_support=scores.team_support,
        team_source=scores.team_source, confidence=scores.confidence.astype(np.float32),
        hold_age_s=scores.hold_age_s.astype(np.float32), frame_ids=matrix.frame_ids, period_ids=matrix.period_ids)
    _atomic_json(folder/'manifest.json', {'version': SCORE_VERSION, 'class_order': ['H', 'A', 'D'],
        'shape': list(scores.probabilities.shape), 'scores_sha256': sha256_file(path),
        'provenance': provenance, 'interpretation': 'observation scores, no temporal decoding or adopted submission',
        'team_source_codes': {'0': 'unavailable/prior', '1': 'visible geometry', '2': 'collective', '3': 'hold'},
        'confidence': '1-normalized entropy; not calibrated probability of correctness'})
    return path


def load_scores(folder):
    folder = Path(folder)
    manifest = json.loads((folder/'manifest.json').read_text())
    if (manifest.get('version') != SCORE_VERSION or manifest.get('class_order') != ['H', 'A', 'D']
            or manifest['scores_sha256'] != sha256_file(folder/'scores.npz')):
        raise ValueError('Observation archive signature/schema mismatch')
    with np.load(folder/'scores.npz', allow_pickle=False) as archive:
        expected = {'probabilities', 'p_dead', 'p_home_given_alive', 'active', 'state_support',
                    'team_support', 'team_source', 'confidence', 'hold_age_s', 'frame_ids', 'period_ids'}
        if set(archive.files) != expected:
            raise ValueError('Unexpected observation archive fields')
        arrays = {key: archive[key] for key in expected}
    score_keys = expected-{'frame_ids', 'period_ids'}
    scores = ObservationScores(**{key: arrays[key] for key in score_keys}).validate()
    if (list(scores.probabilities.shape) != manifest['shape']
            or arrays['frame_ids'].shape != scores.active.shape
            or arrays['period_ids'].shape != scores.active.shape
            or not np.issubdtype(arrays['frame_ids'].dtype, np.integer)
            or not np.issubdtype(arrays['period_ids'].dtype, np.integer)
            or not np.array_equal(arrays['period_ids'] > 0, scores.active)):
        raise ValueError('Observation timeline mismatch')
    return scores, arrays['frame_ids'], arrays['period_ids'], manifest


def official_score(metrics, labels, prediction, inputs):
    gt, pred = metrics.label_codes(labels), metrics.label_codes(prediction)
    boundaries = [end for _, end in period_intervals(inputs)[:-1]]
    result = metrics.evaluate(np.insert(gt, boundaries, metrics.X),
                              np.insert(pred, boundaries, metrics.X), bootstrap_n=0)
    return {'spell_f1': float(result['spell_f1_mean']), 'macro_f1': float(result['macro_f1']),
            'n_gt_spells': result['n_gt_spells'], 'n_pred_spells': result['n_pred_spells'],
            'per_class': result['per_class']}


def probability_metrics(labels, scores):
    known = np.isin(labels, ['H', 'A', 'D']) & scores.active
    if not known.any():
        raise ValueError('No known validation labels')
    y = labels[known]
    p = scores.probabilities[known]
    one_hot = np.column_stack((y == 'H', y == 'A', y == 'D')).astype(float)
    dead = scores.p_dead[known]
    alive = y != 'D'
    return {'log_loss': float(-np.mean(np.sum(one_hot*np.log(np.maximum(p, 1e-15)), axis=1))),
            'brier_sum': float(np.mean(np.sum((p-one_hot)**2, axis=1))),
            'dead_brier': float(np.mean((dead-(y == 'D'))**2)),
            'team_brier_alive': float(np.mean((scores.p_home_given_alive[known][alive]-(y[alive] == 'H'))**2)) if alive.any() else None,
            'known_frames': int(known.sum()), 'abstention_frames': int((scores.labels()[known] == 'X').sum())}


def validate(progress=print, *, match_id=None):
    opt, protocol = options(), settings('external_protocol.json')
    if match_id is not None and match_id not in opt['validation_matches']:
        raise PermissionError('Only a frozen validation match can be requested')
    selected = opt['validation_matches'] if match_id is None else [match_id]
    model = load_model()
    before, stamps = code_provenance(), signature()
    context, feature_options = context_model(), settings('features.json')['settings']
    metrics = load_official_metrics()
    model_hash = sha256_file(ROOT/'model.json')
    report = {'version': SCORE_VERSION, 'purpose': 'held-out-match validation, no fitting or model selection',
        'code': before, 'signatures': stamps, 'model_sha256': model_hash,
        'training_matches': opt['train_matches'], 'validation_matches': selected,
        'competition_labels_read': False, 'final_test_accessed': False, 'hyperparameter_searches': 0,
        'automatic_promotion': False, 'calibration_fitted': False, 'runs': []}
    for match in selected:
        if match_role(match) != 'validation':
            raise PermissionError('Validation must concern a held-out validation match')
        inputs = load_inputs(match)
        pending = []
        for scenario in protocol['scenarios']:
            seeds = protocol['scenario_seeds'][:1] if scenario['kind'] == 'clean' else protocol['scenario_seeds']
            for seed in seeds:
                progress(f'Validation predictions: {match}, {scenario["name"]}, seed {seed}')
                observations, matrix, quality = matrix_for_external(inputs, scenario, seed, context, feature_options)
                folder = ROOT/'validation'/match/f'{scenario["name"]}_{seed}'
                provenance = {'match_id': match, 'split': 'validation', 'scenario': scenario,
                    'seed': seed, 'model_sha256': model_hash, 'signatures': stamps,
                    'inputs_sha256': sha256_file(dataset_root()/'prepared'/match/'inputs.npz'),
                    'validation_targets_read_for_prediction': False,
                    'inference_source_files_sha256': before['source_files_sha256']}
                for name, scores in (
                    ('rules', rule_scores(matrix)),
                    ('rules_hold', rule_scores(matrix, with_hold=True, hold_decay_s=opt['hold_decay_s'],
                                               hold_minimum_abs_logit=opt['hold_minimum_abs_logit'])),
                    ('logistic', model_scores(matrix, model))):
                    save_scores(scores, matrix, folder/name, {**provenance, 'candidate': name})
                baseline = predict_external(observations, half_width=protocol['baseline']['half_width'],
                                             missing_label=protocol['baseline']['missing_label'])
                atomic_npz(folder/'baseline.npz', labels=baseline, frame_ids=matrix.frame_ids, period_ids=matrix.period_ids)
                pending.append((scenario['name'], seed, folder, quality))
                del matrix, observations
        # Freeze every candidate for this match before its target archive is opened.
        progress(f'{match}: all predictions saved; now opening validation targets for scoring only')
        targets = load_targets(match, purpose='validation')
        if not np.array_equal(targets.frame_ids, inputs.frame_ids) or not np.array_equal(targets.period_ids, inputs.period_ids):
            raise ValueError('Validation targets are misaligned')
        for scenario_name, seed, folder, quality in pending:
            for name in ('baseline', 'rules', 'rules_hold', 'logistic'):
                entry = {'match_id': match, 'scenario': scenario_name, 'seed': seed, 'candidate': name, **quality}
                if name == 'baseline':
                    with np.load(folder/'baseline.npz', allow_pickle=False) as archive:
                        predicted = archive['labels']
                        if not np.array_equal(archive['frame_ids'], targets.frame_ids):
                            raise ValueError('Baseline validation timeline mismatch')
                else:
                    scores, frames, periods, _ = load_scores(folder/name)
                    if not np.array_equal(frames, targets.frame_ids) or not np.array_equal(periods, targets.period_ids):
                        raise ValueError('Candidate validation timeline mismatch')
                    predicted = scores.labels()
                    entry.update(probability_metrics(targets.labels, scores))
                entry.update(official_score(metrics, targets.labels, predicted, inputs))
                report['runs'].append(entry)
        progress(f'{match}: 19 frozen scenario/seed comparisons scored')
    if before['source_files_sha256'] != code_provenance()['source_files_sha256'] or signature() != stamps:
        raise RuntimeError('Code/settings changed during validation; report not frozen')
    report['summary'] = []
    for match in selected:
        for name in ('baseline', 'rules', 'rules_hold', 'logistic'):
            entries = [row for row in report['runs'] if row['match_id'] == match and row['candidate'] == name]
            report['summary'].append({'match_id': match, 'candidate': name, 'runs': len(entries),
                'mean_spell_f1': float(np.mean([row['spell_f1'] for row in entries])),
                'mean_macro_f1': float(np.mean([row['macro_f1'] for row in entries]))})
    destination = 'validation.json' if match_id is None else f'validation-{match_id}.json'
    _atomic_json(ROOT/destination, report)
    return report


def merge_validation():
    """Combine independently computed matches only with identical frozen provenance."""
    opt = options()
    reports = [json.loads((ROOT/f'validation-{match}.json').read_text()) for match in opt['validation_matches']]
    code = code_provenance()['source_files_sha256']
    model_hash = sha256_file(ROOT/'model.json')
    for match, report in zip(opt['validation_matches'], reports):
        if (report['validation_matches'] != [match] or report['signatures'] != signature()
                or report['model_sha256'] != model_hash or report['code']['source_files_sha256'] != code
                or len(report['runs']) != 76 or any(row['match_id'] != match for row in report['runs'])):
            raise ValueError('Validation reports do not cover identical frozen experiments')
        keys = {(row['scenario'], row['seed'], row['candidate']) for row in report['runs']}
        protocol = settings('external_protocol.json')
        expected = {(scenario['name'], seed, candidate)
            for scenario in protocol['scenarios']
            for seed in (protocol['scenario_seeds'][:1] if scenario['kind'] == 'clean' else protocol['scenario_seeds'])
            for candidate in ('baseline', 'rules', 'rules_hold', 'logistic')}
        if keys != expected or len(keys) != len(report['runs']):
            raise ValueError('Validation scenario coverage mismatch')
    merged = {**reports[0], 'validation_matches': opt['validation_matches'],
              'runs': [run for report in reports for run in report['runs']],
              'summary': [row for report in reports for row in report['summary']]}
    _atomic_json(ROOT/'validation.json', merged)
    return merged


def tactical(progress=print):
    model, opt = load_model(), options()
    before = code_provenance()
    arrays, feature_manifest, schema = load_matrix(config.CACHE_DIR/'features/tactical')
    if feature_manifest['diagnostics']['settings'] != settings('features.json')['settings']:
        raise ValueError('Tactical feature settings disagree')
    matrix = FeatureMatrix(arrays['values'], arrays['valid'], tuple(arrays['names'].tolist()), schema['features'],
                           arrays['frame_ids'], arrays['period_ids'], feature_manifest['diagnostics'])
    if not np.array_equal(matrix.frame_ids, np.arange(config.TOTAL_FRAMES)):
        raise ValueError('Tactical observation output must preserve every video frame')
    frozen_hash = settings('baseline_reference.json')['competition_csv_sha256']
    if sha256_file(config.SUBMISSIONS_DIR/'MYA.csv') != frozen_hash:
        raise ValueError('Baseline submission changed')
    provenance = {'source': 'tactical', 'features_sha256': feature_manifest['features_sha256'],
        'model_sha256': sha256_file(ROOT/'model.json'), 'signatures': signature(), 'code': before,
        'competition_labels_read': False, 'known_dead_zone_forced': False,
        'baseline_csv_unchanged': True, 'no_temporal_decoder': True}
    for name, scores in (
        ('rules', rule_scores(matrix)),
        ('rules_hold', rule_scores(matrix, with_hold=True, hold_decay_s=opt['hold_decay_s'],
                                  hold_minimum_abs_logit=opt['hold_minimum_abs_logit'])),
        ('logistic', model_scores(matrix, model))):
        save_scores(scores, matrix, ROOT/'tactical'/name, {**provenance, 'candidate': name})
        reloaded, _, _, _ = load_scores(ROOT/'tactical'/name)
        if not np.allclose(scores.probabilities, reloaded.probabilities, atol=1e-7, equal_nan=True):
            raise RuntimeError('Observation archive roundtrip differs')
        progress(f'Tactical {name}: complete H/A/D observation scores and uncertainty saved locally')
    if before['source_files_sha256'] != code_provenance()['source_files_sha256']:
        raise RuntimeError('Code changed during tactical inference')
    return provenance


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for action in ('prepare', 'train', 'validate', 'tactical', 'all', 'merge-validation'):
        parser.add_argument(f'--{action}', action='store_true')
    parser.add_argument('--validation-match', help='Optional single frozen validation match; merge independent reports afterwards')
    args = parser.parse_args(argv)
    if not any(getattr(args, key) for key in ('prepare', 'train', 'validate', 'tactical', 'all', 'merge_validation')):
        parser.error('Choose --all or one or more explicit stages')
    try:
        progress = lambda message: print(message, flush=True)
        if args.prepare or args.all: prepare(progress)
        if args.train or args.all: train(progress)
        if args.validate or args.all:
            report = validate(progress, match_id=args.validation_match)
            for row in report['summary']:
                print(f"{row['match_id']} {row['candidate']}: mean spellF1={row['mean_spell_f1']:.4f}, macroF1={row['mean_macro_f1']:.4f}", flush=True)
        if args.merge_validation:
            merged = merge_validation()
            print(f"Merged {len(merged['runs'])} validation comparisons with matching frozen provenance", flush=True)
        if args.tactical or args.all: tactical(progress)
    except Exception as error:
        ROOT.mkdir(parents=True, exist_ok=True)
        (ROOT/'error.log').write_text(traceback.format_exc(), encoding='utf-8')
        print(f'Observation pipeline failed ({type(error).__name__}); inspect .cache/observations/error.log locally', file=sys.stderr)
        return 1
    print('Milestone-4 artifacts remain local; baseline submission unchanged; final test untouched')
    return 0


if __name__ == '__main__': sys.exit(main())
