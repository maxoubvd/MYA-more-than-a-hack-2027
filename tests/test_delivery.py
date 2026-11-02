"""Frozen package integrity, numerical contract, atomic export and final-test gate."""
import copy
from dataclasses import replace
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

from src import config
from src.delivery import (load_release,read_json,canonical_sha,code_sha,atomic_json,
                          quantize_scores,final_costs,export_csv,validate_csv,observation_scores)
from src.final_test import begin,scoring_targets
from src.experiments.archive import load_archived_j6
from src.features.builder import build_features
from src.features.team_assignment import FeatureInputs
from src.models.observations import factor_scores
from src.utils.external_data import match_role
from src.hygiene.repository_check import issues_for_paths


class DeliveryIntegrityTests(unittest.TestCase):
    def temporary_release(self,root):
        model=read_json(config.MYA_DIR/'release/model.json')
        atomic_json(root/'release/model.json',model)
        (root/'implementation.py').write_text('x = 1\n',encoding='utf-8')
        manifest={'version':'mya-delivery-v1','model_canonical_sha256':canonical_sha(model),
            'expected_csv_sha256':model['origin']['expected_csv_sha256'],
            'code_files':{'implementation.py':code_sha(root/'implementation.py')}}
        atomic_json(root/'release/manifest.json',manifest)
        return model,manifest

    def test_current_release_and_runtime_verified(self):
        package,manifest=load_release()
        self.assertEqual(package['team_scale'],1.)
        self.assertEqual(package['dead_scale'],2.)
        self.assertFalse(manifest['official_checkout_required_for_inference'])
        self.assertFalse(manifest['external_targets_required_for_inference'])

    def test_model_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); model,_=self.temporary_release(root)
            model['dead_scale']=3.
            atomic_json(root/'release/model.json',model)
            with self.assertRaises(ValueError): load_release(root,check_runtime=False)

    def test_code_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); self.temporary_release(root)
            (root/'implementation.py').write_text('x = 2\n',encoding='utf-8')
            with self.assertRaises(ValueError): load_release(root,check_runtime=False)

    def test_manifest_path_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); _,manifest=self.temporary_release(root)
            manifest['code_files']={'../escape.py':'0'*64}
            atomic_json(root/'release/manifest.json',manifest)
            with self.assertRaises(ValueError): load_release(root,check_runtime=False)

    def test_unsupported_runtime_rejected(self):
        with patch('src.delivery.platform.python_version',return_value='0.0.0'):
            with self.assertRaises(RuntimeError): load_release()
        with patch('src.delivery.importlib.metadata.version',return_value='0.0.0'):
            with self.assertRaises(RuntimeError): load_release()

    def test_crlf_and_bom_do_not_change_source_fingerprint(self):
        with tempfile.TemporaryDirectory() as d:
            a,b=Path(d)/'a.py',Path(d)/'b.py'
            a.write_bytes(b'x = 1\n')
            b.write_bytes(b'\xef\xbb\xbfx = 1\r\n')
            self.assertEqual(code_sha(a),code_sha(b))

    def test_float32_boundary_is_explicit_and_nonmutating(self):
        s=factor_scores(np.array([.123456789,.333333333]),np.array([.765432198,.333333333]),
            np.ones(2,dtype=bool),state_support=np.ones(2),team_support=np.ones(2),team_source=np.ones(2))
        old=s.probabilities.copy(); q=quantize_scores(s)
        self.assertEqual(q.probabilities.dtype,np.float32)
        self.assertEqual(q.p_dead.dtype,np.float32)
        np.testing.assert_array_equal(s.probabilities,old)
        np.testing.assert_array_equal(q.probabilities,old.astype(np.float32))

    def test_final_costs_keep_HA_and_double_only_D_changes(self):
        package,_=load_release()
        p=np.asarray(package['prior']['transition_probability'])
        original=-np.log(p); cost=final_costs(package)
        self.assertEqual(cost[0,1],original[0,1])
        np.testing.assert_array_equal(cost.diagonal(),original.diagonal())
        np.testing.assert_array_equal(cost[:2,2],original[:2,2]*2.)
        np.testing.assert_array_equal(cost[2,:2],original[2,:2]*2.)

    def test_synthetic_observations_require_neither_labels_nor_official_repo(self):
        package,_=load_release(); n=60
        players=np.broadcast_to(np.array([[.2,.3],[.3,.6],[.7,.3],[.8,.6]],dtype=np.float32),(n,4,2)).copy()
        ball=np.tile(np.array([.22,.3],dtype=np.float32),(n,1)); ball[20:30]=np.nan
        matrix=build_features(FeatureInputs(players,ball,np.array(['H','H','A','A']),
            np.arange(n),np.ones(n,dtype=int),25.,(105.3,68.)),settings=package['features'],context_model=package['context'])
        with (patch('src.utils.external_data.load_targets',side_effect=AssertionError('No labels')),
              patch('src.utils.official.load_official_metrics',side_effect=AssertionError('No official repo'))):
            result=observation_scores(matrix,package)
        self.assertEqual(result.probabilities.shape,(n,3))
        self.assertEqual(result.probabilities.dtype,np.float32)


