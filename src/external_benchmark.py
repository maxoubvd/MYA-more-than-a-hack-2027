"""Frozen pre-J3 smoke benchmark. Scores a TRAIN match, never the locked test.

Observation degradation never receives labels. Predictions are frozen before
opening the target archive. Every scenario is reported; no best variant is chosen.
"""
from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys
import traceback

import numpy as np

from src import config
from src.baseline import majority_vote, nearest_team_labels
from src.pipeline import _atomic_json, code_provenance
from src.refinement.exporter import sha256_file
from src.utils.external_data import (ExternalInputs, INPUT_KEYS, dataset_root, load_inputs,
                                     load_targets, match_role, prepare_match, settings)
from src.utils.official import load_official_metrics


def period_intervals(inputs):
    ids = np.asarray(inputs.period_ids)
    if ids.ndim != 1 or not len(ids) or len(ids) != len(inputs.frame_ids):
        raise ValueError("Invalid external timeline")
    edges = np.r_[0, np.flatnonzero(ids[1:] != ids[:-1]) + 1, len(ids)]
    if len(set(ids[edges[:-1]].tolist())) != len(edges)-1:
        raise ValueError("A period may not reappear later")
    for start, end in zip(edges[:-1], edges[1:]):
        if (np.diff(inputs.frame_ids[start:end]) != 1).any():
            raise ValueError("External frames must be contiguous inside each period")
    return tuple(zip(edges[:-1].tolist(), edges[1:].tolist()))


def predict_external(inputs, *, half_width=50, missing_label="D"):
    if not isinstance(inputs, ExternalInputs) or set(inputs.feature_dict()) != INPUT_KEYS:
        raise TypeError("Prediction accepts only the observation allowlist, never targets or a mixed dictionary")
    n, slots = inputs.players_xy_normalized.shape[:2]
    players = np.full((n, slots, 3), np.nan, dtype=np.float32)
    ball = np.full((n, 3), np.nan, dtype=np.float32)
    players[..., :2], ball[..., :2] = inputs.players_xy_normalized, inputs.ball_xy_normalized
    raw = nearest_team_labels(players, ball, dict(enumerate(inputs.team_mapping.tolist())),
                              missing_label=missing_label, pitch_dims=inputs.pitch_dims)
    labels = np.full(n, "X", dtype="<U1")
    for start, end in period_intervals(inputs):
        labels[start:end] = majority_vote(raw[start:end], half_width, missing_label=missing_label)
    return labels


def gap_mask(inputs, scenario, rng, *, crowded=False):
    mask = np.zeros(len(inputs.frame_ids), dtype=bool)
    fraction = scenario["missing_fraction"]
    low, high = scenario["gap_frames"]
    if not 0 <= fraction < 1 or not 1 <= low <= high:
        raise ValueError("Invalid frozen gap scenario")
    for start, end in period_intervals(inputs):
        size, target = end-start, int(round((end-start)*fraction))
        local = mask[start:end]
        weights = None
        if crowded:
            delta = (inputs.players_xy_normalized[start:end] - inputs.ball_xy_normalized[start:end, None, :]) * np.asarray(inputs.pitch_dims)
            neighbours = (np.linalg.norm(delta, axis=-1) <= scenario["neighbour_radius_metres"]).sum(axis=1)
            weights = (1. + neighbours.astype(float))
            weights /= weights.sum()
        attempts = 0
        while int(local.sum()) < target:
            origin = int(rng.choice(size, p=weights))
            length = int(rng.integers(low, high+1))
            candidates = np.flatnonzero(~local[origin:min(size, origin+length)]) + origin
            remaining = target-int(local.sum())
            local[candidates[:remaining]] = True
            attempts += 1
            if attempts > size*10:
                raise RuntimeError("Could not construct the frozen gap mask")
    return mask


def degrade(inputs, scenario, seed):
    """Copy observations only; labels cannot influence a simulated sensor failure."""
    if not isinstance(inputs, ExternalInputs):
        raise TypeError("Degradation accepts observations only")
    rng = np.random.default_rng(seed)
    players, ball = inputs.players_xy_normalized.copy(), inputs.ball_xy_normalized.copy()
    kind = scenario["kind"]
    if kind in ("ball_gaps", "crowded_gaps", "combined"):
        ball[gap_mask(inputs, scenario, rng, crowded=kind=="crowded_gaps")] = np.nan
    if kind in ("spatial_noise", "combined"):
        sigma = scenario["sigma_metres"] / np.asarray(inputs.pitch_dims)
        players += rng.normal(size=players.shape).astype(np.float32) * sigma
        ball += rng.normal(size=ball.shape).astype(np.float32) * sigma
    if kind in ("fragmentation", "combined"):
        width = scenario["segment_frames"]
        if type(width) is not int or width < 1 or not 0 <= scenario["dropout_fraction"] < 1:
            raise ValueError("Invalid frozen fragmentation scenario")
        # Within-team track reassignment models identity switches without leaking
        # stable identities. Contiguous dropout also interrupts individual tracks.
        for start, end in period_intervals(inputs):
            for left in range(start, end, width):
                right = min(end, left+width)
                for team in ("H", "A"):
                    slots = np.flatnonzero(inputs.team_mapping == team)
                    players[left:right, slots] = players[left:right, rng.permutation(slots)]
                dropout = rng.random(players.shape[1]) < scenario["dropout_fraction"]
                players[left:right, dropout] = np.nan
    if kind not in ("clean", "ball_gaps", "crowded_gaps", "spatial_noise", "fragmentation", "combined"):
        raise ValueError("Unknown frozen scenario")
    result = replace(inputs, players_xy_normalized=players, ball_xy_normalized=ball,
                     players_observed=np.isfinite(players).all(axis=-1), ball_observed=np.isfinite(ball).all(axis=-1))
    return result, {"ball_missing_fraction": float((~result.ball_observed).mean()),
                    "player_missing_fraction": float((~result.players_observed).mean())}


