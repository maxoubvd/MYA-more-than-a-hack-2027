"""State/control isolation, uncertainty, split hygiene and logistic mathematics."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from src.features.builder import FeatureMatrix, build_features
from src.features.team_assignment import FeatureInputs
from src.imputation.deadball_detector import state_rule_evidence
from src.models.anchors import hold_control
from src.models.dataset import (FeatureBlock, observation_design, training_examples,
                                aligned_labels)
from src.models.observations import factor_scores, rule_scores, model_scores
from src.models.tabular import fit_logistic, predict_logistic, fit_factorized, transform
from src.observation_pipeline import save_scores, load_scores, probability_metrics, options, validate as validate_external
from src.utils.external_data import ExternalTargets


def fixture(n=90, missing_ball=False):
    t = np.arange(n, dtype=np.float32)/25.
    players = np.broadcast_to(np.array([[.2,.3],[.25,.6],[.7,.3],[.75,.6]], dtype=np.float32), (n,4,2)).copy()
    players[...,0] += t[:,None]*.01
    ball = np.column_stack((.21+t*.01, np.full(n,.3))).astype(np.float32)
    if missing_ball: ball[:] = np.nan
    inputs = FeatureInputs(players, ball, np.array(['H','H','A','A']), np.arange(n),
                           np.ones(n,dtype=int), 25., (100.,60.))
    return build_features(inputs)


def change(matrix, **columns):
    result = replace(matrix, values=matrix.values.copy(), valid=matrix.valid.copy())
    for name, value in columns.items():
        result.values[:,result.names.index(name)] = value
    result.valid[:] = np.isfinite(result.values)
    return result


def small_model(matrix):
    labels = np.resize(np.array(['H','A','D']),len(matrix.frame_ids))
    targets = ExternalTargets(labels, matrix.frame_ids.copy(), matrix.period_ids.copy())
    batch = training_examples('J03WMX','synthetic',matrix,targets,maximum_rows=90)
    opt = {'l2':.01,'max_iterations':50,'gradient_tolerance':1e-6,'standardized_clip':8.}
    return fit_factorized([batch],opt), batch, opt


class StateAndControlTests(unittest.TestCase):
    def test_state_rules_ignore_proximity_team_and_tactical_support(self):
        matrix = fixture()
        changed = change(matrix,H_distance_kernel=0.,A_distance_kernel=1.,
            H_motion_distance_kernel=0.,A_motion_distance_kernel=1.,
            H_nearest_1_m=100.,A_nearest_1_m=.01,tag_H_minus_A=-100.,
            H_centroid_x_m=99.,A_centroid_x_m=1.)
        np.testing.assert_array_equal(state_rule_evidence(matrix)[1],state_rule_evidence(changed)[1])
        np.testing.assert_array_equal(observation_design(matrix).state.values,observation_design(changed).state.values)
        self.assertFalse(np.array_equal(rule_scores(matrix).p_home_given_alive,rule_scores(changed).p_home_given_alive))

    def test_missing_ball_alone_never_becomes_a_dead_decision(self):
        matrix = fixture(missing_ball=True)
        scores = rule_scores(matrix)
        np.testing.assert_allclose(scores.p_dead,1./3.)
        np.testing.assert_allclose(scores.p_home_given_alive,.5)
        self.assertTrue((scores.labels()=='X').all())
        self.assertTrue((scores.team_source==0).all())

    def test_stationary_ball_needs_collective_context_and_is_not_forced_dead(self):
        matrix = fixture()
        stopped = change(matrix,ball_speed_mps=0.,ball_low_motion_score=1.,
                         ball_low_motion_run_s=2.,collective_median_speed_mps=.1)
        fast_collective = change(stopped,collective_median_speed_mps=6.)
        self.assertGreater(rule_scores(stopped).p_dead[10],rule_scores(fast_collective).p_dead[10])
        self.assertLess(rule_scores(stopped).p_dead[10],1.)

    def test_outside_candidate_increases_state_evidence_without_nearest_player(self):
        matrix = fixture()
        outside = change(matrix,ball_boundary_distance_m=-3.)
        self.assertGreater(rule_scores(outside).p_dead[10],rule_scores(matrix).p_dead[10])

    def test_unobserved_everything_has_uniform_probabilities_and_zero_confidence(self):
        matrix = fixture()
        unknown = replace(matrix,values=np.full_like(matrix.values,np.nan),valid=np.zeros_like(matrix.valid))
        rules = rule_scores(unknown)
        np.testing.assert_allclose(rules.probabilities,1./3.)
        np.testing.assert_allclose(rules.confidence,0.,atol=1e-14)
        model,_,_ = small_model(matrix)
        np.testing.assert_allclose(model_scores(unknown,model).probabilities,1./3.)

    def test_real_empty_tracking_does_not_count_missing_window_support_as_evidence(self):
        matrix=fixture();model,_,_=small_model(matrix)
        # A strong fitted prior cannot justify a state decision without observations.
        model['heads']['state']['coefficients'][0]=3.
        inputs=FeatureInputs(np.full((30,4,2),np.nan),np.full((30,2),np.nan),
            np.array(['H','H','A','A']),np.arange(30),np.ones(30,dtype=int),25.,(100.,60.))
        scores=model_scores(build_features(inputs),model)
        self.assertTrue((scores.state_support==0).all())
        np.testing.assert_allclose(scores.probabilities,1./3.)
        np.testing.assert_allclose(scores.confidence,0.,atol=1e-14)

    def test_factorization_and_outside_period_mask(self):
        scores=factor_scores(np.array([.2,.8,.5]),np.array([.9,.1,.4]),np.array([True,True,False]),
            state_support=np.ones(3),team_support=np.ones(3),team_source=np.ones(3))
        np.testing.assert_allclose(scores.probabilities[:2],[[.72,.08,.2],[.02,.18,.8]])
        self.assertTrue(np.isnan(scores.probabilities[2]).all())
        self.assertEqual(scores.labels()[2],'X')

    def test_invalid_probabilities_and_broken_factorization_are_rejected(self):
        with self.assertRaises(ValueError):
            factor_scores(np.array([1.2]),np.array([.5]),np.array([True]),state_support=np.ones(1),team_support=np.ones(1),team_source=np.ones(1))
        scores=rule_scores(fixture())
        altered=scores.probabilities.copy();altered[:,0],altered[:,1]=altered[:,1].copy(),altered[:,0].copy()
        with self.assertRaises(ValueError): replace(scores,probabilities=altered).validate()

    def test_collective_head_handles_missing_ball_without_imputing_geometry(self):
        matrix=fixture();model,_,_=small_model(matrix)
        missing=fixture(missing_ball=True)
        result=model_scores(missing,model)
        self.assertTrue((result.team_source==2).all())
        self.assertTrue(np.isnan(missing.column('H_nearest_1_m')).all())
        self.assertTrue((result.team_support>0).all())

    def test_absent_team_is_unavailable_not_certain_opponent(self):
        matrix=fixture();model,_,_=small_model(matrix)
        result=model_scores(change(matrix,A_observed_n=0.),model)
        np.testing.assert_allclose(result.p_home_given_alive,.5)
        self.assertTrue((result.team_source==0).all())

    def test_learned_state_head_is_separate_from_team_control(self):
        matrix=fixture();model,_,_=small_model(matrix)
        changed=change(matrix,H_distance_kernel=0.,A_distance_kernel=1.,tag_H_minus_A=-10.)
        np.testing.assert_array_equal(model_scores(matrix,model).p_dead,model_scores(changed,model).p_dead)

    def test_team_exchange_swaps_probabilities_and_preserves_dead_score(self):
        matrix=fixture();model,_,_=small_model(matrix)
        swapped=replace(matrix,values=matrix.values.copy())
        for name in matrix.names:
            if name.startswith('H_') and 'A_'+name[2:] in matrix.names:
                swapped.values[:,matrix.names.index(name)]=matrix.column('A_'+name[2:])
                swapped.values[:,matrix.names.index('A_'+name[2:])]=matrix.column(name)
        first,second=model_scores(matrix,model),model_scores(swapped,model)
        np.testing.assert_allclose(first.probabilities[:,0],second.probabilities[:,1],atol=1e-12)
        np.testing.assert_allclose(first.p_dead,second.p_dead,atol=1e-12)

    def test_inference_does_not_open_target_loaders(self):
        matrix=fixture();model,_,_=small_model(matrix)
        with patch('src.utils.external_data.load_targets',side_effect=AssertionError('No target read')):
            model_scores(matrix,model);rule_scores(matrix)


class ControlMemoryTests(unittest.TestCase):
    def test_hold_decays_and_resets_between_periods(self):
        direct=np.array([3.,np.nan,np.nan,np.nan,np.nan, -3., np.nan])
        period=np.array([1,1,1,2,2,2,2])
        result,held,age=hold_control(direct,np.full(7,.1),period,10,decay_s=2.)
        self.assertAlmostEqual(result[1],3*np.exp(-.05))
        self.assertTrue(np.isnan(result[3:5]).all())
        self.assertLess(result[6],0);self.assertTrue(held[6]);self.assertEqual(age[6],.1)

    def test_contradictory_new_control_overrides_old_team(self):
        result,held,_=hold_control(np.array([3.,np.nan,-3.,np.nan]),np.full(4,.1),np.ones(4),25)
        self.assertGreater(result[1],0);self.assertLess(result[3],0)
        self.assertFalse(held[2])

    def test_strong_dead_evidence_and_weak_control_clear_memory(self):
        result,_,_=hold_control(np.array([3.,np.nan,np.nan]),np.array([.1,.9,.1]),np.ones(3),25)
        self.assertTrue(np.isnan(result[1:]).all())
        result,_,_=hold_control(np.array([3.,.1,np.nan]),np.full(3,.1),np.ones(3),25)
        self.assertTrue(np.isnan(result[2]))

    def test_invalid_memory_settings_fail(self):
        with self.assertRaises(ValueError): hold_control(np.array([1.]),np.array([.1]),np.ones(1),25,decay_s=0.)


class LogisticAndSplitTests(unittest.TestCase):
    def test_regularized_logistic_learns_synthetic_signal_and_converges(self):
        rng=np.random.default_rng(7)
        x=rng.normal(size=(1000,3)); y=(x[:,0]+.25*x[:,1]>0).astype(float)
        block=FeatureBlock(x,('x','y','z'))
        model=fit_logistic(block,y)
        self.assertTrue(model['converged']);self.assertLess(model['gradient_max'],1e-6)
        self.assertGreater(np.mean((predict_logistic(block,model)>.5)==y),.96)

    def test_preprocessing_is_training_only_and_missing_is_explicit(self):
        block=FeatureBlock(np.array([[1.,np.nan],[2.,np.nan],[3.,np.nan],[4.,np.nan]]),('x','empty'))
        model=fit_logistic(block,np.array([0.,0.,1.,1.]))
        self.assertEqual(model['location'],[2.5,0.])
        transformed=transform(FeatureBlock(np.array([[np.nan,1000.]]),block.names),model)
        self.assertEqual(transformed[0,-2],1.)
        self.assertEqual(model['location'],[2.5,0.])

    def test_team_logistic_has_no_intercept_and_is_exactly_odd(self):
        x=np.linspace(-2,2,200)[:,None]
        block=FeatureBlock(x,('difference',),True)
        model=fit_logistic(block,(x[:,0]>0).astype(float))
        p=predict_logistic(block,model)
        reversed_p=predict_logistic(FeatureBlock(-x,block.names,True),model)
        np.testing.assert_allclose(p+reversed_p,1.,atol=1e-14)
        self.assertEqual(len(model['coefficients']),1)

    def test_logistic_json_roundtrip_and_schema_failure(self):
        block=FeatureBlock(np.array([[-1.],[1.],[-2.],[2.]]),('x',))
        model=fit_logistic(block,np.array([0.,1.,0.,1.]))
        restored=json.loads(json.dumps(model))
        np.testing.assert_array_equal(predict_logistic(block,model),predict_logistic(block,restored))
        with self.assertRaises(ValueError): predict_logistic(FeatureBlock(block.values,('bad',)),model)

    def test_invalid_labels_infinity_or_constant_target_fail(self):
        block=FeatureBlock(np.array([[-1.],[1.]]),('x',))
        for y in (np.array([0.,2.]),np.array([1.,1.])):
            with self.assertRaises(ValueError): fit_logistic(block,y)
        with self.assertRaises(ValueError): fit_logistic(FeatureBlock(np.array([[np.inf],[1.]]),('x',)),np.array([0.,1.]))

    def test_training_samples_exclude_unknowns_and_preserve_match_boundaries(self):
        matrix=fixture();labels=np.resize(np.array(['H','A','D','X']),90)
        targets=ExternalTargets(labels,matrix.frame_ids,matrix.period_ids)
        batch=training_examples('J03WMX','synthetic',matrix,targets,maximum_rows=20)
        self.assertEqual(len(batch.labels),20);self.assertNotIn('X',batch.labels)
        self.assertTrue((np.diff(batch.frame_ids)>0).all())

    def test_validation_and_final_test_cannot_be_training_examples(self):
        matrix=fixture();targets=ExternalTargets(np.full(90,'H'),matrix.frame_ids,matrix.period_ids)
        for match in ('J03WPY','J03WR9'):
            with self.assertRaises(PermissionError): training_examples(match,'clean',matrix,targets,maximum_rows=20)
        _,batch,opt=small_model(matrix)
        with self.assertRaises(PermissionError): fit_factorized([replace(batch,match_id='J03WPY')],opt)

    def test_alignment_mismatch_and_mixed_target_dictionary_are_rejected(self):
        matrix=fixture();targets=ExternalTargets(np.full(90,'H'),matrix.frame_ids+1,matrix.period_ids)
        with self.assertRaises(ValueError): aligned_labels(matrix,targets)
        with self.assertRaises(TypeError): aligned_labels(matrix,{'labels':np.full(90,'H')})

    def test_unknown_targets_cannot_be_smuggled_into_fit(self):
        _,batch,opt=small_model(fixture())
        with self.assertRaises(ValueError): fit_factorized([replace(batch,labels=np.full(90,'X'))],opt)

    def test_frozen_config_retains_four_train_two_validation_and_no_search(self):
        opt=options()
        self.assertEqual(len(opt['train_matches']),4);self.assertEqual(len(opt['validation_matches']),2)
        self.assertNotIn('J03WR9',opt['train_matches']+opt['validation_matches'])

    def test_validation_selector_refuses_train_or_test_before_loading_model(self):
        with patch('src.observation_pipeline.load_model',side_effect=AssertionError('Must not load')):
            for match in ('J03WMX','J03WR9'):
                with self.assertRaises(PermissionError): validate_external(match_id=match)


class ArchiveAndMetricTests(unittest.TestCase):
    def test_observation_archive_roundtrip_and_signature_tampering(self):
        matrix=fixture();scores=rule_scores(matrix)
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            save_scores(scores,matrix,folder,{'synthetic':True})
            loaded,frames,periods,manifest=load_scores(folder)
            np.testing.assert_allclose(scores.probabilities,loaded.probabilities,atol=1e-7)
            np.testing.assert_array_equal(frames,matrix.frame_ids)
            self.assertEqual(manifest['class_order'],['H','A','D'])
            with (folder/'scores.npz').open('ab') as file: file.write(b'changed')
            with self.assertRaises(ValueError): load_scores(folder)

    def test_probability_metrics_match_uniform_three_class_reference(self):
        matrix=fixture()
        unknown=replace(matrix,values=np.full_like(matrix.values,np.nan),valid=np.zeros_like(matrix.valid))
        scores=rule_scores(unknown)
        report=probability_metrics(np.resize(np.array(['H','A','D']),90),scores)
        self.assertAlmostEqual(report['log_loss'],np.log(3.))
        self.assertAlmostEqual(report['brier_sum'],2./3.)
        self.assertEqual(report['abstention_frames'],90)
