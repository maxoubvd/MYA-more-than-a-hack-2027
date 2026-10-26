"""Milestone 3: analytical motion, missingness, permutations and label isolation."""
from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from src.features.team_assignment import FeatureInputs,from_external,from_tactical,attack_directions_from_xml
from src.imputation.gap_analyzer import gap_features
from src.preprocessing.player_denoising import track_kinematics,duplicate_weights
from src.preprocessing.smart_tagging import tagging_features
from src.features.context_features import temporal_context
from src.features.physical import contact_window_distance
from src.features.collective_dynamics import collective_features
from src.features.relative_kinematics import relative_features
from src.features.activity import fit_context_model,low_activity_score
from src.features.builder import build_features
from src.build_features import save_matrix,load_matrix,build_source,run as run_feature_build
from src.utils.external_data import ExternalInputs,ExternalTargets


def fixture(n=30):
    players = np.broadcast_to(np.array([[.3,.4],[.4,.6],[.6,.4],[.7,.6]],dtype=np.float32),(n,4,2)).copy()
    ball = np.broadcast_to(np.array([.35,.5],dtype=np.float32),(n,2)).copy()
    return FeatureInputs(players,ball,np.array(['H','H','A','A']),np.arange(n,dtype=np.int32),np.ones(n,dtype=np.int8),25.,(100.,60.))


class GapAndKinematicsTests(unittest.TestCase):
    def test_contact_window_retains_uncertainty_without_crossing_fragments(self):
        distance=np.array([5.,4.,3.,1.,np.nan,.1,2.,3.])
        links=np.array([False,True,True,True,False,False,True,True])
        result=contact_window_distance(distance,links,2)
        np.testing.assert_allclose(result,[3.,1.,1.,1.,np.nan,.1,.1,.1],equal_nan=True)
        with self.assertRaises(ValueError): contact_window_distance(distance,links,2.5)

    def test_gaps_at_period_edges_and_all_missing_are_censored(self):
        observed=np.array([False,True,False,False,False,False,True,False])
        periods=np.array([1,1,1,1,2,2,2,2])
        features,last,runs=gap_features(observed,periods,25)
        self.assertEqual([r['length_frames'] for r in runs],[1,2,2,1])
        self.assertTrue(np.isnan(features['since_observation_s'][0]))
        self.assertTrue(np.isnan(features['since_observation_s'][4]))
        self.assertTrue(np.isnan(features['until_observation_s'][3]))
        self.assertEqual(last[4],-1)
        self.assertEqual(features['gap_left_censored'][4],1)
        self.assertEqual(features['gap_right_censored'][3],1)

    def test_fully_missing_period_has_no_previous_or_next_observation(self):
        features,last,runs=gap_features(np.zeros(5,dtype=bool),np.ones(5,dtype=int),25)
        np.testing.assert_allclose(features['gap_duration_s'],.2)
        self.assertTrue(np.isnan(features['since_observation_s']).all())
        self.assertTrue(np.isnan(features['until_observation_s']).all())
        self.assertTrue((last==-1).all())

    def test_constant_motion_has_correct_units_and_does_not_modify_raw(self):
        t=np.arange(12,dtype=np.float32)
        points=np.column_stack((5+t*.125,7+t*.25))
        original=points.copy()
        k=track_kinematics(points,np.ones(12),np.arange(12),25,max_link_speed_mps=20)
        np.testing.assert_allclose(k.velocity[1:-1],np.tile([3.125,6.25],(10,1)),atol=1e-5)
        np.testing.assert_allclose(k.acceleration[1:-1],0,atol=1e-4)
        np.testing.assert_array_equal(points,original)
        self.assertTrue(np.isnan(k.velocity[[0,-1]]).all())

    def test_missing_gap_large_jump_and_half_boundary_break_derivatives(self):
        points=np.column_stack((np.arange(12,dtype=np.float32)*.1,np.zeros(12)))
        points[3]=np.nan;points[7:]+=20
        periods=np.r_[np.ones(9),np.full(3,2)]
        k=track_kinematics(points,periods,np.arange(12),25,max_link_speed_mps=20)
        for row in (2,3,4,6,7,8,9): self.assertTrue(np.isnan(k.velocity[row]).all())
        self.assertTrue(k.fragment_start[4]);self.assertTrue(k.fragment_start[7]);self.assertTrue(k.fragment_start[9])
        self.assertTrue(np.isnan(k.positions[3]).all())

    def test_temporal_frame_id_gap_breaks_links(self):
        points=np.zeros((6,2))
        k=track_kinematics(points,np.ones(6),np.array([0,1,2,10,11,12]),25,max_link_speed_mps=20)
        self.assertFalse(k.link_valid[3]);self.assertTrue(np.isnan(k.velocity[2:4]).all())

    def test_duplicate_weights_are_symmetric_and_do_not_remove_positions(self):
        players=np.array([[[1.,1.],[1.,1.],[3.,1.],[9.,1.]]])
        weights,duplicate=duplicate_weights(players,np.array(['H','H','H','A']))
        np.testing.assert_allclose(weights,[[.5,.5,1,1]])
        np.testing.assert_array_equal(duplicate,[[True,True,False,False]])
        features=collective_features(players,np.zeros_like(players),np.array(['H','H','H','A']),weights,duplicate,period_ids=np.array([1]),pitch_dims=(100,60))
        self.assertEqual(features['H_centroid_x_m'][0],2)
        self.assertEqual(features['H_effective_n'][0],2)

    def test_past_future_context_excludes_current_and_never_crosses_half(self):
        values=np.array([1.,2.,100.,10.,20.,30.]);periods=np.array([1,1,1,2,2,2])
        result=temporal_context(values,periods,2)
        self.assertTrue(np.isnan(result['past_mean'][3]))
        self.assertTrue(np.isnan(result['future_mean'][2]))
        self.assertEqual(result['past_mean'][2],1.5)
        self.assertEqual(result['future_mean'][3],25)
        self.assertEqual(result['future_mean'][0],51)


