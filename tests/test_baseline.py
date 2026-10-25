"""J2: synthetic geometries, temporal boundaries and atomic export failures."""
from __future__ import annotations

import json
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.baseline import majority_vote, nearest_team_labels, predict_baseline
from src.diagnostics import frozen_submission
from src.hygiene.masking import apply_official_masks, checked_intervals, evaluated_mask
from src.hygiene.validator import validate_labels, validate_submission_file
from src.pipeline import main, run
from src.refinement.exporter import export_submission, sha256_file


class SyntheticMetrics:
    """IO double only. Actual official CLI acceptance is an integration check."""
    read_label_csv = staticmethod(pd.read_csv)

    @staticmethod
    def validate_submission(table, n_expected):
        return None if len(table) == n_expected else "incorrect row count"


def fixture(n=12):
    players = np.zeros((n, 2, 3), dtype=np.float32)
    players[:, 1, 0] = 1
    ball = np.zeros((n, 3), dtype=np.float32)
    return {"players": players, "ball": ball, "team_mapping": {0: "H", 1: "A"},
            "video_frames": np.arange(n), "source": "tactical", "complete": True,
            "provenance": {"synthetic": True}}


class BaselineTests(unittest.TestCase):
    def test_nearest_player_scales_rectangular_pitch_and_ignores_speed(self):
        # In normalised coordinates H is closer; in metres A is closer.
        players = np.array([[[.6, .5, np.nan], [.5, .64, 1000]]])
        ball = np.array([[.5, .5, np.nan]])
        np.testing.assert_array_equal(nearest_team_labels(players, ball, {0: "H", 1: "A"}), ["A"])

    def test_exact_distance_tie_is_first_xml_slot(self):
        players = np.array([[[.4, .5, 0], [.6, .5, 0]]])
        ball = np.array([[.5, .5, 0]])
        self.assertEqual(nearest_team_labels(players, ball, {0: "A", 1: "H"})[0], "A")

    def test_missing_ball_players_partial_xy_and_explicit_abstention(self):
        atd = fixture(4)
        atd["ball"][0, :2] = np.nan
        atd["players"][1, :, :2] = np.nan
        atd["players"][2, 0, 1] = np.nan
        result = nearest_team_labels(atd["players"], atd["ball"], atd["team_mapping"])
        np.testing.assert_array_equal(result, ["D", "D", "A", "H"])
        result_x = nearest_team_labels(atd["players"], atd["ball"], atd["team_mapping"], missing_label="X")
        np.testing.assert_array_equal(result_x, ["X", "X", "A", "H"])

    def test_batches_and_slot_permutations_preserve_unambiguous_result(self):
        atd = fixture(19)
        atd["ball"][::2, 0] = 1
        reference = nearest_team_labels(atd["players"], atd["ball"], atd["team_mapping"], batch_size=1)
        actual = nearest_team_labels(atd["players"][:, ::-1], atd["ball"], {0: "A", 1: "H"}, batch_size=7)
        np.testing.assert_array_equal(reference, actual)

    def test_invalid_tracking_mapping_and_infinity_rejected(self):
        atd = fixture(2)
        for mapping in ({0: "H"}, {0: "H", 1: "U"}):
            with self.assertRaises(ValueError):
                nearest_team_labels(atd["players"], atd["ball"], mapping)
        atd["ball"][0, 0] = np.inf
        with self.assertRaises(ValueError):
            nearest_team_labels(atd["players"], atd["ball"], atd["team_mapping"])

    def test_majority_matches_simple_official_rule_for_all_windows(self):
        labels = np.array(list("DHADDAHXADHDD"))
        for width in (0, 1, 2, 25, 50, 125):
            expected = labels.copy()
            if width:
                for i in range(len(labels)):
                    window = labels[max(0, i-width):i+width+1]
                    home, away = np.sum(window == "H"), np.sum(window == "A")
                    expected[i] = "H" if home >= away and home else "A" if away else "D"
            np.testing.assert_array_equal(majority_vote(labels, width), expected)

    def test_majority_tie_home_no_votes_and_clipped_edges(self):
        np.testing.assert_array_equal(majority_vote(list("HDA"), 1), list("HHA"))
        np.testing.assert_array_equal(majority_vote(list("XXX"), 50, missing_label="X"), list("XXX"))
        np.testing.assert_array_equal(majority_vote(list("DDD"), 50), list("DDD"))
        for width in (-1, 1.5, True):
            with self.assertRaises(ValueError):
                majority_vote(list("HDA"), width)

    def test_no_smoothing_between_periods_or_from_non_evaluated_frames(self):
        atd = fixture()
        atd["ball"][8:, 0] = 1  # A only in the second period
        labels = predict_baseline(atd, half_width=50, intervals=((2, 5), (8, 11)), dead_zone=None)
        np.testing.assert_array_equal(labels, list("XXHHHXXXAAAX"))

    def test_no_previous_half_fill_at_empty_period_head(self):
        atd = fixture()
        atd["ball"][8:11, :2] = np.nan
        labels = predict_baseline(atd, half_width=50, missing_label="X", intervals=((2, 5), (8, 11)), dead_zone=None)
        np.testing.assert_array_equal(labels, list("XXHHHXXXXXXX"))

    def test_dead_zone_overrides_any_vote_including_wide_window(self):
        atd = fixture()
        labels = predict_baseline(atd, half_width=50, intervals=((2, 5), (8, 11)), dead_zone=(8, 10))
        np.testing.assert_array_equal(labels, list("XXHHHXXXDDHX"))

    def test_published_mask_boundaries_are_half_open(self):
        labels = apply_official_masks(np.full(199319, "A"))
        for frame in (0, 11184, 90652, 110807, 190198, 199318):
            self.assertEqual(labels[frame], "X")
        for frame in (11185, 90651, 113742, 190197):
            self.assertEqual(labels[frame], "A")
        self.assertEqual(labels[110808], "D")
        self.assertEqual(labels[113741], "D")
        self.assertEqual(int(evaluated_mask().sum()), 158857)

    def test_invalid_periods_and_dead_zone_rejected(self):
        for intervals in (((2, 5), (4, 6)), ((4, 2),), ((-1, 2),), ((0, 20),)):
            with self.assertRaises(ValueError):
                checked_intervals(12, intervals)
        with self.assertRaises(ValueError):
            apply_official_masks(list("H"*12), intervals=((2, 5),), dead_zone=(0, 1))

    def test_wrong_source_partial_or_misaligned_input_rejected(self):
        for key, value in (("source", "broadcast"), ("complete", False), ("video_frames", np.arange(1, 13))):
            atd = fixture()
            atd[key] = value
            with self.assertRaises(ValueError):
                predict_baseline(atd, intervals=((2, 5),), dead_zone=None)

    def test_labels_do_not_silently_truncate_or_fill(self):
        for labels in (["HOME"], [""], [None], ["h"], [["H"]], [1]):
            with self.assertRaises(ValueError):
                validate_labels(labels)
        with self.assertRaises(ValueError):
            validate_labels(["H"], n_expected=2)


class ExportPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.metrics = patch("src.hygiene.validator.load_official_metrics", return_value=SyntheticMetrics)
        self.metrics.start()

    def tearDown(self):
        self.metrics.stop()
        self.temporary.cleanup()

    def test_deterministic_lf_exact_header_and_no_index(self):
        first = export_submission(self.root / "one.csv", list("HADX"), n_expected=4)
        second = export_submission(self.root / "two.csv", list("HADX"), n_expected=4)
        self.assertEqual(first["sha256"], second["sha256"])
        self.assertEqual((self.root / "one.csv").read_bytes(), b"frame,label\n0,H\n1,A\n2,D\n3,X\n")

    def test_bad_labels_do_not_replace_existing_output(self):
        path = self.root / "keep.csv"
        path.write_bytes(b"previous")
        with self.assertRaises(ValueError):
            export_submission(path, ["HOME"], n_expected=1)
        self.assertEqual(path.read_bytes(), b"previous")

    def test_official_validation_failure_is_atomic(self):
        path = self.root / "keep.csv"
        path.write_bytes(b"previous")
        with patch("src.refinement.exporter.validate_submission_file", side_effect=ValueError("synthetic rejection")):
            with self.assertRaises(ValueError):
                export_submission(path, ["H"], n_expected=1)
        self.assertEqual(path.read_bytes(), b"previous")
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["keep.csv"])

    def test_exact_columns_enforced_on_top_of_official_validator(self):
        path = self.root / "extra.csv"
        path.write_text("frame,label,extra\n0,H,value\n")
        with self.assertRaises(ValueError):
            validate_submission_file(path, n_expected=1)

    def test_pipeline_reproducible_without_ground_truth_and_with_provenance(self):
        atd = fixture()
        with patch("src.pipeline.load_atd", return_value=atd), \
             patch("src.pipeline.check_official_revision", return_value="synthetic-revision"), \
             patch("src.pipeline.code_provenance", return_value={"source_files_sha256": {"synthetic": "sha"}}), \
             patch("src.utils.loaders.load_ground_truth", side_effect=AssertionError("Must never read labels")), \
             patch("src.utils.loaders.load_ground_truth_meta", side_effect=AssertionError("Must never read labels")), \
             patch("src.config.TOTAL_FRAMES", 12), patch("src.config.EVALUATED_INTERVALS", ((2, 5), (8, 11))), \
             patch("src.config.DEAD_ZONE_2HT_INTERVAL", (8, 10)), patch("src.config.CACHE_DIR", self.root):
            first = run(self.root / "first.csv")
            second = run(self.root / "second.csv")
        self.assertEqual(first["sha256"], second["sha256"])
        manifest = json.loads(Path(first["manifest"]).read_text())
        self.assertFalse(manifest["ground_truth_used"])
        self.assertEqual(manifest["settings"]["half_width"], 50)
        self.assertEqual(manifest["output"]["official_validation"], "passed")

    def test_negative_cli_window_rejected_before_loading(self):
        with patch("sys.stderr", new=io.StringIO()), self.assertRaises(SystemExit) as raised:
            main(["--window", "-1"])
        self.assertEqual(raised.exception.code, 2)

    def test_diagnostic_requires_candidate_frozen_before_reading_labels(self):
        path = self.root / "candidate.csv"
        path.write_bytes(b"frame,label\n0,H\n")
        with patch("src.config.CACHE_DIR", self.root), self.assertRaises(ValueError):
            frozen_submission(path)

    def test_diagnostic_accepts_frozen_configuration_and_rejects_changed_bytes(self):
        path = self.root / "candidate.csv"
        path.write_bytes(b"frame,label\n0,H\n")
        digest = sha256_file(path)
        folder = self.root / "runs"
        folder.mkdir()
        manifest = {"output": {"sha256": digest}, "ground_truth_used": False, "settings": {"half_width": 50}}
        (folder / f"baseline_{digest}.json").write_text(json.dumps(manifest))
        with patch("src.config.CACHE_DIR", self.root):
            _, actual, frozen = frozen_submission(path)
            self.assertEqual(actual, digest)
            self.assertEqual(frozen["settings"]["half_width"], 50)
            path.write_bytes(b"frame,label\n0,A\n")
            with self.assertRaises(ValueError):
                frozen_submission(path)

    def test_diagnostic_rejects_label_using_or_inconsistent_manifest(self):
        path = self.root / "candidate.csv"
        path.write_bytes(b"frame,label\n0,H\n")
        digest = sha256_file(path)
        folder = self.root / "runs"
        folder.mkdir()
        for reported_hash, used_labels in ((digest, True), ("wrong-hash", False)):
            manifest = {"output": {"sha256": reported_hash}, "ground_truth_used": used_labels}
            (folder / f"baseline_{digest}.json").write_text(json.dumps(manifest))
            with patch("src.config.CACHE_DIR", self.root), self.assertRaises(ValueError):
                frozen_submission(path)


if __name__ == "__main__":
    unittest.main()
