"""Independent Kloppy consistency check on 200 frames of the training smoke match.

This validates schema/conventions; it is not new annotation or independent truth.
The strict XML parser remains authoritative for unknown status/owner handling.
"""
from __future__ import annotations

import json

import numpy as np

from src.utils.external_data import dataset_root, load_inputs, load_targets, metadata_from_xml, settings


def crosscheck_kloppy():
    from kloppy import sportec
    from kloppy.domain import BallState, Ground
    import kloppy

    match = settings("external_protocol.json")["smoke_match"]
    assets = settings("dfl_manifest.json")["matches"][match]
    root = dataset_root() / "raw"
    meta, raw = root / assets["metadata"]["name"], root / assets["positions"]["name"]
    inputs, targets = load_inputs(match), load_targets(match, purpose="smoke")
    reference = sportec.load_tracking(meta_data=str(meta), raw_data=str(raw), limit=200,
                                      coordinates="metrica", only_alive=False)
    index = {(int(p), int(f)): i for i, (p, f) in enumerate(zip(inputs.period_ids, inputs.frame_ids))}
    slots = {player: i for i, player in enumerate(sorted(metadata_from_xml(meta, match)["players"]))}
    coordinate_checks = label_checks = player_checks = 0
    for frame in reference.records:
        i = index[(frame.period.id, int(frame.frame_id))]
        np.testing.assert_allclose(inputs.ball_xy_normalized[i], [frame.ball_coordinates.x, frame.ball_coordinates.y], atol=1e-6)
        coordinate_checks += 1
        for player, observation in frame.players_data.items():
            np.testing.assert_allclose(inputs.players_xy_normalized[i, slots[player.player_id]],
                [observation.coordinates.x, observation.coordinates.y], atol=1e-6)
            expected = "H" if player.team.ground == Ground.HOME else "A"
            if inputs.team_mapping[slots[player.player_id]] != expected:
                raise ValueError("Kloppy team mapping disagrees with strict XML parser")
            player_checks += 1
        if targets.labels[i] != "X":
            expected = "D" if frame.ball_state == BallState.DEAD else "H" if frame.ball_owning_team.ground == Ground.HOME else "A"
            if expected != targets.labels[i]:
                raise ValueError("Kloppy known-state mapping disagrees with strict XML parser")
            label_checks += 1
    result = {"kloppy_version": kloppy.__version__, "only_alive": False, "coordinate_system": "metrica",
        "sample_frames": coordinate_checks, "player_coordinate_and_team_checks": player_checks,
        "known_target_mapping_checks": label_checks, "unknown_values_not_validated_through_kloppy_defaults": True,
        "scope": "API and parser consistency only; not independent ground truth annotation"}
    output = dataset_root() / "prepared" / match / "kloppy_crosscheck.json"
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    result = crosscheck_kloppy()
    print(f"Kloppy crosscheck passed: {result['sample_frames']} frames, {result['player_coordinate_and_team_checks']} player observations")
