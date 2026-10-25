"""Synthetic fixtures only: no competition file or label is used by these tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd

from src import config
from src.hygiene.repository_check import issues_for_paths
from src.preprocessing.atd_parser import DataValidationError, parse_atd, parse_metadata
from src.preprocessing.cache_manager import ARRAY_KEYS, read_cache, provenance, write_cache
from src.preprocessing.coordinates import project, to_metres, unproject
from src.source_policy import load_registry, require_use, validate_source
from src.utils.loaders import load_atd, load_ground_truth, load_homography, load_smart_tagging


def make_xml(path, slots=2, frames=3, namespace=False, reverse_players=False):
    root = ET.Element("EPTS")
    teams = ET.SubElement(root, "Teams")
    for key, name in (("random-home", "Barcelona"), ("random-away", "Athletic Club")):
        team = ET.SubElement(teams, "Team", id=key)
        ET.SubElement(team, "Name").text = name
    players = ET.SubElement(root, "Players")
    for i in (reversed(range(slots)) if reverse_players else range(slots)):
        ET.SubElement(players, "Player", id=f"person-{i}", teamId="random-home" if i % 2 == 0 else "random-away")
    channels = ET.SubElement(root, "Channels")
    for key, name, unit in (("cx", "X", "normalized"), ("cy", "Y", "normalized"), ("cs", "Speed", "m/s")):
        channel = ET.SubElement(channels, "Channel", id=key)
        ET.SubElement(channel, "Name").text = name
        ET.SubElement(channel, "Unit").text = unit
    player_channels = ET.SubElement(root, "PlayerChannels")
    for i in range(slots):
        for key in ("cx", "cy", "cs"):
            ET.SubElement(player_channels, "PlayerChannel", id=f"p{i}-{key}", playerId=f"person-{i}", channelId=key)
    ET.SubElement(root, "FrameRate").text = "25"
    fmt = ET.SubElement(root, "DataFormatSpecification", separator=":", startFrame="1", endFrame=str(frames))
    ET.SubElement(fmt, "StringRegister", name="frame_id")
    registers = ET.SubElement(fmt, "SplitRegister", separator=";")
    for i in range(slots):
        register = ET.SubElement(registers, "SplitRegister", separator=",")
        for key in ("cx", "cy", "cs"):
            ET.SubElement(register, "PlayerChannelRef", playerChannelId=f"p{i}-{key}")
    ball = ET.SubElement(fmt, "SplitRegister", separator=",")
    for key in ("cx", "cy", "cs"):
        ET.SubElement(ball, "BallChannelRef", channelId=key)
    if namespace:
        for elem in root.iter():
            elem.tag = "{urn:synthetic}" + elem.tag
    ET.ElementTree(root).write(path, encoding="utf-8")


def make_atd(path, slots=2, ids=(1, 2, 3), missing=False):
    lines = []
    for frame in ids:
        players = ["0.25,0.5,2.0"] * slots
        ball = "0.5,0.75,3.0"
        if missing and frame == 2:
            players[0], ball = "NaN,NaN,NaN", "NaN,NaN,NaN"
        lines.append(f"{frame}:{';'.join(players)}:{ball}\n")
    path.write_text("".join(lines), encoding="utf-8")


class IngestionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.txt, self.xml, self.cache = (self.root / name for name in ("input.txt", "input.xml", "cache.npz"))
        make_atd(self.txt)
        make_xml(self.xml)
        self.spec = config.SourceSpec("tactical", 3, 2, self.txt, self.xml, self.root / "h.csv", self.root / "v.mp4", self.cache)

    def tearDown(self):
        self.temporary.cleanup()

    def load(self, **kwargs):
        with patch("src.config.get_source", return_value=self.spec):
            return load_atd(**kwargs)

    def mutate_xml(self, action):
        tree = ET.parse(self.xml)
        action(tree.getroot())
        tree.write(self.xml, encoding="utf-8")

    def test_valid_alignment_metrics_and_missing(self):
        make_atd(self.txt, missing=True)
        result = self.load()
        np.testing.assert_array_equal(result["video_frames"], [0, 1, 2])
        np.testing.assert_array_equal(result["ball_observed"], [True, False, True])
        self.assertTrue(np.isnan(result["players"][1, 0]).all())
        np.testing.assert_allclose(result["players_metres"][0, 0], [26.325, 34, 2])

    def test_speed_and_position_masks_independent(self):
        text = self.txt.read_text().replace("0.25,0.5,2.0", "0.25,0.5,NaN").replace("0.5,0.75,3.0", "NaN,0.75,3.0")
        self.txt.write_text(text)
        result = self.load()
        self.assertTrue(result["players_observed"].all())
        self.assertFalse(result["players_speed_observed"].any())
        self.assertFalse(result["ball_observed"].any())
        self.assertTrue(result["ball_speed_observed"].all())

    def test_truncated_extra_disordered_duplicate_offset_missing_rows(self):
        for ids in ((1, 2), (1, 2, 3, 4), (1, 3, 2), (1, 1, 3), (2, 3, 4), (1, 3)):
            with self.subTest(ids=ids):
                make_atd(self.txt, ids=ids)
                with self.assertRaises(DataValidationError):
                    self.load(use_cache=False)

    def test_bad_fields_and_infinity_fail_without_echoing_values(self):
        original = self.txt.read_text()
        for replacement in ("SECRET_PRIVATE_TOKEN", "inf", "1e100", "", "0.25,0.5"):
            self.txt.write_text(original.replace("0.25,0.5,2.0", replacement, 1))
            with self.subTest(replacement=replacement), self.assertRaises(DataValidationError) as raised:
                self.load(use_cache=False)
            self.assertNotIn("SECRET_PRIVATE_TOKEN", str(raised.exception))

    def test_blank_record_is_not_missing_observation(self):
        self.txt.write_text(self.txt.read_text().replace("2:", "\n2:", 1))
        with self.assertRaises(DataValidationError):
            self.load()

    def test_trailing_player_separator_accepted(self):
        self.txt.write_text(self.txt.read_text().replace(":0.5,0.75,3.0", ";:0.5,0.75,3.0"))
        self.assertEqual(self.load()["players"].shape, (3, 2, 3))

    def test_preview_validates_tail_and_never_caches(self):
        self.assertEqual(self.load(max_frames=1)["ball"].shape, (1, 3))
        self.assertFalse(self.cache.exists())
        self.txt.write_text(self.txt.read_text() + "4:invalid\n")
        with self.assertRaises(DataValidationError):
            self.load(max_frames=1)
        for maximum in (0, -1, 4, 1.5, True):
            with self.assertRaises(ValueError):
                self.load(max_frames=maximum)

    def test_team_mapping_follows_channels_not_player_order_with_namespaces(self):
        make_xml(self.xml, namespace=True, reverse_players=True)
        self.assertEqual(self.load()["team_mapping"], {0: "H", 1: "A"})

    def test_xml_bad_counts_unknown_team_channel_and_frame_range(self):
        actions = [lambda r: r.find("Players").remove(r.find("Players/Player")),
                   lambda r: r.find("Players/Player").set("teamId", "unknown"),
                   lambda r: r.find("DataFormatSpecification").set("endFrame", "4"),
                   lambda r: r.find("DataFormatSpecification/SplitRegister/SplitRegister/PlayerChannelRef").set("playerChannelId", "unknown"),
                   lambda r: r.find("Channels/Channel/Unit").__setattr__("text", "metres")]
        for action in actions:
            make_xml(self.xml)
            self.mutate_xml(action)
            with self.assertRaises(DataValidationError):
                self.load(use_cache=False)

    def test_broadcast_51_slots_and_source_specific_xml(self):
        make_xml(self.xml, slots=51)
        make_atd(self.txt, slots=51)
        self.spec = config.SourceSpec("broadcast", 3, 51, self.txt, self.xml, self.root / "h.csv", self.root / "v.mp4", self.cache)
        result = self.load(source="broadcast")
        self.assertEqual(result["players"].shape, (3, 51, 3))
        self.assertEqual(len(result["team_mapping"]), 51)
        self.assertEqual(result["source"], "broadcast")

    def test_epts_position_names_and_native_kph_are_preserved(self):
        def adapt(root):
            root.find("Channels/Channel/Name").text = "position_x"
            root.find("Channels")[1].find("Name").text = "position_y"
            root.find("Channels")[2].find("Name").text = "speed_abs"
            root.find("Channels")[2].find("Unit").text = "kph"
        self.mutate_xml(adapt)
        result = self.load()
        self.assertEqual(result["speed_unit"], "km/h")
        self.assertTrue(result["speed_documentation_conflict"])
        self.assertEqual(result["players_metres"][0, 0, 2], 2)

    def test_cache_roundtrip_and_disabled_cache(self):
        direct = self.load(use_cache=False)
        cached = self.load(save_cache=False)
        self.assertTrue(cached["cache_hit"])
        for key in ARRAY_KEYS:
            np.testing.assert_array_equal(direct[key], cached[key])
        self.assertFalse(self.load(use_cache=False, save_cache=False)["cache_hit"])

    def test_cache_invalidation_content_even_same_size_and_timestamp(self):
        self.load()
        before = self.txt.stat()
        self.txt.write_text(self.txt.read_text().replace("0.25", "0.75"))
        os.utime(self.txt, ns=(before.st_atime_ns, before.st_mtime_ns))
        result = self.load()
        self.assertFalse(result["cache_hit"])
        self.assertEqual(result["players"][0, 0, 0], .75)

    def test_cache_invalidation_xml_path_source_parser(self):
        self.load()
        self.mutate_xml(lambda r: r.find("Players/Player").set("teamId", "random-away"))
        self.assertFalse(self.load()["cache_hit"])
        self.assertEqual(self.load()["team_mapping"][0], "A")
        other = self.root / "other.txt"
        shutil.copyfile(self.txt, other)
        self.assertFalse(self.load(path=other)["cache_hit"])
        self.assertFalse(self.load(source="broadcast")["cache_hit"])
        with patch("src.preprocessing.cache_manager.PARSER_VERSION", "future-parser"):
            self.assertFalse(self.load()["cache_hit"])

    def test_old_incomplete_corrupt_bad_shape_and_bad_ids_cache_reparsed(self):
        original = self.load()
        arrays = {key: original[key] for key in ARRAY_KEYS}
        for mutate in (lambda a: a.pop("ball"), lambda a: a.update(players=np.zeros((1, 1, 3))),
                       lambda a: a.update(frame_ids=np.array([2, 3, 4], dtype=np.int32))):
            wrong = dict(arrays)
            mutate(wrong)
            np.savez(self.cache, **wrong, metadata=np.array(json.dumps(original["provenance"])))
            self.assertFalse(self.load()["cache_hit"])
        np.savez(self.cache, **arrays)  # previous implementation, no provenance
        self.assertFalse(self.load()["cache_hit"])
        self.cache.write_bytes(b"not a zip")
        self.assertFalse(self.load()["cache_hit"])

    def test_atomic_cache_failure_keeps_previous_file(self):
        result = self.load()
        previous = self.cache.read_bytes()
        with patch("src.preprocessing.cache_manager.os.replace", side_effect=OSError("synthetic failure")):
            with self.assertRaises(OSError):
                write_cache(self.cache, {key: result[key] for key in ARRAY_KEYS}, result["provenance"])
        self.assertEqual(self.cache.read_bytes(), previous)
        self.assertEqual(list(self.root.glob("*.tmp")), [])

    def homography(self):
        table = pd.DataFrame({"frame": [0, 1, 2], "reprojection_error": [.1, np.nan, .3], "valid": [1, 0, 1]})
        for r in range(3):
            for c in range(3):
                table[f"h{r}{c}"] = [float(r == c), np.nan, float(r == c)]
        return table

    def test_homography_valid_and_invalid(self):
        self.homography().to_csv(self.spec.homography_path, index=False)
        with patch("src.config.get_source", return_value=self.spec):
            matrices, error, valid, table = load_homography()
        self.assertTrue(np.isnan(matrices[1]).all())
        np.testing.assert_array_equal(valid, [True, False, True])

    def test_homography_rejects_bad_frame_flags_errors_and_matrices(self):
        for column, row, value in (("frame", 1, 0), ("valid", 1, np.nan), ("valid", 1, 2),
                                   ("h00", 0, np.inf), ("h00", 0, np.nan), ("h00", 1, 1),
                                   ("h00", 0, 0), ("reprojection_error", 0, -np.inf), ("reprojection_error", 0, np.nan)):
            table = self.homography()
            table.loc[row, column] = value
            table.to_csv(self.spec.homography_path, index=False)
            with patch("src.config.get_source", return_value=self.spec), self.assertRaises(DataValidationError):
                load_homography()

    def test_negative_homography_error_is_explicitly_unavailable(self):
        table = self.homography()
        table.loc[0, "reprojection_error"] = -5
        table.to_csv(self.spec.homography_path, index=False)
        with patch("src.config.get_source", return_value=self.spec):
            matrices, errors, valid, raw = load_homography()
        self.assertTrue(valid[0])
        self.assertTrue(np.isnan(errors[0]))
        self.assertFalse(raw.reprojection_error_observed.iloc[0])
        self.assertEqual(raw.reprojection_error.iloc[0], -5)

    def smart(self, start="0.02", end="0.10", team="N/A"):
        self.xml.write_text(f'<file><instance><start>{start}</start><end>{end}</end><code>set pieces</code>'
                            f'<label><group>tEaM</group><text>{team}</text></label>'
                            '<label><group>Future field</group><text>unknown</text></label></instance></file>')

    def test_smart_case_na_unknown_half_open_rounding(self):
        self.smart()
        table = load_smart_tagging(self.xml, num_frames=3)
        row = table.iloc[0]
        self.assertEqual((row.start_frame, row.end_frame, row.duration_frames), (1, 3, 2))
        self.assertEqual(row.team, "N/A")
        self.assertIsNone(row.team_code)
        self.assertEqual(row.raw_tags["Future field"], "unknown")
        self.smart(team="bArCeLoNa")
        self.assertEqual(load_smart_tagging(self.xml, num_frames=3).iloc[0].team_code, "H")

    def test_smart_rejects_negative_reversed_nonfinite_and_out_of_bounds(self):
        for start, end in (("-1", "1"), ("1", "0"), ("0", "0"), ("NaN", "1"), ("0", "inf"), ("0", "1"), ("bad", ".1")):
            self.smart(start, end)
            with self.assertRaises(DataValidationError):
                load_smart_tagging(self.xml, num_frames=3)


class PolicyGeometryConfigurationTests(unittest.TestCase):
    def test_public_labels_refuse_learning_calibration_selection_before_reading(self):
        for purpose in ("training", "calibration", "selection", "external_validation", "pipeline"):
            with self.assertRaises(PermissionError):
                load_ground_truth(Path("does-not-exist.csv"), purpose=purpose)
        self.assertEqual(require_use("public_labels", "diagnostic")["nature"], "human")

    def test_unregistered_and_human_match_sources_rejected(self):
        with self.assertRaises(PermissionError):
            require_use("unregistered", "pipeline")
        source = dict(load_registry()["sources"][0], id="forbidden", nature="human")
        with self.assertRaises(PermissionError):
            validate_source(source)

    def test_geometry_roundtrip_speed_and_no_mutation(self):
        observations = np.array([[.5, .5, 7], [np.nan, .2, np.nan]])
        metric = to_metres(observations)
        np.testing.assert_allclose(metric[0], [52.65, 34, 7])
        self.assertEqual(observations[0, 0], .5)
        matrix = np.array([[100, 2, 3], [5, 200, 7], [.1, .2, 1]])
        points = np.array([[.25, .75], [.1, .2]])
        np.testing.assert_allclose(unproject(matrix, project(matrix, points)), points)
        self.assertTrue(np.isnan(unproject(np.zeros((3, 3)), points)).all())
        self.assertTrue(np.isnan(project(np.full((3, 3), np.nan), points)).all())

    def test_source_contracts_and_unknown_source(self):
        self.assertEqual((config.get_source("tactical").num_frames, config.get_source("tactical").num_slots), (199319, 46))
        self.assertEqual((config.get_source("broadcast").num_frames, config.get_source("broadcast").num_slots), (164488, 51))
        with self.assertRaises(ValueError):
            config.get_source("unknown")

    def test_config_renamed_repo_overrides_and_no_import_mkdir(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "arbitrary-repository-name"
            (root / "src").mkdir(parents=True)
            shutil.copyfile(config.SRC_DIR / "config.py", root / "src" / "config.py")
            env = dict(os.environ, MTAH_CHALLENGE_DIR=str(Path(directory) / "official-custom"),
                       MTAH_DATA_DIR=str(Path(directory) / "data-custom"), MTAH_CACHE_DIR=str(Path(directory) / "cache-custom"))
            script = 'from pathlib import Path; from unittest.mock import patch; import runpy; ' + \
                'p=patch.object(Path,"mkdir",side_effect=RuntimeError("import writes")); p.start(); ' + \
                'c=runpy.run_path("src/config.py"); ' + \
                'print(c["MYA_DIR"].name); print(c["CHALLENGE_DIR"].name); print(c["DATA_DIR"].name); print(c["CACHE_DIR"].name)'
            process = subprocess.run([sys.executable, "-c", script], cwd=root, env=env, capture_output=True, text=True)
            self.assertEqual(process.returncode, 0, process.stderr)
            self.assertEqual(process.stdout.splitlines(), [root.name, "official-custom", "data-custom", "cache-custom"])
            self.assertFalse((Path(directory) / "cache-custom").exists())

    def test_publication_check_detects_notebook_outputs_and_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "n.ipynb").write_text(json.dumps({"cells": [{"cell_type": "code", "outputs": [{"text": "private"}], "execution_count": 1}]}))
            self.assertEqual(len(issues_for_paths(root, ["n.ipynb", "data/private.csv", "bad:name.pdf"])), 3)


if __name__ == "__main__":
    unittest.main()
