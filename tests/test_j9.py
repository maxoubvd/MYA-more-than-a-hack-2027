"""J9 weighted estimation, calibration, equivariance and fold leakage guards."""
import unittest
from dataclasses import replace
from unittest.mock import patch
import numpy as np
from src.bonus import j9,j9_models as m
from src.bonus.j9_logistic import fit_weighted_logistic
from src.models.dataset import FeatureBlock
from src.models.tabular import fit_logistic,predict_logistic,sigmoid
from src.utils.external_data import ExternalTargets
from test_observations import fixture,change


class J9Models(unittest.TestCase):
    def test_plain_solver_matches_C0(self):
        rng=np.random.default_rng(5); x=rng.normal(size=(1000,3)); x[:15,0]=np.nan
        block=FeatureBlock(x,('a','b','c')); y=rng.random(1000)<sigmoid(np.nan_to_num(x[:,0]))
        a=fit_logistic(block,y); b=fit_weighted_logistic(block,y)
        np.testing.assert_allclose(a['coefficients'],b['coefficients'],atol=1e-12)

    def test_class_weight_is_training_frequency_only(self):
        x=FeatureBlock(np.zeros((100,1)),('constant',)); y=np.arange(100)<10
        plain=fit_weighted_logistic(x,y); balanced=fit_weighted_logistic(x,y,balanced=True)
        self.assertAlmostEqual(predict_logistic(x,plain)[0],.1,places=6)
        self.assertAlmostEqual(predict_logistic(x,balanced)[0],.5,delta=2e-6)
        self.assertAlmostEqual(balanced['class_weights'][1],5.)

    def test_calibration_fits_distortion_without_team_intercept(self):
        x=np.linspace(-3,3,20000)
        # Deterministic quantile labels, with local class frequencies close to sigmoid(2x).
        uniform=(np.arange(len(x))*0.6180339887498949)%1
        y=uniform<sigmoid(2*x)
        self.assertAlmostEqual(m.temperature(x,y),2.,delta=.04)
        p=m.platt(x,uniform<sigmoid(1.4*x-.6))
        self.assertAlmostEqual(p['slope'],1.4,delta=.04)
        self.assertAlmostEqual(p['intercept'],-.6,delta=.04)

    def trained(self):
        raw=fixture(120); labels=np.resize(np.array(['H','A','D']),120)
        target=ExternalTargets(labels,raw.frame_ids,raw.period_ids)
        batch=m.examples('J03WMX','S0',raw,target,4,True)
        return raw,m.fit([batch])

    def test_quality_state_excludes_control_and_team_identity(self):
        raw,model=self.trained()
        swapped=replace(raw,values=raw.values.copy(),valid=raw.valid.copy())
        for name in raw.names:
            if name.startswith('H_') and 'A_'+name[2:] in raw.names:
                swapped.values[:,raw.names.index(name)]=raw.column('A_'+name[2:])
                swapped.values[:,raw.names.index('A_'+name[2:])]=raw.column(name)
        a=m.scores(raw,model,4); b=m.scores(swapped,model,4)
        np.testing.assert_allclose(a.p_dead,b.p_dead)
        np.testing.assert_allclose(a.p_home_given_alive,1-b.p_home_given_alive,atol=1e-12)
        changed=change(raw,H_distance_kernel=999.,A_distance_kernel=-999.,H_nearest_1_m=.01,A_nearest_1_m=100.)
        np.testing.assert_allclose(a.p_dead,m.scores(changed,model,4).p_dead)
        self.assertEqual(len(m.quality_block(raw,4).names),30)

    def test_fully_blind_stays_neutral_even_after_calibration(self):
        raw,model=self.trained(); raw.values[:]=np.nan; raw.valid[:]=False
        c={'dead_slope':3.,'dead_intercept':5.,'team_slope':2.}
        scores=m.scores(raw,model,4,c)
        np.testing.assert_allclose(scores.probabilities,1/3.)
        self.assertTrue((scores.state_support==0).all())
        self.assertTrue((scores.team_support==0).all())

    def test_missing_ball_is_not_a_forced_dead_prediction(self):
        raw,model=self.trained(); missing=fixture(120,missing_ball=True)
        scores=m.scores(missing,model,4)
        self.assertTrue(np.all((scores.p_dead>0)&(scores.p_dead<1)))
        self.assertTrue((scores.team_source==2).all())

    def test_immobile_and_moving_remain_probabilistic(self):
        raw,model=self.trained()
        for speed in (0.,10.):
            changed=change(raw,ball_speed_mps=speed)
            p=m.scores(changed,model,4).p_dead
            self.assertTrue(np.all((p>0)&(p<1)))

    def test_quality_does_not_change_team_design(self):
        raw,model=self.trained()
        for name in m.QUALITY[:7]: raw.values[:,raw.names.index(name)]=.5
        # Team attribution is unchanged by availability metadata on the state head.
        self.assertTrue(model['heads']['visible_team']['symmetric_team'])
        self.assertFalse(set(m.QUALITY)&set(model['heads']['visible_team']['feature_names']))


class J9Leakage(unittest.TestCase):
    def test_forbidden_data_and_outside_fold_targets_rejected_before_read(self):
        with patch.object(j9,'load_targets',side_effect=AssertionError('Forbidden read')) as read:
            for name in ('J03WPY','J03WQQ','J03WR9','BAR-ATH','2017461'):
                with self.assertRaises(PermissionError): j9.target(name,[name])
            with self.assertRaises(PermissionError): j9.target('J03WMX',['J03WN1'])
            read.assert_not_called()

    def test_incomplete_predictions_prevent_outer_target_read(self):
        with patch.object(j9,'read_json',return_value={'predictions':[], 'experiment_id':'fake'}), \
             patch.object(j9,'target',side_effect=AssertionError('Premature labels')) as read:
            with self.assertRaises(ValueError): j9.score_outer('J03WMX',{'experiment_id':'fake'},print)
            read.assert_not_called()

    def test_inner_calibration_never_fits_inner_or_outer_holdout(self):
        training=['J03WN1','J03WOH','J03WOY']; seen=[]
        def fake_fit(matches,kind,progress):
            seen.append(matches)
            self.assertEqual(len(matches),2)
            self.assertNotIn('J03WMX',matches)
            raise RuntimeError('stop after proof of first inner fit')
        with patch.object(j9,'fit_pack',side_effect=fake_fit),patch.object(j9.Path,'exists',return_value=False):
            with self.assertRaises(RuntimeError): j9.inner_calibration(training,False)
        self.assertEqual(seen,[['J03WOH','J03WOY']])

if __name__=='__main__': unittest.main()

