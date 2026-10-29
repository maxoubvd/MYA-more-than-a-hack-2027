"""Milestone 6: bounded match-disjoint search, confirmation and frozen export."""
from __future__ import annotations
import argparse
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from time import perf_counter
import traceback
import numpy as np

from src import config
from src.build_features import load_matrix, save_matrix
from src.external_benchmark import degrade
from src.features.activity import fit_context_model
from src.features.builder import FeatureMatrix, build_features
from src.features.team_assignment import from_external
from src.models.dataset import training_examples
from src.models.tabular import fit_factorized
from src.models.observations import factor_scores
from src.observation_pipeline import (context_model, load_model, load_scores, save_scores,
                                      options as observation_options)
from src.pipeline import _atomic_json, code_provenance
from src.refinement.exporter import export_submission, sha256_file
from src.sequential.decoder import decode
from src.sequential.dynamic_matrix import fit_transition_prior, base_costs
from src.sequential_pipeline import (load_prior, load_sequence, save_sequence, score_sequence,
                                     options as sequential_options)
from src.experiments.batch import decode_batch
from src.experiments.design import (FAMILIES, family_examples, family_scores, scaled_costs,
                                     choose_family, choose_temporal, adoption)
from src.hygiene.masking import apply_official_masks
from src.utils.external_data import (settings, load_inputs, load_targets, match_role,
                                     dataset_root, atomic_npz)
from src.utils.official import check_official_revision, load_official_metrics

VERSION = 'selection-v1'
ROOT = config.CACHE_DIR/'experiments'
OBS = config.CACHE_DIR/'observations'
SEQ = config.CACHE_DIR/'sequential'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def options():
    opt = settings('experiments.json')
    protocol = settings('external_protocol.json')
    if (opt['version'] != VERSION or opt['families'] != list(FAMILIES)
            or opt['maximum_family_fits'] != 16 or opt['maximum_temporal_settings'] != 9
            or opt['internal_prediction_comparisons'] != 156
            or opt['internal_scenarios'] != ['clean', 'long_gaps', 'combined']
            or opt['transition_scales'] != [.5, 1., 2.] or opt['extra_searches'] != 0
            or opt['minimum_duration_frames'] is not None
            or opt['internal_seed'] != protocol['scenario_seeds'][0]):
        raise ValueError('Experiment is outside its registered search budget')
    return opt


def signature():
    return {'configuration': {name: sha256_file(config.MYA_DIR/'configs'/name) for name in (
                'experiments.json', 'external_protocol.json', 'features.json', 'observation_model.json', 'sequential.json')},
            'sources': code_provenance()['source_files_sha256'],
            'j4_model_sha256': sha256_file(OBS/'model.json'),
            'j5_prior_sha256': sha256_file(SEQ/'prior.json'),
            'context_sha256': sha256_file(config.CACHE_DIR/'features/context_model.json'),
            'official_revision': (config.MYA_DIR/'official-revision.txt').read_text().strip()}


def register():
    check_official_revision()
    opt = options()
    stamp = signature()
    path = ROOT/'registration.json'
    if path.exists():
        entry = read(path)
        if entry['signature'] != stamp or entry['options'] != opt:
            raise ValueError('Registered experiment changed; preserve old results before starting a new version')
        return entry
    splits = settings('external_protocol.json')['splits']
    entry = {'version': VERSION, 'registered_utc': datetime.now(timezone.utc).isoformat(),
             'experiment_id': digest(stamp), 'options': opt, 'signature': stamp,
             'git': code_provenance(), 'sources': [], 'public_labels_read': False,
             'test_accessed': False, 'validation_previously_inspected': True}
    for match in splits['train']+splits['validation']:
        folder = dataset_root()/'prepared'/match
        entry['sources'].append({'match_id': match, 'role': match_role(match),
            'inputs_sha256': sha256_file(folder/'inputs.npz'), 'targets_sha256': sha256_file(folder/'targets.npz')})
    _atomic_json(path, entry)
    return entry


def ensure_registration():
    entry = register()
    # Hash bytes for integrity; do not deserialize labels for this check.
    for source in entry['sources']:
        folder = dataset_root()/'prepared'/source['match_id']
        for kind in ('inputs', 'targets'):
            if sha256_file(folder/f'{kind}.npz') != source[f'{kind}_sha256']:
                raise ValueError('Registered external data bytes changed')
    return entry


