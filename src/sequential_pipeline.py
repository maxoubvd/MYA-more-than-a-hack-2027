"""Milestone 5: train-only soft priors, external comparison and complete CSV export."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from time import perf_counter
import traceback

import numpy as np

from src import config
from src.build_features import load_matrix
from src.features.builder import FeatureMatrix
from src.models.observations import model_scores
from src.observation_pipeline import (context_model, load_model, load_scores, matrix_for_external,
                                      signature as observation_signature)
from src.external_benchmark import period_intervals, predict_external
from src.hygiene.masking import apply_official_masks
from src.pipeline import _atomic_json, code_provenance
from src.refinement.exporter import export_submission, sha256_file
from src.sequential.decoder import SequenceResult, decode
from src.sequential.dynamic_matrix import (BoundaryCues, CUE_NAMES, base_costs, boundary_cues,
                                          fit_transition_prior, transition_costs)
from src.utils.external_data import atomic_npz, dataset_root, load_inputs, load_targets, match_role, settings
from src.utils.official import check_official_revision, load_official_metrics

VERSION = 'sequential-v1'
ROOT = config.CACHE_DIR/'sequential'
OBS = config.CACHE_DIR/'observations'


def options():
    opt = settings('sequential.json')
    if (opt['version'] != VERSION or opt['comparisons'] != ['baseline', 'raw_logistic', 'static', 'dynamic']
            or opt['primary_decoder'] != 'dynamic' or opt['hyperparameter_search_budget'] != 0
            or opt['minimum_duration_frames'] is not None or opt['initial_prior'] != 'uniform'):
        raise ValueError('Sequential experiment differs from the frozen milestone-5 design')
    positive = ('transition_pseudocount', 'emission_weight', 'probability_floor', 'control_context_s',
        'contact_distance_scale_m', 'exit_memory_s', 'restart_context_s', 'boundary_profile_radius_s',
        'short_segment_diagnostic_s')
    if (not all(np.isfinite(opt[key]) and opt[key] > 0 for key in positive)
            or not 0 < opt['probability_floor'] < 1./3.
            or not 0 <= opt['maximum_cost_reduction'] < 1
            or type(opt['contact_half_window_frames']) is not int or opt['contact_half_window_frames'] < 1
            or not np.isfinite([opt['boundary_margin_m'], opt['boundary_near_optimal_log_gap']]).all()
            or min(opt['boundary_margin_m'], opt['boundary_near_optimal_log_gap']) < 0):
        raise ValueError('Invalid sequential scales')
    return opt


def signatures():
    return {'decoder_settings_sha256': sha256_file(config.MYA_DIR/'configs/sequential.json'),
            'observation_model_sha256': sha256_file(OBS/'model.json'),
            'observation_signatures': observation_signature()}


def fit_prior(progress=print):
    check_official_revision()
    opt, protocol = options(), settings('external_protocol.json')
    code, stamp = code_provenance(), signatures()
    targets, sources = {}, []
    for match in protocol['splits']['train']:
        if match_role(match) != 'train':
            raise PermissionError('Only training matches may fit temporal parameters')
        progress(f'Transition supervision: external training match {match}')
        targets[match] = load_targets(match, purpose='training')
        sources.append({'match_id': match,
            'targets_sha256': sha256_file(dataset_root()/'prepared'/match/'targets.npz')})
    prior = fit_transition_prior(targets, pseudocount=opt['transition_pseudocount'])
    prior.update(signatures=stamp, sources=sources, code=code, validation_used_for_fit=False,
                 public_labels_read=False, hyperparameter_searches=0)
    if code_provenance()['source_files_sha256'] != code['source_files_sha256'] or signatures() != stamp:
        raise RuntimeError('Code/settings changed during transition fitting')
    _atomic_json(ROOT/'prior.json', prior)
    return prior


def load_prior():
    prior = json.loads((ROOT/'prior.json').read_text())
    if prior.get('signatures') != signatures() or prior.get('training_matches') != sorted(settings('external_protocol.json')['splits']['train']):
        raise ValueError('Temporal prior has incompatible model/settings/splits')
    for match in prior['training_matches']:
        if match_role(match) != 'train':
            raise PermissionError('Temporal prior contains non-training supervision')
    base_costs(prior)
    return prior


def _baseline(path, frames, periods):
    with np.load(path, allow_pickle=False) as archive:
        if (set(archive.files) != {'labels', 'frame_ids', 'period_ids'}
                or not np.array_equal(archive['frame_ids'], frames)
                or not np.array_equal(archive['period_ids'], periods)):
            raise ValueError('Frozen baseline archive is misaligned')
        labels = archive['labels']
    if labels.shape != frames.shape or not np.isin(labels, ['H', 'A', 'D', 'X']).all():
        raise ValueError('Invalid baseline labels')
    return labels


def external_cues(match, scenario, seed, inputs, scores, frames, periods, manifest, opt, model):
    """Cache only four observation cues; no target interface in this function."""
    folder = ROOT/'cues'/match/f'{scenario["name"]}_{seed}'
    frozen = OBS/'validation'/match/f'{scenario["name"]}_{seed}'
    code = code_provenance()['source_files_sha256']
    dependencies = {name: digest for name, digest in code.items() if name.startswith(('src/features/', 'src/preprocessing/'))
                    or name in ('src/imputation/gap_analyzer.py', 'src/models/observations.py',
                                'src/sequential/dynamic_matrix.py', 'src/observation_pipeline.py')}
    stamp = {'inputs_sha256': sha256_file(dataset_root()/'prepared'/match/'inputs.npz'),
        'scores_sha256': manifest['scores_sha256'], 'baseline_sha256': sha256_file(frozen/'baseline.npz'),
        'observation_signatures': observation_signature(), 'observation_model_sha256': sha256_file(OBS/'model.json'),
        'cue_code': dependencies, 'cue_options': {key: opt[key] for key in (
            'control_context_s', 'contact_distance_scale_m', 'contact_half_window_frames',
            'boundary_margin_m', 'exit_memory_s', 'restart_context_s')}}
    meta_path = folder/'manifest.json'
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text())
        if meta.get('signatures') == stamp and sha256_file(folder/'cues.npz') == meta['sha256']:
            with np.load(folder/'cues.npz', allow_pickle=False) as archive:
                if (set(archive.files) != {'values', 'valid', 'names', 'frame_ids', 'period_ids'}
                        or not np.array_equal(archive['frame_ids'], frames)
                        or not np.array_equal(archive['period_ids'], periods)
                        or archive['names'].tolist() != list(CUE_NAMES)
                        or archive['values'].shape != (len(frames), 4)
                        or not np.array_equal(np.isfinite(archive['values']), archive['valid'])):
                    raise ValueError('Invalid boundary cue cache')
                cues = BoundaryCues(archive['values'])
            return cues, meta['quality']
    observations, matrix, quality = matrix_for_external(inputs, scenario, seed, context_model(), settings('features.json')['settings'])
    recomputed = model_scores(matrix, model)
    if (not np.array_equal(matrix.frame_ids, frames) or not np.array_equal(matrix.period_ids, periods)
            or not np.allclose(recomputed.probabilities, scores.probabilities, atol=1e-7, rtol=0, equal_nan=True)):
        raise ValueError('Recomputed observation scores differ from the frozen milestone-4 artifact')
    baseline = _baseline(frozen/'baseline.npz', frames, periods)
    protocol = settings('external_protocol.json')
    direct = predict_external(observations, half_width=protocol['baseline']['half_width'],
                              missing_label=protocol['baseline']['missing_label'])
    if not np.array_equal(baseline, direct):
        raise ValueError('Frozen baseline differs from the unchanged published reference')
    cues = boundary_cues(matrix, scores, opt)
    atomic_npz(folder/'cues.npz', values=cues.values, valid=np.isfinite(cues.values),
        names=np.asarray(cues.names), frame_ids=frames, period_ids=periods)
    _atomic_json(meta_path, {'signatures': stamp, 'quality': quality, 'sha256': sha256_file(folder/'cues.npz'),
        'target_archives_read': False, 'frozen_observations_reproduced': True})
    return cues, quality


def save_sequence(result, frames, periods, folder, provenance):
    folder = Path(folder)
    atomic_npz(folder/'predictions.npz', labels=result.labels, state_path=result.state_path,
        margin=result.margin, allowed_unknown=result.allowed_unknown, frame_ids=frames, period_ids=periods)
    _atomic_json(folder/'boundaries.json', {'profiles': result.boundaries, 'periods': result.periods,
        'interpretation': 'conditional single-boundary near-optimal envelopes; not statistical intervals'})
    _atomic_json(folder/'manifest.json', {'version': VERSION, 'shape': [len(frames)],
        'predictions_sha256': sha256_file(folder/'predictions.npz'),
        'boundaries_sha256': sha256_file(folder/'boundaries.json'), 'provenance': provenance,
        'margin': 'max-sum state-constrained objective gap; infinity for a uniquely forced state; not calibrated confidence'})


def load_sequence(folder):
    from src.hygiene.guards import guard_decoded_labels
    folder = Path(folder)
    manifest = json.loads((folder/'manifest.json').read_text())
    if (manifest.get('version') != VERSION or sha256_file(folder/'predictions.npz') != manifest['predictions_sha256']
            or sha256_file(folder/'boundaries.json') != manifest['boundaries_sha256']):
        raise ValueError('Sequential artifact signature mismatch')
    with np.load(folder/'predictions.npz', allow_pickle=False) as archive:
        if set(archive.files) != {'labels', 'state_path', 'margin', 'allowed_unknown', 'frame_ids', 'period_ids'}:
            raise ValueError('Unexpected sequential archive fields')
        a = {key: archive[key] for key in archive.files}
    n = len(a['frame_ids'])
    if (manifest['shape'] != [n] or any(value.shape != (n,) for value in a.values())
            or not np.issubdtype(a['frame_ids'].dtype, np.integer)
            or not np.issubdtype(a['period_ids'].dtype, np.integer) or (a['period_ids'] < 0).any()
            or not np.issubdtype(a['state_path'].dtype, np.integer)
            or (a['state_path'][a['period_ids'] <= 0] != -1).any()
            or not np.isin(a['state_path'][a['period_ids'] > 0], [0, 1, 2]).all()
            or np.isneginf(a['margin']).any() or (a['margin'][np.isfinite(a['margin'])] < 0).any()):
        raise ValueError('Invalid sequential archive timeline or margins')
    guard_decoded_labels(a['labels'], a['period_ids'], allowed_unknown=a['allowed_unknown'])
    return a, manifest


def score_sequence(pm, targets, prediction, inputs, short_s):
    gt, pred = pm.label_codes(targets.labels), pm.label_codes(prediction)
    boundaries = [end for _, end in period_intervals(inputs)[:-1]]
    gt, pred = np.insert(gt, boundaries, pm.X), np.insert(pred, boundaries, pm.X)
    result = pm.evaluate(gt, pred, bootstrap_n=0)
    valid_runs = pm.valid_runs(gt)
    filled = pm.fill_abstentions(pred, valid_runs)
    short = {}
    for name, states in (('possession', (pm.H, pm.A)), ('dead', (pm.D,))):
        actual = [(a, b, k) for a, b, k in pm.segments(gt, valid_runs) if k in states]
        proposed = [(a, b, k) for a, b, k in pm.segments(filled, valid_runs) if k in states]
        flags = pm.matched_gt_flags(pm.spell_overlaps(actual, proposed), len(actual), .5)
        is_short = np.array([b-a < short_s*inputs.fps for a, b, _ in actual], dtype=bool)
        count = int(is_short.sum())
        short[name] = {'duration_less_than_s': short_s, 'n_gt': count,
            'n_matched_iou05': int(flags[is_short].sum()),
            'recall_iou05': float(flags[is_short].mean()) if count else None}
    transitions = {str(tol): {key: value for key, value in row.items()
                    if key not in ('pairs', 'missed', 'spurious')} for tol, row in result['transitions'].items()}
    return {'spell_f1': result['spell_f1_mean'], 'macro_f1': result['macro_f1'],
        'spell_f1_by_iou': {str(key): row for key, row in result['spell_f1'].items()},
        'n_gt_spells': result['n_gt_spells'], 'n_pred_spells': result['n_pred_spells'],
        'n_gt_segments': result['n_gt_segments'], 'n_pred_segments': result['n_pred_segments'],
        'fragmentation': result['fragmentation'], 'per_class': result['per_class'],
        'transitions': transitions, 'short_segments': short, 'n_graded': result['n_graded'],
        'n_abstain_on_graded': result['n_abstain_on_graded']}


def validate(progress=print, *, match_id=None):
    protocol, opt = settings('external_protocol.json'), options()
    selected = protocol['splits']['validation'] if match_id is None else [match_id]
    if not set(selected) <= set(protocol['splits']['validation']):
        raise PermissionError('Only frozen validation matches can be compared')
    model, prior = load_model(), load_prior()
    code, stamp, prior_hash = code_provenance(), signatures(), sha256_file(ROOT/'prior.json')
    pm = load_official_metrics()
    report = {'version': VERSION, 'code': code, 'signatures': stamp, 'prior_sha256': prior_hash,
        'validation_matches': selected, 'training_matches': prior['training_matches'],
        'primary_decoder_predefined': opt['primary_decoder'], 'public_labels_read': False,
        'final_test_accessed': False, 'validation_used_for_fit': False, 'hyperparameter_searches': 0,
        'baseline_replaced': False, 'runs': []}
    for match in selected:
        if match_role(match) != 'validation':
            raise PermissionError('Validation split mismatch')
        inputs = load_inputs(match)
        pending, frozen = [], []
        for scenario in protocol['scenarios']:
            seeds = protocol['scenario_seeds'][:1] if scenario['kind'] == 'clean' else protocol['scenario_seeds']
            for seed in seeds:
                progress(f'Sequential predictions: {match}, {scenario["name"]}, seed {seed}')
                origin = OBS/'validation'/match/f'{scenario["name"]}_{seed}'
                scores, frames, periods, manifest = load_scores(origin/'logistic')
                if (not np.array_equal(frames, inputs.frame_ids) or not np.array_equal(periods, inputs.period_ids)
                        or manifest['provenance']['model_sha256'] != stamp['observation_model_sha256']
                        or manifest['provenance']['signatures'] != stamp['observation_signatures']):
                    raise ValueError('Frozen external score provenance mismatch')
                start = perf_counter()
                cues, quality = external_cues(match, scenario, seed, inputs, scores, frames, periods, manifest, opt, model)
                cue_seconds = perf_counter()-start
                folder = ROOT/'validation'/match/f'{scenario["name"]}_{seed}'
                entry = {'scenario': scenario['name'], 'seed': seed, 'quality': quality,
                         'cue_seconds': cue_seconds, 'decode_seconds': {}}
                for name in ('static', 'dynamic'):
                    start = perf_counter()
                    cost = transition_costs(prior, cues if name == 'dynamic' else None,
                                            reduction=opt['maximum_cost_reduction'])
                    result = decode(scores, frames, periods, cost, opt, fps=inputs.fps)
                    entry['decode_seconds'][name] = perf_counter()-start
                    save_sequence(result, frames, periods, folder/name, {'match_id': match, 'scenario': scenario,
                        'seed': seed, 'decoder': name, 'signatures': stamp, 'prior_sha256': prior_hash,
                        'frozen_scores_sha256': manifest['scores_sha256'], 'validation_targets_read_for_predictions': False,
                        'code': code})
                    reloaded, _ = load_sequence(folder/name)
                    if not np.array_equal(reloaded['labels'], result.labels):
                        raise RuntimeError('Sequential prediction roundtrip mismatch')
                pending.append((origin, folder, entry))
                frozen.append({'scenario': scenario['name'], 'seed': seed,
                    'raw_scores_sha256': manifest['scores_sha256'], 'baseline_sha256': sha256_file(origin/'baseline.npz'),
                    'decoded': {name: sha256_file(folder/name/'predictions.npz') for name in ('static', 'dynamic')}})
        _atomic_json(ROOT/'validation'/match/'frozen_inputs.json', {'code': code, 'signatures': stamp,
            'prior_sha256': prior_hash, 'predictions': frozen, 'target_archive_opened_after_snapshot': True})
        progress(f'{match}: all 19 decoded variants frozen; opening targets only for scoring')
        targets = load_targets(match, purpose='validation')
        if not np.array_equal(targets.frame_ids, inputs.frame_ids) or not np.array_equal(targets.period_ids, inputs.period_ids):
            raise ValueError('Sequential validation targets are misaligned')
        for origin, folder, entry in pending:
            raw, frames, periods, _ = load_scores(origin/'logistic')
            predictions = {'baseline': _baseline(origin/'baseline.npz', frames, periods), 'raw_logistic': raw.labels()}
            predictions.update({name: load_sequence(folder/name)[0]['labels'] for name in ('static', 'dynamic')})
            for name, prediction in predictions.items():
                metrics = score_sequence(pm, targets, prediction, inputs, opt['short_segment_diagnostic_s'])
                report['runs'].append({'match_id': match, 'candidate': name, **entry, **metrics})
        progress(f'{match}: baseline, raw scores, static and dynamic decoders compared in all 19 conditions')
    if code_provenance()['source_files_sha256'] != code['source_files_sha256'] or signatures() != stamp or sha256_file(ROOT/'prior.json') != prior_hash:
        raise RuntimeError('Code/model/decoder settings changed during validation')
    report['summary'] = []
    for match in selected:
        for name in opt['comparisons']:
            rows = [row for row in report['runs'] if row['match_id'] == match and row['candidate'] == name]
            report['summary'].append({'match_id': match, 'candidate': name, 'runs': len(rows),
                'mean_spell_f1': float(np.mean([row['spell_f1'] for row in rows])),
                'mean_macro_f1': float(np.mean([row['macro_f1'] for row in rows])),
                'mean_pred_segments': float(np.mean([row['n_pred_segments'] for row in rows]))})
    _atomic_json(ROOT/('validation.json' if match_id is None else f'validation-{match_id}.json'), report)
    return report


def merge_validation():
    matches = settings('external_protocol.json')['splits']['validation']
    reports = [json.loads((ROOT/f'validation-{match}.json').read_text()) for match in matches]
    code, stamp, prior_hash = code_provenance()['source_files_sha256'], signatures(), sha256_file(ROOT/'prior.json')
    protocol = settings('external_protocol.json')
    expected = {(scenario['name'], seed, candidate) for scenario in protocol['scenarios']
        for seed in (protocol['scenario_seeds'][:1] if scenario['kind'] == 'clean' else protocol['scenario_seeds'])
        for candidate in options()['comparisons']}
    for match, report in zip(matches, reports):
        keys = {(row['scenario'], row['seed'], row['candidate']) for row in report['runs']}
        if (report['validation_matches'] != [match] or report['signatures'] != stamp
                or report['prior_sha256'] != prior_hash or report['code']['source_files_sha256'] != code
                or keys != expected or len(keys) != len(report['runs'])
                or any(row['match_id'] != match for row in report['runs'])):
            raise ValueError('Sequential validation reports have inconsistent provenance/coverage')
    merged = {**reports[0], 'validation_matches': matches, 'runs': [row for r in reports for row in r['runs']],
              'summary': [row for r in reports for row in r['summary']]}
    _atomic_json(ROOT/'validation.json', merged)
    return merged


def tactical(progress=print):
    opt, prior, stamp, code = options(), load_prior(), signatures(), code_provenance()
    scores, frames, periods, score_manifest = load_scores(OBS/'tactical/logistic')
    if (not np.array_equal(frames, np.arange(config.TOTAL_FRAMES))
            or score_manifest['provenance']['model_sha256'] != stamp['observation_model_sha256']
            or score_manifest['provenance']['signatures'] != stamp['observation_signatures']):
        raise ValueError('Tactical frozen observations do not match the model/timeline')
    a, feature_manifest, schema = load_matrix(config.CACHE_DIR/'features/tactical')
    if (not np.array_equal(a['frame_ids'], frames) or not np.array_equal(a['period_ids'], periods)
            or feature_manifest['diagnostics']['settings'] != settings('features.json')['settings']):
        raise ValueError('Tactical feature and score archives disagree')
    matrix = FeatureMatrix(a['values'], a['valid'], tuple(a['names'].tolist()), schema['features'],
                           frames, periods, feature_manifest['diagnostics'])
    matrix.diagnostics['fps'] = config.FPS
    cues = boundary_cues(matrix, scores, opt)
    allowed = np.ones((len(frames), 3), dtype=bool)
    start, end = config.DEAD_ZONE_2HT_INTERVAL
    allowed[start:end, :2] = False  # Published FAQ constraint, never a fitted label.
    baseline_hash = settings('baseline_reference.json')['competition_csv_sha256']
    if sha256_file(config.SUBMISSIONS_DIR/'MYA.csv') != baseline_hash:
        raise ValueError('Frozen baseline submission changed')
    for name in ('static', 'dynamic'):
        cost = transition_costs(prior, cues if name == 'dynamic' else None, reduction=opt['maximum_cost_reduction'])
        result = decode(scores, frames, periods, cost, opt, allowed_states=allowed, fps=config.FPS)
        masked = apply_official_masks(result.labels)
        if not np.array_equal(masked, result.labels):
            raise RuntimeError('Contractual constraints were not enforced inside decoding')
        save_sequence(result, frames, periods, ROOT/'tactical'/name, {'source': 'tactical', 'decoder': name,
            'code': code, 'signatures': stamp, 'prior_sha256': sha256_file(ROOT/'prior.json'),
            'frozen_scores_sha256': score_manifest['scores_sha256'], 'public_labels_read': False,
            'published_dead_zone_constraint': list(config.DEAD_ZONE_2HT_INTERVAL), 'baseline_unchanged': True})
        loaded, _ = load_sequence(ROOT/'tactical'/name)
        if not np.array_equal(loaded['labels'], result.labels):
            raise RuntimeError('Tactical sequential archive roundtrip mismatch')
        if name == opt['primary_decoder']:
            artifact = export_submission(config.SUBMISSIONS_DIR/'MYA_jalon5.csv', result.labels)
            _atomic_json(ROOT/'tactical/export.json', {**artifact, 'decoder': name, 'signatures': stamp,
                'baseline_replaced': False, 'public_labels_read': False})
        progress(f'Tactical {name}: full period-local labels, margins and boundary envelopes verified')
    if sha256_file(config.SUBMISSIONS_DIR/'MYA.csv') != baseline_hash or code_provenance()['source_files_sha256'] != code['source_files_sha256']:
        raise RuntimeError('Baseline or code changed during sequential inference')
    return artifact


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for action in ('fit', 'validate', 'merge-validation', 'tactical', 'all'):
        parser.add_argument(f'--{action}', action='store_true')
    parser.add_argument('--validation-match')
    args = parser.parse_args(argv)
    if not any(getattr(args, key) for key in ('fit', 'validate', 'merge_validation', 'tactical', 'all')):
        parser.error('Choose --all or explicit stages')
    try:
        progress = lambda value: print(value, flush=True)
        if args.fit or args.all: fit_prior(progress)
        if args.validate or args.all:
            report = validate(progress, match_id=args.validation_match)
            for row in report['summary']:
                print(f"{row['match_id']} {row['candidate']}: spellF1={row['mean_spell_f1']:.4f}, macroF1={row['mean_macro_f1']:.4f}, segments={row['mean_pred_segments']:.1f}", flush=True)
        if args.merge_validation:
            report = merge_validation()
            print(f"Merged {len(report['runs'])} frozen sequential comparisons")
        if args.tactical or args.all:
            artifact = tactical(progress)
            print(f"Separate candidate CSV validated: {artifact['rows']} frames; MYA_jalon5.csv")
    except Exception as error:
        ROOT.mkdir(parents=True, exist_ok=True)
        (ROOT/'error.log').write_text(traceback.format_exc(), encoding='utf-8')
        print(f'Sequential stage failed ({type(error).__name__}); inspect .cache/sequential/error.log locally', file=sys.stderr)
        return 1
    print('Baseline unchanged; no public labels read; final test untouched')
    return 0


if __name__ == '__main__': sys.exit(main())