def smoke_benchmark(match_id=None):
    protocol = settings("external_protocol.json")
    match_id = match_id or protocol["smoke_match"]
    if match_role(match_id) != "train":
        raise PermissionError("Pre-J3 smoke benchmark is restricted to training matches")
    inputs = load_inputs(match_id)
    metrics = load_official_metrics()
    folder = dataset_root() / "benchmark" / match_id
    folder.mkdir(parents=True, exist_ok=True)
    preparation = json.loads((dataset_root() / "prepared" / match_id / "manifest.json").read_text())
    report = {"match_id": match_id, "split": "train", "purpose": "development_smoke_only_not_held_out_performance",
              "protocol_sha256": sha256_file(config.MYA_DIR / "configs/external_protocol.json"),
              "input_archive_sha256": preparation["inputs_sha256"],
              "target_archive_sha256": preparation["targets_sha256"],
              "raw_sources": preparation["sources"],
              "code": code_provenance(), "baseline": protocol["baseline"], "scenarios": [], "selection_performed": False}
    targets = None
    for scenario in protocol["scenarios"]:
        seeds = protocol["scenario_seeds"] if scenario["kind"] != "clean" else protocol["scenario_seeds"][:1]
        for seed in seeds:
            observations, quality = degrade(inputs, scenario, seed)
            predicted = predict_external(observations, half_width=protocol["baseline"]["half_width"],
                                         missing_label=protocol["baseline"]["missing_label"])
            # Save prediction/config first. The prediction function never gets targets.
            prediction_path = folder / f"{scenario['name']}_{seed}.npy"
            np.save(prediction_path, predicted, allow_pickle=False)
            if targets is None:
                targets = load_targets(match_id, purpose="smoke")
                if not np.array_equal(targets.frame_ids, inputs.frame_ids) or not np.array_equal(targets.period_ids, inputs.period_ids):
                    raise ValueError("External observations/targets are misaligned")
            gt_codes, pred_codes = metrics.label_codes(targets.labels), metrics.label_codes(predicted)
            # Separate halves explicitly: official metrics take runs from non-X GT.
            # Add X separators so adjacent equal labels cannot merge across halftime.
            boundaries = [end for _, end in period_intervals(inputs)[:-1]]
            gt_codes = np.insert(gt_codes, boundaries, metrics.X)
            pred_codes = np.insert(pred_codes, boundaries, metrics.X)
            result = metrics.evaluate(gt_codes, pred_codes, bootstrap_n=0)
            report["scenarios"].append({"scenario": scenario["name"], "seed": seed, **quality,
               "spell_f1": result["spell_f1_mean"], "macro_f1": result["macro_f1"],
               "spell_f1_by_iou": {str(key): value["f1"] for key, value in result["spell_f1"].items()},
               "transitions": {str(key): value for key, value in result["transitions"].items()},
               "fragmentation": result["fragmentation"],
               "per_class": result["per_class"],
               "n_graded": result["n_graded"], "n_gt_spells": result["n_gt_spells"], "n_pred_spells": result["n_pred_spells"],
               "prediction_sha256": sha256_file(prediction_path)})
    _atomic_json(folder / "scores.json", report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--prepare", action="store_true", help="Download and strictly ingest the training smoke match")
    parser.add_argument("--benchmark", action="store_true", help="Evaluate the frozen baseline and all frozen smoke scenarios")
    args = parser.parse_args(argv)
    if not args.prepare and not args.benchmark:
        parser.error("Choose --prepare and/or --benchmark")
    try:
        match = settings("external_protocol.json")["smoke_match"]
        if args.prepare:
            inputs, targets, manifest = prepare_match(match, progress=lambda message: print(message, flush=True))
            print(f"Prepared {match}: {manifest['frame_count']} frames; separate inputs/targets; MD5 and SHA-256 recorded", flush=True)
        if args.benchmark:
            report = smoke_benchmark(match)
            clean = report["scenarios"][0]
            print(f"Training smoke baseline: spellF1={clean['spell_f1']:.4f}; macroF1={clean['macro_f1']:.4f}")
            print(f"{len(report['scenarios'])} fixed scenario/seed runs recorded; no selection; final test locked")
        return 0
    except Exception as error:
        destination = dataset_root() / "preflight-error.log"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(traceback.format_exc(), encoding="utf-8")
        print(f"External preflight failed ({type(error).__name__}); inspect local .cache/external/dfl/28196177/v1/preflight-error.log", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
