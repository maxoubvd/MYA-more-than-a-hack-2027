"""Synthetic external data only. No competition or DFL observations in tests."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from dataclasses import fields
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import numpy as np

from src import config
from src.external_benchmark import degrade, period_intervals, predict_external, smoke_benchmark
from src.utils.external_data import (ExternalInputs, ExternalTargets, INPUT_KEYS, atomic_npz,
    download_asset, load_inputs, load_targets, match_role, parse_match, settings, target_label)
from src.preprocessing.atd_parser import DataValidationError
from src.refinement.exporter import sha256_file


def xml_fixture(root, *, mutate=None, missing_ball=False):
    metadata = root / "metadata.xml"
    document = ET.Element("PutDataRequest")
    info = ET.SubElement(document, "MatchInformation")
    ET.SubElement(info, "General", MatchId="DFL-MAT-SYNTHETIC")
    ET.SubElement(info, "Environment", PitchX="100", PitchY="60")
    ET.SubElement(info, "OtherGameInformation", TotalTimeFirstHalf="120", TotalTimeSecondHalf="120")
    teams = ET.SubElement(info, "Teams")
    # Away first on purpose: order is not a home-team definition.
    for role, team_id, person in (("guest", "a", "away-person"), ("home", "h", "home-person")):
        team = ET.SubElement(teams, "Team", Role=role, TeamId=team_id)
        ET.SubElement(ET.SubElement(team, "Players"), "Player", PersonId=person, ShirtNumber="SECRET_UNUSED")
    ET.ElementTree(document).write(metadata)
    raw = ET.Element("PutDataRequest")
    for period, first in (("firstHalf", 100), ("secondHalf", 1000)):
        for team, person, x in (("h", "home-person", "0"), ("a", "away-person", "20"), ("BALL", "", "0")):
            fs = ET.SubElement(raw, "FrameSet", GameSection=period, MatchId="DFL-MAT-SYNTHETIC", TeamId=team, PersonId=person)
            for i in range(4):
                if missing_ball and team == "BALL" and i == 1:
                    continue
                stamp = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=i/25)
                attributes = dict(N=str(first+i), T=stamp.isoformat(), X=x, Y="0", S="999", Z="123")
                if team == "BALL":
                    attributes.update(BallStatus="0" if i==0 else "1", BallPossession="1" if i<3 else "2")
                ET.SubElement(fs, "Frame", **attributes)
    if mutate:
        mutate(raw)
    positions = root / "positions.xml"
    ET.ElementTree(raw).write(positions)
    return metadata, positions


def observation_fixture():
    n, slots = 80, 4
    players = np.zeros((n, slots, 2), dtype=np.float32)
    players[:, 2:, 0] = 1
    return ExternalInputs(players, np.zeros((n, 2), dtype=np.float32), np.ones((n, slots), dtype=bool),
        np.ones(n,dtype=bool), np.array(["H","H","A","A"]), np.r_[np.arange(100,140),np.arange(1000,1040)],
        np.r_[np.ones(40,dtype=np.int8),np.full(40,2,dtype=np.int8)],25.,(100.,60.))


class ExternalDataTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self):
        self.temporary.cleanup()

    def test_label_mapping_unknowns_never_default_to_away_or_dead(self):
        for status, owner, expected in (("0",None,"D"),("0","bad","D"),("1","1","H"),("1","2","A"),
                                         (None,"1","X"),("bad","2","X"),("1",None,"X"),("1","0","X"),("1","3","X")):
            self.assertEqual(target_label(status,owner),expected)

    def test_parser_keeps_dead_frames_periods_and_actual_geometry(self):
        metadata, raw = xml_fixture(self.root)
        inputs, targets, report = parse_match(metadata, raw, "SYNTHETIC")
        self.assertEqual(inputs.players_xy_normalized.shape,(8,2,2))
        self.assertEqual(inputs.pitch_dims,(100.,60.))
        self.assertEqual(inputs.team_mapping.tolist(),["A","H"])
        np.testing.assert_allclose(inputs.ball_xy_normalized,[ [.5,.5] ]*8)
        self.assertEqual(targets.labels.tolist(),list("DHHA"*2))
        self.assertEqual(period_intervals(inputs),((0,4),(4,8)))
        self.assertEqual(set(inputs.feature_dict()),INPUT_KEYS)

    def test_missing_ball_record_keeps_timeline_and_unknown_target(self):
        metadata, raw = xml_fixture(self.root,missing_ball=True)
        inputs, targets, report = parse_match(metadata,raw,"SYNTHETIC")
        self.assertEqual(len(inputs.frame_ids),8)
        self.assertFalse(inputs.ball_observed[1])
        self.assertEqual(targets.labels[1],"X")
        self.assertEqual(report['quality']['missing_ball_records'],2)

    def test_bad_status_does_not_change_observation_features(self):
        metadata, raw = xml_fixture(self.root)
        original, targets, _ = parse_match(metadata,raw,"SYNTHETIC")
        def alter(root):
            for fs in root.findall('FrameSet'):
                if fs.get('TeamId')=='BALL':
                    for frame in fs:
                        frame.set('BallStatus','unknown'); frame.set('BallPossession','unknown')
        metadata, raw = xml_fixture(self.root,mutate=alter)
        changed, bad_targets, _ = parse_match(metadata,raw,"SYNTHETIC")
        for name in INPUT_KEYS:
            np.testing.assert_array_equal(getattr(original,name),getattr(changed,name))
        self.assertTrue((bad_targets.labels=='X').all())

    def test_duplicate_unordered_nonfinite_mismatched_timestamp_rejected(self):
        mutations = [lambda r:r.find('FrameSet')[1].set('N','100'),
                     lambda r:r.find('FrameSet')[1].set('X','inf'),
                     lambda r:r.find('FrameSet').set('PersonId','unknown'),
                     lambda r:r.find('FrameSet').set('MatchId','other')]
        def bad_time(r):
            fs=next(fs for fs in r if fs.get('TeamId')=='BALL')
            fs[1].set('T',fs[0].get('T'))
        mutations.append(bad_time)
        for mutate in mutations:
            metadata, raw=xml_fixture(self.root,mutate=mutate)
            with self.assertRaises(DataValidationError):
                parse_match(metadata,raw,'SYNTHETIC')

    def test_truncated_xml_and_missing_period_rejected(self):
        metadata,raw=xml_fixture(self.root)
        raw.write_text(raw.read_text()[:-20])
        with self.assertRaises(DataValidationError): parse_match(metadata,raw,'SYNTHETIC')
        def remove_period(r):
            for fs in list(r):
                if fs.get('GameSection')=='secondHalf': r.remove(fs)
        metadata,raw=xml_fixture(self.root,mutate=remove_period)
        with self.assertRaises(DataValidationError): parse_match(metadata,raw,'SYNTHETIC')

    def test_download_hash_size_and_atomic_failure(self):
        payload=b'synthetic data'
        asset={'name':'fixture.xml','size':len(payload),'computed_md5':hashlib.md5(payload).hexdigest(),'download_url':'https://ndownloader.figshare.com/files/1'}
        with patch('urllib.request.urlopen',return_value=io.BytesIO(payload)):
            path=download_asset(asset,self.root)
        self.assertEqual(path.read_bytes(),payload)
        with patch('urllib.request.urlopen',side_effect=AssertionError('Must reuse verified file')):
            download_asset(asset,self.root)
        corrupted=dict(asset,computed_md5='wrong')
        with patch('urllib.request.urlopen',return_value=io.BytesIO(payload)),self.assertRaises(DataValidationError):
            download_asset(corrupted,self.root)
        self.assertEqual(path.read_bytes(),payload)
        self.assertEqual(list(self.root.glob('*.part')),[])

    def test_download_path_and_host_validation(self):
        for name,url in (('../outside','https://ndownloader.figshare.com/files/1'),('safe.xml','https://untrusted.example/1')):
            asset={'name':name,'size':1,'computed_md5':'x','download_url':url}
            with self.assertRaises(ValueError): download_asset(asset,self.root)

    def test_splits_disjoint_complete_and_test_locked(self):
        protocol=settings('external_protocol.json'); splits=protocol['splits']
        flattened=[m for ids in splits.values() for m in ids]
        self.assertEqual(len(flattened),7); self.assertEqual(len(set(flattened)),7)
        self.assertIn(protocol['smoke_match'],splits['train'])
        for test in splits['test']:
            with self.assertRaises(PermissionError): match_role(test)
            with self.assertRaises(PermissionError): load_inputs(test)
            with self.assertRaises(PermissionError): smoke_benchmark(test)

    def test_inputs_archive_never_opens_target_archive(self):
        inputs=observation_fixture()
        folder=self.root/'prepared/SYNTHETIC'; folder.mkdir(parents=True)
        atomic_npz(folder/'inputs.npz',**inputs.feature_dict())
        (folder/'manifest.json').write_text(json.dumps({'inputs_sha256':sha256_file(folder/'inputs.npz'),'parser_version':'dfl-strict-v1','protocol_sha256':sha256_file(config.MYA_DIR/'configs/external_protocol.json')}))
        real_load=np.load
        def guarded(path,*args,**kwargs):
            self.assertNotIn('targets',str(path)); return real_load(path,*args,**kwargs)
        with patch('src.utils.external_data.match_role',return_value='train'),patch('src.utils.external_data.dataset_root',return_value=self.root),patch('numpy.load',side_effect=guarded):
            restored=load_inputs('SYNTHETIC')
            predict_external(restored)
        self.assertEqual(set(restored.feature_dict()),INPUT_KEYS)

    def test_extra_label_field_in_input_archive_rejected(self):
        inputs=observation_fixture()
        folder=self.root/'prepared/SYNTHETIC';folder.mkdir(parents=True)
        atomic_npz(folder/'inputs.npz',**inputs.feature_dict(),labels=np.array(['H']))
        (folder/'manifest.json').write_text(json.dumps({'inputs_sha256':sha256_file(folder/'inputs.npz'),'parser_version':'dfl-strict-v1','protocol_sha256':sha256_file(config.MYA_DIR/'configs/external_protocol.json')}))
        with patch('src.utils.external_data.match_role',return_value='train'),patch('src.utils.external_data.dataset_root',return_value=self.root),self.assertRaises(DataValidationError):
            load_inputs('SYNTHETIC')

    def test_wrong_label_purpose_rejected_before_file_read(self):
        with patch('src.utils.external_data.match_role',return_value='validation'),self.assertRaises(PermissionError):
            load_targets('SYNTHETIC',purpose='training')


class ExternalBenchmarkTests(unittest.TestCase):
    def test_predictions_and_degradation_reject_target_containers(self):
        target=ExternalTargets(np.array(['H']),np.array([0]),np.array([1]))
        with self.assertRaises(TypeError): predict_external(target)
        with self.assertRaises(TypeError): degrade(target,{'kind':'clean'},0)
        self.assertFalse({field.name for field in fields(ExternalInputs)} & {'labels','BallStatus','BallPossession'})

    def test_scens_are_reproducible_labels_free_and_preserve_original(self):
        original=observation_fixture()
        protocol=settings('external_protocol.json')
        baseline=original.players_xy_normalized.copy()
        for scenario in protocol['scenarios']:
            first,quality=degrade(original,scenario,123)
            second,_=degrade(original,scenario,123)
            np.testing.assert_array_equal(first.players_xy_normalized,second.players_xy_normalized)
            np.testing.assert_array_equal(first.ball_xy_normalized,second.ball_xy_normalized)
            self.assertEqual(first.team_mapping.tolist(),original.team_mapping.tolist())
            if scenario['kind'] in ('ball_gaps','crowded_gaps','combined'):
                expected=sum(round((b-a)*scenario['missing_fraction']) for a,b in period_intervals(original))
                self.assertEqual(int((~first.ball_observed).sum()),expected)
        np.testing.assert_array_equal(original.players_xy_normalized,baseline)
        self.assertTrue(original.ball_observed.all())

    def test_external_half_boundary_has_no_inherited_team(self):
        inputs=observation_fixture()
        inputs.ball_xy_normalized[40:,0]=1
        labels=predict_external(inputs,half_width=100)
        self.assertTrue((labels[:40]=='H').all()); self.assertTrue((labels[40:]=='A').all())

    def test_actual_pitch_dimensions_are_used(self):
        inputs=observation_fixture()
        inputs.players_xy_normalized[:,:,:]=np.nan
        inputs.players_xy_normalized[:,0]=[.6,.5]
        # Actual 100x60 gives A=9.6m < H=10m; the competition 105.3x68
        # would incorrectly give H=10.53m < A=10.88m.
        inputs.players_xy_normalized[:,2]=[.5,.66]
        inputs.ball_xy_normalized[:]=[.5,.5]
        labels=predict_external(inputs,half_width=0)
        self.assertTrue((labels=='A').all())


if __name__=='__main__': unittest.main()
