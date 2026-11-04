"""J10 bounded trajectories, geometric equivalence and state/fold isolation."""
import unittest
from dataclasses import replace
from unittest.mock import patch
import numpy as np
from src.bonus import j10
from src.bonus.ball_bridges import impute_ball
from src.bonus.geometry_layer import Geometry,local_control,append_control,bridge_scores,control_scores
from src.bonus.contracts import PositionLayers
from src.features.builder import build_features
from src.features.team_assignment import from_external
from src.models.dataset import FeatureBlock,observation_design
from src.models.tabular import fit_logistic
from src.models.observations import model_scores
from src.utils.external_data import ExternalInputs
from test_observations import small_model


def fixture(n=110):
    t=np.arange(n,dtype=np.float32)/25
    ball=np.column_stack((.3+.015*t,np.full(n,.4))).astype(np.float32)
    players=np.tile(np.array([[.2,.4],[.3,.6],[.7,.4],[.8,.6]],np.float32),(n,1,1))
    players[:,:,0]+=t[:,None]*.01
    return ExternalInputs(players,ball,np.isfinite(players).all(axis=-1),np.ones(n,bool),
                          np.array(['H','H','A','A']),np.arange(n),np.ones(n,int),25.,(105.,68.))


def gap(x,a=40,b=45):
    ball=x.ball_xy_normalized.copy();ball[a:b]=np.nan
    return replace(x,ball_xy_normalized=ball,ball_observed=np.isfinite(ball).all(axis=1))


def build(x):return build_features(from_external(x))


class BridgeTests(unittest.TestCase):
    def test_line_reconstructed_by_both_methods_without_overwriting_raw(self):
        truth=fixture();x=gap(truth);original=x.ball_xy_normalized.copy()
        for method in ('linear','kalman_rts'):
            out=impute_ball(x,method,5,j10.OPTIONS['bridge'])
            np.testing.assert_allclose(out.layers.imputed_xy[40:45],truth.ball_xy_normalized[40:45],atol=2e-6)
            np.testing.assert_array_equal(out.layers.observed_xy,original)
            self.assertEqual(out.filled.sum(),5)
            self.assertTrue((out.layers.uncertainty_m[out.filled]>0).all())
            self.assertTrue(np.isnan(out.layers.imputed_xy[~out.filled]).all())
            self.assertFalse(np.shares_memory(out.layers.observed_xy,x.ball_xy_normalized))
        np.testing.assert_array_equal(x.ball_xy_normalized,original)

    def test_acceleration_produces_distinct_finite_paths(self):
        x=fixture();t=np.arange(len(x.frame_ids),dtype=np.float32)/25
        ball=x.ball_xy_normalized.copy();ball[:,0]=.2+.003*t*t
        truth=replace(x,ball_xy_normalized=ball);x=gap(truth,40,65)
        a=impute_ball(x,'linear',25,j10.OPTIONS['bridge']);b=impute_ball(x,'kalman_rts',25,j10.OPTIONS['bridge'])
        self.assertEqual(a.filled.sum(),25);self.assertEqual(b.filled.sum(),25)
        self.assertGreater(np.max(np.abs(a.layers.imputed_xy[a.filled]-b.layers.imputed_xy[b.filled])),1e-7)
        self.assertFalse(np.isinf(b.layers.imputed_xy).any())

    def test_cap_is_in_missing_frames_and_long_holes_stay_empty(self):
        x=gap(fixture(),40,51)
        for method in ('linear','kalman_rts'):
            self.assertEqual(impute_ball(x,method,10,j10.OPTIONS['bridge']).filled.sum(),0)
            self.assertEqual(impute_ball(x,method,25,j10.OPTIONS['bridge']).filled.sum(),11)
        x=gap(fixture(),40,66)
        self.assertEqual(impute_ball(x,'linear',25,j10.OPTIONS['bridge']).filled.sum(),0)

    def test_censored_or_missing_support_points_never_extrapolate(self):
        for a,b in ((0,5),(105,110),(1,6)):
            x=gap(fixture(),a,b)
            for method in ('linear','kalman_rts'):
                self.assertFalse(impute_ball(x,method,5,j10.OPTIONS['bridge']).filled.any())
        x=gap(gap(fixture(),40,45),46,47)
        self.assertFalse(impute_ball(x,'linear',5,j10.OPTIONS['bridge']).filled.any())

    def test_period_boundary_and_inactive_frames_are_not_bridged(self):
        x=fixture();periods=np.r_[np.ones(45,int),np.full(65,2)]
        x=replace(gap(x,42,47),period_ids=periods)
        self.assertFalse(impute_ball(x,'kalman_rts',25,j10.OPTIONS['bridge']).filled.any())
        periods=np.r_[np.ones(40,int),np.zeros(10,int),np.full(60,2)]
        x=replace(gap(fixture(),42,47),period_ids=periods)
        self.assertFalse(impute_ball(x,'linear',25,j10.OPTIONS['bridge']).filled.any())

    def test_outlier_terminal_or_impossible_motion_is_rejected(self):
        x=gap(fixture());ball=x.ball_xy_normalized.copy();ball[45:]=.99
        x=replace(x,ball_xy_normalized=ball)
        for method in ('linear','kalman_rts'):
            self.assertFalse(impute_ball(x,method,5,j10.OPTIONS['bridge']).filled.any())

    def test_registered_cadence_and_methods_only(self):
        with self.assertRaises(ValueError):impute_ball(replace(fixture(),fps=10.),'linear',5,j10.OPTIONS['bridge'])
        with self.assertRaises(ValueError):impute_ball(fixture(),'linear',100,j10.OPTIONS['bridge'])
        with self.assertRaises(ValueError):impute_ball(fixture(),'extrapolate',5,j10.OPTIONS['bridge'])


