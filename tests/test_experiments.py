"""Search isolation, exact batched paths, feature ablations and frozen decisions."""
from dataclasses import replace
import tempfile
import unittest
from unittest.mock import patch
import numpy as np

from src.experiments.batch import decode_batch
from src.experiments.design import (select_block, family_examples, family_scores, scaled_costs,
                                    choose_family, choose_temporal, adoption)
from src.experiment_pipeline import fold_training, intervention, options, raw_matrix
from src.models.dataset import FeatureBlock, training_examples
from src.models.observations import factor_scores, model_scores
from src.models.tabular import fit_factorized
from src.sequential.decoder import decode
from src.sequential_pipeline import options as decoder_options
from src.features.builder import build_features
from src.features.team_assignment import FeatureInputs
from src.utils.external_data import ExternalTargets


def score(home, dead=.1, periods=None, support=True):
    home = np.asarray(home, dtype=float)
    n = len(home)
    active = np.ones(n,dtype=bool) if periods is None else np.asarray(periods)>0
    return factor_scores(np.broadcast_to(dead,n),home,active,state_support=np.full(n,int(support)),
                         team_support=np.full(n,int(support)),team_source=np.full(n,2))


def prior():
    return {'version':'symmetric-markov-v1','class_order':['H','A','D'],
            'transition_probability':[[.98,.01,.01],[.01,.98,.01],[.01,.01,.98]]}


def metric_rows():
    return [{'match_id':m,'scenario':s,'candidate':f,'spell_f1':.4,'columns':i+1}
            for i,f in enumerate(('base','motion','temporal','full'))
            for m in ('J03WMX','J03WN1','J03WOH','J03WOY') for s in ('clean','long_gaps','combined')]


class BatchExactTests(unittest.TestCase):
    def test_paths_equal_reference_with_random_costs_and_independent_candidates(self):
        rng=np.random.default_rng(29)
        for n in (1,2,5,60):
            scores=[score(rng.uniform(.01,.99,n),rng.uniform(.01,.9,n)) for _ in range(5)]
            costs=rng.uniform(0,5,(5,3,3))
            actual=decode_batch(scores,np.arange(n),np.ones(n,dtype=int),costs)
            for index,s in enumerate(scores):
                expected=decode(s,np.arange(n),np.ones(n,dtype=int),costs[index],decoder_options())
                np.testing.assert_array_equal(actual[index],expected.labels)

    def test_exact_ties_and_short_single_frame_states(self):
        scores=[score([.5]*6,1/3),score([.99,.99,.01,.99,.99],.00001)]
        for s in scores:
            n=len(s.active)
            costs=np.zeros((1,3,3))
            pred=decode_batch([s],np.arange(n),np.ones(n,dtype=int),costs)[0]
            ref=decode(s,np.arange(n),np.ones(n,dtype=int),costs[0],decoder_options()).labels
            np.testing.assert_array_equal(pred,ref)
        self.assertEqual(pred[2],'A')

    def test_independent_halves_and_completely_blind_period(self):
        periods=np.array([1]*5+[0]*3+[2]*5)
        s=score([.99]*5+[.5]*3+[.01]*5,periods=periods)
        actual=decode_batch([s],np.arange(13),periods,[scaled_costs(prior(),2,2)])[0]
        np.testing.assert_array_equal(actual[:5],['H']*5)
        np.testing.assert_array_equal(actual[5:8],['X']*3)
        np.testing.assert_array_equal(actual[8:],['A']*5)
        blind=score([.5]*13,1/3,periods,support=False)
        self.assertTrue((decode_batch([blind],np.arange(13),periods,[scaled_costs(prior(),1,1)])=='X').all())

    def test_invalid_costs_or_timeline_rejected(self):
        s=score([.9,.9])
        for c in (np.zeros((3,3)),np.full((1,3,3),-1),np.full((1,3,3),np.nan)):
            with self.assertRaises(ValueError): decode_batch([s],np.arange(2),np.ones(2,dtype=int),c)
        with self.assertRaises(ValueError): decode_batch([s],np.array([0,2]),np.ones(2,dtype=int),np.zeros((1,3,3)))