def record(stage, data):
    entry = ensure_registration()
    value = {'experiment_id': entry['experiment_id'], 'stage': stage,
             'completed_utc': datetime.now(timezone.utc).isoformat(), **data}
    _atomic_json(ROOT/f'{stage}.json', value)
    return value


def artifact(stage):
    entry = ensure_registration()
    value = read(ROOT/f'{stage}.json')
    if value.get('experiment_id') != entry['experiment_id']:
        raise ValueError('Experiment artifact belongs to another registration')
    return value


def scenarios(internal=False):
    protocol = settings('external_protocol.json')
    for scenario in protocol['scenarios']:
        if internal and scenario['name'] not in options()['internal_scenarios']:
            continue
        seeds = [options()['internal_seed']] if internal else (
            protocol['scenario_seeds'][:1] if scenario['kind'] == 'clean' else protocol['scenario_seeds'])
        for seed in seeds:
            yield scenario, seed


def raw_matrix(match, scenario, seed, progress=print):
    """Label-free reusable features; fold-specific context is applied AFTER loading."""
    if match_role(match) not in ('train', 'validation'):
        raise PermissionError('The final test is locked')
    folder = ROOT/'features'/match/f'{scenario["name"]}_{seed}'
    entry = ensure_registration()
    stamp = {'experiment_id': entry['experiment_id'], 'match': match, 'scenario': scenario, 'seed': seed,
             'inputs_sha256': next(s['inputs_sha256'] for s in entry['sources'] if s['match_id'] == match)}
    if (folder/'manifest.json').exists():
        a, manifest, schema = load_matrix(folder)
        if manifest['provenance'] != stamp:
            raise ValueError('Feature cache provenance differs')
        matrix = FeatureMatrix(a['values'], a['valid'], tuple(a['names'].tolist()), schema['features'],
                               a['frame_ids'], a['period_ids'], manifest['diagnostics'])
        return matrix
    start = perf_counter()
    inputs = load_inputs(match)
    observations, quality = degrade(inputs, scenario, seed)
    progress(f'Observation features: {match} {scenario["name"]} seed {seed}')
    matrix = build_features(from_external(observations), settings=settings('features.json')['settings'])
    matrix.diagnostics.update(fps=inputs.fps, degradation=quality, extraction_seconds=perf_counter()-start)
    save_matrix(matrix, folder, stamp)
    return matrix


def prepare(progress=print):
    entry = ensure_registration()
    for match in settings('external_protocol.json')['splits']['train']:
        for scenario, seed in scenarios(True):
            matrix = raw_matrix(match, scenario, seed, progress)
            progress(f'{match} {scenario["name"]}: validated {len(matrix.frame_ids)} observation rows')
            del matrix
    return entry


def fold_training(held_out):
    train = settings('external_protocol.json')['splits']['train']
    if held_out not in train:
        raise PermissionError('Internal holdout must be a registered training match')
    return [match for match in train if match != held_out]


def fit_context(training, progress):
    match = training[0]
    clean = next(s for s, _ in scenarios(True) if s['name'] == 'clean')
    matrix = raw_matrix(match, clean, options()['internal_seed'], progress)
    return fit_context_model(matrix.column('collective_median_speed_mps'),
        matrix.column('ball_acceleration_mps2'), match_id=match,
        contact_quantile=settings('features.json')['settings']['contact_quantile'])


def batches_for(training, context, progress):
    batches, targets = [], {}
    opt = observation_options()
    for match in training:
        if match_role(match) != 'train':
            raise PermissionError('Only registered training matches may fit heads')
        targets[match] = load_targets(match, purpose='training')
        for scenario, seed in scenarios(True):
            matrix = raw_matrix(match, scenario, seed, progress).apply_context_model(context)
            batches.append(training_examples(match, scenario['name'], matrix, targets[match],
                maximum_rows=opt['maximum_rows_per_match_scenario']))
    return batches, targets


def summary_of(rows):
    summary = []
    for match in sorted({r['match_id'] for r in rows}):
        for name in sorted({r['candidate'] for r in rows if r['match_id'] == match}):
            group = [r for r in rows if r['match_id'] == match and r['candidate'] == name]
            summary.append({'match_id': match, 'candidate': name, 'runs': len(group),
                'mean_spell_f1': float(np.mean([r['spell_f1'] for r in group])),
                'mean_macro_f1': float(np.mean([r['macro_f1'] for r in group])),
                'mean_short_recall': float(np.mean([r['short_segments']['possession']['recall_iou05'] for r in group])),
                'mean_pred_segments': float(np.mean([r['n_pred_segments'] for r in group]))})
    return summary