class GeometryTests(unittest.TestCase):
    def test_imputed_team_design_matches_frozen_builder_exactly(self):
        x=gap(fixture());matrix=build(x);geom=Geometry(x,matrix,j10.OPTIONS)
        bridge=impute_ball(x,'linear',5,j10.OPTIONS['bridge'])
        rows,block,_=geom.imputed_block(bridge)
        merged=x.ball_xy_normalized.copy();merged[bridge.filled]=bridge.layers.imputed_xy[bridge.filled]
        inputs=replace(x,ball_xy_normalized=merged,ball_observed=np.isfinite(merged).all(axis=1))
        expected=observation_design(build(inputs)).visible_team
        self.assertEqual(block.names,expected.names)
        np.testing.assert_allclose(block.values,expected.values[rows],rtol=0,atol=0,equal_nan=True)

    def test_state_and_unmodified_scores_remain_bit_identical(self):
        x=gap(fixture());matrix=build(x);model,_,_=small_model(matrix)
        base=model_scores(matrix,model);geom=Geometry(x,matrix,j10.OPTIONS)
        bridge=impute_ball(x,'linear',5,j10.OPTIONS['bridge'])
        out=bridge_scores(geom,base,bridge,model['heads']['visible_team'])
        np.testing.assert_array_equal(out.p_dead,base.p_dead)
        np.testing.assert_array_equal(out.state_support,base.state_support)
        np.testing.assert_array_equal(out.probabilities[~bridge.filled],base.probabilities[~bridge.filled])
        np.testing.assert_array_equal(x.ball_observed,~bridge.filled)
        self.assertTrue((out.team_source[bridge.filled]==4).all())

    def test_missing_player_team_does_not_create_control(self):
        x=gap(fixture());players=x.players_xy_normalized.copy();players[:,2:]=np.nan
        x=replace(x,players_xy_normalized=players,players_observed=np.isfinite(players).all(axis=-1))
        matrix=build(x);geom=Geometry(x,matrix,j10.OPTIONS)
        self.assertTrue(np.isnan(geom.control).all())
        full=build(gap(fixture()));model,_,_=small_model(full);base=model_scores(matrix,model)
        bridge=impute_ball(x,'linear',5,j10.OPTIONS['bridge'])
        self.assertIs(bridge_scores(geom,base,bridge,model['heads']['visible_team']),base)

    def test_local_control_is_permutation_and_duplicate_invariant_and_team_odd(self):
        x=fixture();g=Geometry(x,build(x),j10.OPTIONS)
        a=g.control
        order=np.array([3,1,0,2])
        b=local_control(g.players[:,order],g.velocity[:,order],g.ball,x.team_mapping[order],j10.OPTIONS['control'])
        np.testing.assert_array_equal(a,b)
        players=np.concatenate([g.players,g.players[:,:1]],axis=1);v=np.concatenate([g.velocity,g.velocity[:,:1]],axis=1)
        c=local_control(players,v,g.ball,np.concatenate([x.team_mapping,np.array(['H'])]),j10.OPTIONS['control'])
        np.testing.assert_array_equal(a,c)
        swapped=np.where(x.team_mapping=='H','A','H')
        np.testing.assert_allclose(a,-local_control(g.players,g.velocity,g.ball,swapped,j10.OPTIONS['control']))

    def test_control_head_is_team_odd_and_never_changes_D(self):
        x=fixture();matrix=build(x);geom=Geometry(x,matrix,j10.OPTIONS);model,_,_=small_model(matrix)
        block=append_control(geom.design.visible_team,geom.control)
        labels=np.arange(len(x.frame_ids))%2==0
        head=fit_logistic(block,labels)
        base=model_scores(matrix,model);out=control_scores(geom,base,head)
        self.assertTrue(head['symmetric_team'])
        np.testing.assert_array_equal(out.p_dead,base.p_dead)
        np.testing.assert_array_equal(out.probabilities[:,2],base.probabilities[:,2])

    def test_no_missing_ball_is_a_noop_for_imputation(self):
        x=fixture();matrix=build(x);geom=Geometry(x,matrix,j10.OPTIONS);model,_,_=small_model(matrix)
        base=model_scores(matrix,model);bridge=impute_ball(x,'linear',25,j10.OPTIONS['bridge'])
        self.assertIs(bridge_scores(geom,base,bridge,model['heads']['visible_team']),base)