class IsolationTests(unittest.TestCase):
    def test_fold_never_contains_held_out_validation_or_test(self):
        for held in ('J03WMX','J03WN1','J03WOH','J03WOY'):
            training=fold_training(held)
            self.assertEqual(len(training),3)
            self.assertNotIn(held,training)
        for bad in ('J03WPY','J03WR9','BAR-ATH'):
            with self.assertRaises(PermissionError): fold_training(bad)

    def test_feature_loader_rejects_final_test_before_any_io(self):
        with patch('src.experiment_pipeline.load_inputs',side_effect=AssertionError('Should never open')):
            with self.assertRaises(PermissionError): raw_matrix('J03WR9',{'name':'clean'},20261026)

    def test_budget_cannot_be_silently_expanded(self):
        opt=options()
        with patch('src.experiment_pipeline.settings',side_effect=lambda name:
                   {**opt,'extra_searches':1} if name=='experiments.json' else {'scenario_seeds':[20261026]}):
            with self.assertRaises(ValueError): options()

    def test_ablations_are_explicit_nested_and_nonmutating(self):
        block=FeatureBlock(np.ones((5,5)),('distance','velocity_coherence','past_mean','recent_exit','size'),True)
        self.assertEqual(select_block(block,'base').names,('distance','size'))
        self.assertEqual(len(select_block(block,'motion').names),3)
        self.assertEqual(len(select_block(block,'temporal').names),4)
        self.assertEqual(len(select_block(block,'full').names),5)
        self.assertEqual(block.values.shape,(5,5))

    def test_interventions_keep_state_or_team_fixed(self):
        s=score([.9,.2,.6]); rules=score([.5]*3,.7)
        no=intervention(s,'no_collective')
        np.testing.assert_array_equal(no.p_dead,s.p_dead)
        np.testing.assert_array_equal(no.p_home_given_alive,.5)
        phy=intervention(s,'physical_state',rules)
        np.testing.assert_array_equal(phy.p_home_given_alive,s.p_home_given_alive)
        np.testing.assert_array_equal(phy.p_dead,rules.p_dead)
        np.testing.assert_array_equal(s.p_home_given_alive,[.9,.2,.6])

    def test_transition_scaling_preserves_diagonal_and_team_exchange(self):
        c=scaled_costs(prior(),.5,2)
        original=scaled_costs(prior(),1,1)
        np.testing.assert_array_equal(c.diagonal(),original.diagonal())
        self.assertEqual(c[0,1],original[0,1]*.5)
        self.assertEqual(c[0,2],original[0,2]*2)
        np.testing.assert_array_equal(c,c[np.ix_([1,0,2],[1,0,2])])

    def test_full_inference_exactly_matches_j4(self):
        n=90
        player=np.broadcast_to(np.array([[.2,.3],[.3,.6],[.7,.3],[.8,.6]],dtype=np.float32),(n,4,2)).copy()
        ball=np.column_stack((np.linspace(.2,.8,n),np.full(n,.3))).astype(np.float32)
        ball[30:45]=np.nan
        matrix=build_features(FeatureInputs(player,ball,np.array(['H','H','A','A']),np.arange(n),np.ones(n,dtype=int),25.,(100.,60.)))
        targets=ExternalTargets(np.array(list('HAD')*30),np.arange(n),np.ones(n,dtype=int))
        examples=[training_examples('J03WMX','clean',matrix,targets,maximum_rows=90)]
        opts={'l2':.01,'max_iterations':50,'gradient_tolerance':1e-6,'standardized_clip':8.}
        model=fit_factorized(examples,opts)
        model['feature_family']='full'
        np.testing.assert_allclose(family_scores(matrix,model).probabilities,model_scores(matrix,model).probabilities,rtol=0,atol=0)
        for family in ('base','motion','temporal'):
            selected=fit_factorized(family_examples(examples,family),opts)
            selected['feature_family']=family
            family_scores(matrix,selected).validate()


class SelectionTests(unittest.TestCase):
    def test_family_chooses_simpler_inside_registered_tolerance(self):
        rows=metric_rows()
        for row in rows:
            if row['candidate']=='full': row['spell_f1']=.404
        self.assertEqual(choose_family(rows,.005)[0],'base')
        for row in rows:
            if row['candidate']=='full': row['spell_f1']=.41
        self.assertEqual(choose_family(rows,.005)[0],'full')
        with self.assertRaises(ValueError): choose_family(rows[:-1],.005)

    def test_temporal_neighbourhood_rejects_isolated_peak(self):
        rows=[]
        scales=[.5,1.,2.]
        for a in scales:
            for b in scales:
                # Corner peak, poor adjacent settings; broad opposite plateau.
                value=.8 if (a,b)==(.5,.5) else (.1 if min(a,b)==.5 else .6)
                for m in ('J03WMX','J03WN1','J03WOH','J03WOY'):
                    for s in ('clean','long_gaps','combined'):
                        rows.append({'match_id':m,'scenario':s,'team_scale':a,'dead_scale':b,'spell_f1':value,
                            'short_segments':{'possession':{'recall_iou05':.1}}})
        choice,_=choose_temporal(rows,scales,.005)
        self.assertEqual((choice['team_scale'],choice['dead_scale']),(2.,2.))
        with self.assertRaises(ValueError): choose_temporal(rows[:-1],scales,.005)

    def test_gate_falls_back_if_any_match_or_short_possessions_regress(self):
        gate=options()['adoption_gate']
        rows=[{'match_id':m,'candidate':c,'mean_spell_f1':.4,'mean_short_recall':.1}
              for m in ('J03WPY','J03WQQ') for c in ('selected','j5_static')]
        self.assertEqual(adoption(rows,gate)['candidate'],'selected')
        rows[0]['mean_short_recall']=.05
        self.assertEqual(adoption(rows,gate)['candidate'],'j5_static')
        rows[0]['mean_short_recall']=.1
        rows[0]['mean_spell_f1']=.37
        self.assertEqual(adoption(rows,gate)['candidate'],'j5_static')
        with self.assertRaises(ValueError): adoption(rows[:2],gate)


if __name__=='__main__': unittest.main()