class TeamAndTacticalTests(unittest.TestCase):
    def test_relative_velocity_uses_actual_nearest_track_not_distance_rank_derivative(self):
        distances=np.array([[1.,2.],[2.,1.]])
        delta=np.stack((distances,np.zeros_like(distances)),axis=-1)
        velocity=np.array([[[10.,0.],[20.,0.]],[[10.,0.],[20.,0.]]])
        result=relative_features(distances,delta,velocity,np.zeros((2,2)),np.array(['H','H']))
        np.testing.assert_allclose(result['H_nearest_relative_speed_mps'],[10,20])
        np.testing.assert_allclose(result['H_nearest_closing_speed_mps'],[-10,-20])

    def test_closing_speed_positive_when_approaching(self):
        result=relative_features(np.array([[10.]]),np.array([[[10.,0.]]]),np.zeros((1,1,2)),np.array([[1.,0.]]),np.array(['H']))
        self.assertEqual(result['H_nearest_closing_speed_mps'][0],1)

    def test_tag_polarity_conflict_na_and_half_open_boundaries(self):
        events=pd.DataFrame([
         {'start_frame':1,'end_frame':4,'code':'build up','team_code':'H','phase_type':None},
         {'start_frame':2,'end_frame':3,'code':'DEFENSIVE TRANSITION','team_code':'H','phase_type':None},
         {'start_frame':3,'end_frame':5,'code':'SET PIECES','team_code':None,'phase_type':'Throw-in'},
         {'start_frame':0,'end_frame':1,'code':'FUTURE CODE','team_code':'A','phase_type':None}])
        result=tagging_features(events,np.arange(6),np.ones(6),25)
        self.assertEqual(result['tag_H_support_n'][1],1)
        self.assertEqual(result['tag_A_support_n'][2],1)
        self.assertEqual(result['tag_conflict'][2],1)
        self.assertEqual(result['tag_H_support_n'][4],0)
        self.assertEqual(result['restart_unknown_team'][3],1)
        self.assertEqual(result['tag_H_support_n'][4]+result['tag_A_support_n'][4],0)
        self.assertEqual(result['tag_unknown_code_n'][0],1)

    def test_optional_tags_absent_vs_empty_are_not_conflated(self):
        missing=tagging_features(None,np.arange(4),np.ones(4),25)
        empty=tagging_features(pd.DataFrame(),np.arange(4),np.ones(4),25)
        self.assertTrue(np.isnan(missing['tag_active_n']).all())
        self.assertTrue((empty['tag_active_n']==0).all())

    def test_restart_boundaries_do_not_cross_halftime(self):
        tags=pd.DataFrame([{'start_frame':0,'end_frame':2,'code':'SET PIECES','team_code':'H'}])
        result=tagging_features(tags,np.arange(8),np.array([1,1,1,1,2,2,2,2]),25)
        self.assertTrue(np.isnan(result['restart_since_last_end_s'][4:]).all())

    def test_attack_axis_projects_both_halves_without_altering_raw_geometry(self):
        inputs=fixture(12)
        inputs.period_ids[6:]=2
        inputs.players_xy[:,:,0]+=np.arange(12)[:,None]*.001
        matrix=build_features(inputs,attack_directions={(1,'H'):1,(2,'H'):-1})
        self.assertGreater(matrix.column('H_attack_velocity_mps')[3],0)
        self.assertLess(matrix.column('H_attack_velocity_mps')[8],0)
        self.assertGreater(matrix.column('H_mean_vx_mps')[8],0)
        self.assertTrue(np.isnan(matrix.column('A_attack_velocity_mps')).all())

    def test_attack_xml_uses_provider_metadata_not_fixed_team_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'meta.xml'
            path.write_text('<root><Team id="arbitrary"><Name>Barcelona</Name><ProviderTeamsParameters>'
              '<ProviderParameter><Name>attack_direction_first_half</Name><Value>right_to_left</Value></ProviderParameter>'
              '</ProviderTeamsParameters></Team></root>')
            self.assertEqual(attack_directions_from_xml(path),{(1,'H'):-1.,(2,'H'):1.})