class ProtocolTests(unittest.TestCase):
    def test_exact_eight_ablation_grid_and_paired_control(self):
        self.assertEqual(len(j10.VARIANTS),8)
        self.assertEqual(len({v['id'] for v in j10.VARIANTS}),8)
        self.assertEqual([(v['method'],v['maximum_frames']) for v in j10.VARIANTS[:6]],
                         [(m,n) for m in ('linear','kalman_rts') for n in (5,10,25)])
        self.assertIsNone(j10.VARIANTS[6]['method']);self.assertEqual(j10.VARIANTS[7]['method'],'linear')
        self.assertEqual(j10.VARIANTS[7]['maximum_frames'],25)

    def test_forbidden_outer_match_rejected_before_reference_read(self):
        with patch.object(j10,'read_json',side_effect=AssertionError('Forbidden data read')) as read:
            for match in ('J03WPY','J03WQQ','J03WR9','BAR-ATH'):
                with self.assertRaises(PermissionError):j10.reference(match)
            read.assert_not_called()

    def test_incomplete_prediction_snapshot_prevents_targets(self):
        with patch.object(j10,'read_json',return_value={'experiment_id':'x','predictions':[]}),\
             patch.object(j10.j9,'target',side_effect=AssertionError('Premature label access')) as read:
            with self.assertRaises(ValueError):j10.score('J03WMX',{'experiment_id':'x'})
            read.assert_not_called()

    def test_hidden_position_accuracy_uses_only_removed_points(self):
        truth=np.zeros((5,2));imputed=np.ones((5,2));removed=np.array([True,False,False,False,False])
        out=j10.position_accuracy(imputed,np.ones(5),removed,truth,(1.,1.),np.ones(5,int))
        self.assertEqual(out['n_imputed_hidden'],1);self.assertAlmostEqual(out['rmse_m'],np.sqrt(2))

if __name__=='__main__':unittest.main()