def internal(progress=print):
    ensure_registration()
    opt, pm = options(), load_official_metrics()
    started = perf_counter()
    family_rows, folds = [], []
    train = settings('external_protocol.json')['splits']['train']
    for held_out in train:
        progress(f'Internal fold: hold out complete match {held_out}')
        training = fold_training(held_out)
        context = fit_context(training, progress)
        batches, training_targets = batches_for(training, context, progress)
        prior = fit_transition_prior(training_targets)
        models = {}
        fit_start = perf_counter()
        for family in FAMILIES:
            progress(f'{held_out}: refit {family} on three other matches')
            model = fit_factorized(family_examples(batches, family), observation_options())
            model.update(feature_family=family, context=context)
            if held_out in model['training_matches'] or context['training_match'] == held_out:
                raise RuntimeError('Held-out match leaked into fitted model/context')
            models[family] = model
        folder = ROOT/'internal'/held_out
        _atomic_json(folder/'models.json', {'training_matches': training, 'held_out': held_out,
                                           'context': context, 'prior': prior, 'models': models})
        folds.append({'held_out': held_out, 'training_matches': training,
            'context_training_match': context['training_match'], 'fit_seconds': perf_counter()-fit_start,
            'models_sha256': sha256_file(folder/'models.json')})
        del batches, training_targets
        frozen = []
        for scenario, seed in scenarios(True):
            matrix = raw_matrix(held_out, scenario, seed, progress).apply_context_model(context)
            scores = [family_scores(matrix, models[family]) for family in FAMILIES]
            start = perf_counter()
            prediction = decode_batch(scores, matrix.frame_ids, matrix.period_ids, [base_costs(prior)]*4)
            seconds = perf_counter()-start
            destination = folder/scenario['name']
            for family, score in zip(FAMILIES, scores):
                save_scores(score, matrix, destination/family, {'held_out': held_out,
                    'training_matches': training, 'family': family, 'context_training_match': context['training_match']})
            atomic_npz(destination/'families.npz', labels=prediction, frame_ids=matrix.frame_ids, period_ids=matrix.period_ids)
            frozen.append({'scenario': scenario['name'], 'sha256': sha256_file(destination/'families.npz'),
                'score_sha256': {family: sha256_file(destination/family/'scores.npz') for family in FAMILIES},
                'batch_decode_seconds': seconds})
        _atomic_json(folder/'family_snapshot.json', {'predictions_frozen_before_scoring': frozen})
        progress(f'{held_out}: all family predictions frozen; score internal held-out targets')
        target, inputs = load_targets(held_out, purpose='training'), load_inputs(held_out)
        for snapshot in frozen:
            scenario = snapshot['scenario']
            with np.load(folder/scenario/'families.npz', allow_pickle=False) as archive:
                predictions = archive['labels']
                if not np.array_equal(archive['frame_ids'], target.frame_ids) or not np.array_equal(archive['period_ids'], target.period_ids):
                    raise ValueError('Held-out family timeline mismatch')
            for family, pred in zip(FAMILIES, predictions):
                metrics = score_sequence(pm, target, pred, inputs, 2.)
                family_rows.append({'match_id': held_out, 'scenario': scenario, 'candidate': family,
                    'columns': sum(len(h['feature_names']) for h in models[family]['heads'].values()), **metrics})
    family, family_summary = choose_family(family_rows, opt['family_tolerance_spell_f1'])
    record('family_selection', {'selected_family': family, 'summary': family_summary, 'runs': family_rows, 'folds': folds})
    progress(f'Internal feature family frozen: {family}; now run the nine registered temporal settings')
    grid, temporal_rows = [(a,b) for a in opt['transition_scales'] for b in opt['transition_scales']], []
    for held_out in train:
        folder = ROOT/'internal'/held_out
        prior = read(folder/'models.json')['prior']
        costs = [scaled_costs(prior, a, b) for a,b in grid]
        frozen = []
        for scenario, _ in scenarios(True):
            scores, frames, periods, manifest = load_scores(folder/scenario['name']/family)
            start = perf_counter()
            labels = decode_batch([scores]*len(grid), frames, periods, costs)
            path = folder/scenario['name']/'temporal.npz'
            atomic_npz(path, labels=labels, frame_ids=frames, period_ids=periods)
            frozen.append({'scenario': scenario['name'], 'sha256': sha256_file(path),
                           'scores_sha256': manifest['scores_sha256'], 'batch_decode_seconds': perf_counter()-start})
        _atomic_json(folder/'temporal_snapshot.json', {'family': family, 'grid': grid, 'predictions_frozen_before_scoring': frozen})
        target, inputs = load_targets(held_out, purpose='training'), load_inputs(held_out)
        for row in frozen:
            with np.load(folder/row['scenario']/'temporal.npz', allow_pickle=False) as archive:
                labels = archive['labels']
            for (a,b), pred in zip(grid, labels):
                temporal_rows.append({'match_id': held_out, 'scenario': row['scenario'],
                    'team_scale': a, 'dead_scale': b, **score_sequence(pm, target, pred, inputs, 2.)})
        progress(f'{held_out}: nine temporal settings evaluated on three complete-match conditions')
    temporal, temporal_summary = choose_temporal(temporal_rows, opt['transition_scales'], opt['plateau_tolerance_spell_f1'])
    result = record('internal', {'selected_family': family, 'family_summary': family_summary,
        'temporal_choice': temporal, 'temporal_summary': temporal_summary, 'temporal_runs': temporal_rows,
        'family_comparisons': len(family_rows), 'temporal_comparisons': len(temporal_rows),
        'total_seconds': perf_counter()-started, 'folds': folds,
        'public_labels_read': False, 'validation_labels_read': False})
    freeze_bundle(progress)
    return result