class MatrixAndIsolationTests(unittest.TestCase):
    def test_feature_masks_units_source_independent_schema_and_no_input_mutation(self):
        inputs=fixture();before=inputs.players_xy.copy()
        matrix=build_features(inputs)
        self.assertEqual(matrix.values.shape,(30,len(matrix.names)))
        np.testing.assert_array_equal(matrix.valid,np.isfinite(matrix.values))
        self.assertFalse(np.isinf(matrix.values).any())
        self.assertEqual(next(f['unit'] for f in matrix.schema if f['name']=='H_nearest_1_m'),'m')
        self.assertEqual(next(f['unit'] for f in matrix.schema if f['name']=='ball_speed_mps'),'m/s')
        np.testing.assert_array_equal(inputs.players_xy,before)
        self.assertTrue(np.isnan(matrix.column('tag_active_n')).all())
        self.assertTrue(np.isnan(matrix.column('collective_low_activity_score')).all())

    def test_team_slot_permutations_including_exact_distance_ties_leave_features_equal(self):
        inputs=fixture(20)
        inputs.players_xy[:,:,0]+=np.arange(20)[:,None]*np.array([.001,-.001,.002,-.002])
        inputs.players_xy[10,0]=inputs.players_xy[10,1]
        reference=build_features(inputs)
        order=np.array([3,1,2,0])
        permuted=replace(inputs,players_xy=inputs.players_xy[:,order],team_mapping=inputs.team_mapping[order])
        actual=build_features(permuted)
        np.testing.assert_allclose(reference.values,actual.values,atol=1e-5,equal_nan=True)

    def test_ball_missing_does_not_become_dead_or_zero_geometry(self):
        inputs=fixture();inputs.ball_xy[4:20]=np.nan
        matrix=build_features(inputs)
        self.assertTrue(np.isnan(matrix.column('H_nearest_1_m')[4:20]).all())
        self.assertTrue(np.isfinite(matrix.column('H_centroid_x_m')[4:20]).all())
        self.assertNotIn('label',matrix.names)
        self.assertFalse(matrix.diagnostics['labels_used'])
        self.assertTrue((matrix.column('ball_observed')[4:20]==0).all())

    def test_entire_team_absent_positions_remain_missing_but_counts_zero(self):
        inputs=fixture();inputs.players_xy[:,2:]=np.nan
        matrix=build_features(inputs)
        self.assertTrue((matrix.column('A_observed_n')==0).all())
        self.assertTrue(np.isnan(matrix.column('A_centroid_x_m')).all())
        self.assertTrue(np.isnan(matrix.column('nearest_distance_A_minus_H_m')).all())

    def test_non_evaluated_rows_are_masked_without_erasing_period_metadata(self):
        inputs=fixture();inputs.period_ids[:3]=0;inputs.period_ids[-3:]=0
        matrix=build_features(inputs)
        self.assertTrue(np.isnan(matrix.values[:3]).all())
        self.assertFalse(matrix.valid[-3:].any())
        np.testing.assert_array_equal(matrix.period_ids,inputs.period_ids)

    def test_boundary_exit_before_gap_uses_backward_velocity_without_filling_ball(self):
        inputs=fixture(12)
        inputs.ball_xy[:4,0]=[.04,.03,.02,.01]
        inputs.ball_xy[4:]=np.nan
        matrix=build_features(inputs)
        self.assertEqual(matrix.column('ball_gap_after_boundary_exit')[4],1)
        self.assertTrue(np.isnan(matrix.column('ball_speed_mps')[4]))
        self.assertGreater(matrix.column('ball_last_seen_outward_speed_mps')[4],0)

    def test_target_containers_and_mixed_dicts_are_rejected(self):
        targets=ExternalTargets(np.array(['H']),np.array([0]),np.array([1]))
        with self.assertRaises(TypeError): from_external(targets)
        with self.assertRaises(TypeError): build_features({'players':fixture().players_xy,'labels':np.array(['H'])})

    def test_external_adapter_cannot_read_or_embed_targets(self):
        i=fixture()
        raw=ExternalInputs(i.players_xy,i.ball_xy,np.isfinite(i.players_xy).all(axis=-1),np.isfinite(i.ball_xy).all(axis=-1),i.team_mapping,i.frame_ids,i.period_ids,i.fps,i.pitch_dims)
        with patch('src.utils.external_data.load_targets',side_effect=AssertionError('No target reads')):
            matrix=build_features(from_external(raw))
        self.assertNotIn('BallStatus',matrix.names);self.assertNotIn('BallPossession',matrix.names)

    def test_context_fit_is_training_observation_only_and_not_dead_probability(self):
        speeds=np.r_[np.full(50,.1),np.full(50,4.)]
        model=fit_context_model(speeds,np.arange(100),match_id='J03WMX')
        self.assertFalse(model['labels_used'])
        result=low_activity_score(np.array([.1,4.,np.nan]),model)
        self.assertGreater(result[0],result[1]);self.assertTrue(np.isnan(result[2]))
        with self.assertRaises(PermissionError): fit_context_model(speeds,np.arange(100),match_id='J03WPY')
        with self.assertRaises(PermissionError): fit_context_model(speeds,np.arange(100),match_id='J03WR9')

    def test_archive_roundtrip_and_corruption_detection(self):
        matrix=build_features(fixture())
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            save_matrix(matrix,folder,{'synthetic':True})
            arrays,manifest,schema=load_matrix(folder)
            np.testing.assert_array_equal(matrix.values,arrays['values'])
            self.assertEqual(schema['features'],matrix.schema)
            (folder/'schema.json').write_text('{}')
            with self.assertRaises(ValueError): load_matrix(folder)

    def test_full_rebuild_replaces_stale_context_but_tactical_only_refuses_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'features').mkdir();(root/'configs').mkdir()
            (root/'features/context_model.json').write_text('{"feature_version":"obsolete"}')
            (root/'configs/features.json').write_text('{}')
            model={'version':'new'}
            result={'source':'external','shape':[2,116],'context_model':model,'matrix':None}
            with patch('src.build_features.config.CACHE_DIR',root), patch('src.build_features.config.MYA_DIR',root), patch('src.build_features.build_source',return_value=result) as builder:
                run_feature_build('all')
                self.assertEqual(builder.call_count,2)
                self.assertTrue(builder.call_args_list[0].kwargs['fit_context'])
                self.assertEqual(builder.call_args_list[1].kwargs['context_model'],model)
                with self.assertRaises(ValueError): run_feature_build('tactical')

    def test_invalid_timeline_inf_coordinates_and_reappearing_period_fail(self):
        inputs=fixture()
        inputs.frame_ids[4]=99
        with self.assertRaises(ValueError): build_features(inputs)
        inputs=fixture();inputs.players_xy[0,0,0]=np.inf
        with self.assertRaises(ValueError): build_features(inputs)
        inputs=fixture();inputs.period_ids[4:8]=2
        with self.assertRaises(ValueError): build_features(inputs)


if __name__=='__main__': unittest.main()