class ExportTests(unittest.TestCase):
    def test_exact_export_and_validator(self):
        expected=hashlib.sha256(b'frame,label\n0,H\n1,D\n2,A\n').hexdigest()
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'MYA.csv'
            result=export_csv(path,np.array(['H','D','A']),expected)
            self.assertEqual(result['sha256'],expected)
            self.assertEqual(validate_csv(path,3),3)
            self.assertEqual(path.read_bytes(),b'frame,label\n0,H\n1,D\n2,A\n')

    def test_wrong_checksum_preserves_existing_output_and_cleans_temp(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'MYA.csv'; path.write_bytes(b'previous file')
            with self.assertRaises(RuntimeError): export_csv(path,np.array(['H','A']),'0'*64)
            self.assertEqual(path.read_bytes(),b'previous file')
            self.assertEqual(list(Path(d).iterdir()),[path])

    def test_invalid_csv_timeline_or_label_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'x.csv'
            for content in ('index,label\n0,H\n','frame,label\n1,H\n','frame,label\n0,HOME\n','frame,label\n'):
                p.write_text(content,encoding='utf-8')
                with self.assertRaises(ValueError): validate_csv(p,1)

    def test_private_final_csv_is_rejected_by_publication_guard(self):
        self.assertTrue(issues_for_paths('.', ['submissions/final/MYA.csv']))


class FinalTestGateTests(unittest.TestCase):
    def test_development_test_guard_remains_locked(self):
        with self.assertRaises(PermissionError): match_role('J03WR9')
        self.assertEqual(match_role('J03WR9',allow_final_test=True),'test')

    def test_completed_final_test_cannot_be_reopened(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); atomic_json(root/'result.json',{'done':True})
            with self.assertRaises(PermissionError): begin(root)

    def test_interrupted_final_test_cannot_resume_with_changed_freeze(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); begin(root)
            previous=read_json(root/'started.json'); previous['freeze']['release_sha256']='changed'
            atomic_json(root/'started.json',previous)
            with self.assertRaises(PermissionError): begin(root)

    def test_targets_not_opened_without_complete_snapshot(self):
        with tempfile.TemporaryDirectory() as d:
            with patch('src.final_test.np.load',side_effect=AssertionError('Target NPZ must stay closed')):
                with self.assertRaises(FileNotFoundError): scoring_targets(Path(d),{})

    def test_j6_archive_does_not_require_current_source_or_DFL_targets(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); cache=root/'cache'; public=root/'repo'
            internal={'experiment_id':'demo','values':[1]}; validation={'experiment_id':'demo','values':[2]}
            candidate={'experiment_id':'demo','export':{'sha256':'abc'},'family':'full','team_scale':1,'dead_scale':2,'decision':{'candidate':'selected'}}
            atomic_json(cache/'experiments/internal.json',internal); atomic_json(cache/'experiments/validation.json',validation)
            atomic_json(cache/'experiments/candidate.json',candidate)
            from src.delivery import sha256_file
            registry={'experiment_id':'demo','frozen_artifacts_sha256':{
                name:sha256_file(cache/'experiments'/name) for name in ('internal.json','validation.json')},
                'csv_sha256':'abc','candidate':{'family':'full','team_scale':1,'dead_scale':2},'decision':candidate['decision']}
            atomic_json(public/'analysis/jalon6_experiment_registry.json',registry)
            with patch.object(config,'MYA_DIR',public),patch.object(config,'CACHE_DIR',cache),patch('src.utils.external_data.load_targets',side_effect=AssertionError('No targets')):
                actual=load_archived_j6()
                self.assertEqual(actual,(internal,validation,candidate))
                atomic_json(cache/'experiments/internal.json',{'changed':True})
                with self.assertRaises(ValueError): load_archived_j6()


if __name__=='__main__': unittest.main()