def freeze_bundle(progress=print):
    internal_result = artifact('internal')
    family = internal_result['selected_family']
    context = context_model()
    if family == 'full':
        # Exact pre-existing all-four-match fit, not an internal validation model.
        model = {**load_model(), 'feature_family': 'full'}
        refit_seconds = 0.
    else:
        progress(f'Final external training: refit {family} on all four training matches')
        start = perf_counter()
        batches, _ = batches_for(settings('external_protocol.json')['splits']['train'], context, progress)
        model = fit_factorized(family_examples(batches, family), observation_options())
        model['feature_family'] = family
        refit_seconds = perf_counter()-start
    return record('bundle', {'model': model, 'context': context, 'prior': load_prior(),
        'family': family, 'team_scale': internal_result['temporal_choice']['team_scale'],
        'dead_scale': internal_result['temporal_choice']['dead_scale'], 'refit_seconds': refit_seconds,
        'shortlist_frozen_before_confirmation': options()['validation_shortlist'],
        'adoption_gate': options()['adoption_gate'], 'validation_used_for_fit': False})


def intervention(scores, name, rules=None):
    home, dead = scores.p_home_given_alive.copy(), scores.p_dead.copy()
    source, support = scores.team_source.copy(), scores.team_support.copy()
    state_support = scores.state_support
    if name == 'no_collective':
        missing = source == 2
        home[missing], source[missing], support[missing] = .5, 0, 0
    elif name == 'physical_state' and rules is not None:
        dead, state_support = rules.p_dead, rules.state_support
    else:
        raise ValueError('Unknown registered score intervention')
    return factor_scores(dead, home, scores.active, state_support=state_support,
                         team_support=support, team_source=source)


def validate(progress=print):
    bundle = artifact('bundle')
    opt, pm, started = options(), load_official_metrics(), perf_counter()
    matches = settings('external_protocol.json')['splits']['validation']
    names = opt['validation_shortlist']
    rows, snapshots = [], []
    for match in matches:
        inputs = load_inputs(match)
        pending = []
        for scenario, seed in scenarios():
            progress(f'Confirmation predictions: {match} {scenario["name"]} seed {seed}')
            origin = OBS/'validation'/match/f'{scenario["name"]}_{seed}'
            full, frames, periods, manifest = load_scores(origin/'logistic')
            if (manifest['provenance']['model_sha256'] != signature()['j4_model_sha256']
                    or not np.array_equal(frames, inputs.frame_ids) or not np.array_equal(periods, inputs.period_ids)):
                raise ValueError('Frozen comparison model/timeline differs')
            rules, rf, rp, _ = load_scores(origin/'rules')
            hold, hf, hp, _ = load_scores(origin/'rules_hold')
            if not all(np.array_equal(a,b) for a,b in ((rf,frames),(rp,periods),(hf,frames),(hp,periods))):
                raise ValueError('Rule comparison timelines differ')
            if bundle['family'] == 'full':
                selected = full
            else:
                matrix = raw_matrix(match, scenario, seed, progress).apply_context_model(bundle['context'])
                selected = family_scores(matrix, bundle['model'])
            altered = [selected, intervention(selected, 'no_collective'), intervention(selected, 'physical_state', rules)]
            start = perf_counter()
            predictions = decode_batch(altered, frames, periods,
                [scaled_costs(bundle['prior'], bundle['team_scale'], bundle['dead_scale'])]*3)
            decode_seconds = perf_counter()-start
            with np.load(origin/'baseline.npz', allow_pickle=False) as archive:
                if not np.array_equal(archive['frame_ids'], frames) or not np.array_equal(archive['period_ids'], periods):
                    raise ValueError('Baseline confirmation timeline differs')
                baseline = archive['labels']
            prior_comparisons = {}
            prior_hash = signature()['j5_prior_sha256']
            for name in ('static','dynamic'):
                a, meta = load_sequence(SEQ/'validation'/match/f'{scenario["name"]}_{seed}'/name)
                if (meta['provenance']['prior_sha256'] != prior_hash
                        or meta['provenance']['frozen_scores_sha256'] != manifest['scores_sha256']
                        or not np.array_equal(a['frame_ids'], frames) or not np.array_equal(a['period_ids'], periods)):
                    raise ValueError('J5 comparison provenance differs')
                prior_comparisons[f'j5_{name}'] = a['labels']
            mapping = {'baseline': baseline, 'rules': rules.labels(), 'rules_hold': hold.labels(),
                'raw_selected': selected.labels(), 'selected': predictions[0],
                'no_collective': predictions[1], 'physical_state': predictions[2], **prior_comparisons}
            folder = ROOT/'validation'/match/f'{scenario["name"]}_{seed}'
            path = folder/'predictions.npz'
            atomic_npz(path, labels=np.stack([mapping[name] for name in names]), names=np.array(names),
                       frame_ids=frames, period_ids=periods)
            snapshot = {'match_id': match, 'scenario': scenario['name'], 'seed': seed,
                        'sha256': sha256_file(path), 'decode_seconds_three_variants': decode_seconds,
                        'raw_scores_sha256': manifest['scores_sha256']}
            pending.append((path,snapshot))
        _atomic_json(ROOT/'validation'/match/'snapshot.json', {'bundle_sha256': sha256_file(ROOT/'bundle.json'),
            'predictions_frozen_before_target_read': [r for _,r in pending], 'shortlist': names})
        progress(f'{match}: 19 conditions and nine methods frozen; open confirmation targets for scoring')
        targets = load_targets(match, purpose='validation')
        for path, snapshot in pending:
            if sha256_file(path) != snapshot['sha256']:
                raise ValueError('Predictions changed after freeze')
            with np.load(path, allow_pickle=False) as archive:
                if (not np.array_equal(archive['frame_ids'], targets.frame_ids)
                        or not np.array_equal(archive['period_ids'], targets.period_ids)):
                    raise ValueError('Confirmation target alignment differs')
                labels = archive['labels']
            for name, pred in zip(names, labels):
                rows.append({**snapshot, 'candidate': name, **score_sequence(pm, targets, pred, inputs, 2.)})
        snapshots.extend([r for _,r in pending])
    summary = summary_of(rows)
    decision = adoption(summary, opt['adoption_gate'])
    return record('validation', {'runs': rows, 'summary': summary, 'decision': decision,
        'snapshots': snapshots, 'bundle_sha256': sha256_file(ROOT/'bundle.json'),
        'total_seconds': perf_counter()-started, 'public_labels_read': False, 'test_accessed': False,
        'validation_previously_inspected': True, 'no_new_search_after_confirmation': True})


def tactical(progress=print):
    bundle, confirmation = artifact('bundle'), artifact('validation')
    if confirmation['bundle_sha256'] != sha256_file(ROOT/'bundle.json'):
        raise ValueError('Candidate changed after confirmation')
    chosen = confirmation['decision']['candidate']
    before = sha256_file(config.SUBMISSIONS_DIR/'MYA.csv')
    if before != settings('baseline_reference.json')['competition_csv_sha256']:
        raise ValueError('Baseline changed')
    if chosen == 'selected':
        if bundle['family'] == 'full':
            scores, frames, periods, _ = load_scores(OBS/'tactical/logistic')
        else:
            a, manifest, schema = load_matrix(config.CACHE_DIR/'features/tactical')
            matrix = FeatureMatrix(a['values'], a['valid'], tuple(a['names'].tolist()), schema['features'],
                                   a['frame_ids'], a['period_ids'], manifest['diagnostics'])
            scores = family_scores(matrix, bundle['model'])
            frames, periods = matrix.frame_ids, matrix.period_ids
        cost = scaled_costs(bundle['prior'], bundle['team_scale'], bundle['dead_scale'])
    elif chosen == 'j5_static':
        scores, frames, periods, _ = load_scores(OBS/'tactical/logistic')
        cost = base_costs(bundle['prior'])
    else:
        raise ValueError('Candidate is outside frozen decision rule')
    if not np.array_equal(frames, np.arange(config.TOTAL_FRAMES)):
        raise ValueError('Incomplete tactical timeline')
    allowed = np.ones((len(frames),3), dtype=bool)
    start, end = config.DEAD_ZONE_2HT_INTERVAL
    allowed[start:end,:2] = False
    begin = perf_counter()
    result = decode(scores, frames, periods, cost, sequential_options(), allowed_states=allowed, fps=config.FPS)
    if not np.array_equal(apply_official_masks(result.labels), result.labels):
        raise RuntimeError('Official constraints were not enforced inside decoding')
    save_sequence(result, frames, periods, ROOT/'tactical', {'candidate': chosen,
        'bundle_sha256': sha256_file(ROOT/'bundle.json'), 'validation_sha256': sha256_file(ROOT/'validation.json'),
        'public_labels_read': False, 'baseline_unchanged': True})
    loaded, _ = load_sequence(ROOT/'tactical')
    if not np.array_equal(loaded['labels'], result.labels):
        raise RuntimeError('Candidate sequence roundtrip mismatch')
    exported = export_submission(config.SUBMISSIONS_DIR/'MYA_jalon6.csv', result.labels)
    if sha256_file(config.SUBMISSIONS_DIR/'MYA.csv') != before:
        raise RuntimeError('Baseline bytes changed')
    anchors = {'published_dead_zone_all_D': bool((result.labels[start:end] == 'D').all()),
        'outside_periods_all_X': bool((result.labels[periods <= 0] == 'X').all()),
        'unexpected_X_inside': int(((periods > 0)&(result.labels == 'X')&~result.allowed_unknown).sum()),
        'kickoff_labels_are_diagnostic_only': [str(result.labels[a]) for a,b in config.EVALUATED_INTERVALS]}
    frozen = record('candidate', {'decision': confirmation['decision'], 'family': bundle['family'] if chosen == 'selected' else 'full',
        'team_scale': bundle['team_scale'] if chosen == 'selected' else 1.,
        'dead_scale': bundle['dead_scale'] if chosen == 'selected' else 1., 'decoder': 'static',
        'export': exported, 'anchors': anchors, 'decode_seconds': perf_counter()-begin,
        'bundle_sha256': sha256_file(ROOT/'bundle.json'), 'validation_sha256': sha256_file(ROOT/'validation.json'),
        'baseline_sha256': before, 'public_labels_read': False, 'test_accessed': False})
    progress(f'Frozen candidate: {chosen}; separate MYA_jalon6.csv exported and validated')
    return frozen


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    for action in ('prepare','internal','validate','tactical','all'):
        parser.add_argument(f'--{action}', action='store_true')
    args = parser.parse_args(argv)
    if not any(vars(args).values()):
        parser.error('Choose --all or explicit stages')
    try:
        progress = lambda value: print(value, flush=True)
        if args.prepare or args.all: prepare(progress)
        if args.internal or args.all: internal(progress)
        if args.validate or args.all:
            report = validate(progress)
            for row in report['summary']:
                print(f"{row['match_id']} {row['candidate']}: spellF1={row['mean_spell_f1']:.4f}, macroF1={row['mean_macro_f1']:.4f}", flush=True)
        if args.tactical or args.all: tactical(progress)
    except Exception as error:
        ROOT.mkdir(parents=True, exist_ok=True)
        (ROOT/'error.log').write_text(traceback.format_exc(), encoding='utf-8')
        print(f'Experiments failed ({type(error).__name__}); inspect .cache/experiments/error.log locally', file=sys.stderr)
        return 1
    print('Milestone 6: public labels unread; final test locked; baseline unchanged')
    return 0


if __name__ == '__main__':
    sys.exit(main())
