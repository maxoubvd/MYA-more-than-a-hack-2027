"""Exactness against exhaustive paths, soft durations, boundaries and label hygiene."""
from __future__ import annotations

from dataclasses import replace
from itertools import product
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from src.features.builder import build_features
from src.features.team_assignment import FeatureInputs
from src.hygiene.guards import guard_decoded_labels
from src.models.observations import factor_scores
from src.sequential.viterbi import viterbi, path_objective
from src.sequential.dynamic_matrix import (BoundaryCues, boundary_cues, transition_costs,
    count_transitions, fit_transition_prior, base_costs)
from src.sequential.decoder import decode
from src.sequential_pipeline import options, save_sequence, load_sequence, validate
from src.utils.external_data import ExternalTargets


def scores(home, dead=.01, periods=None, support=True):
    home = np.asarray(home, dtype=float)
    periods = np.ones(len(home), dtype=int) if periods is None else np.asarray(periods)
    n = len(home)
    return factor_scores(np.broadcast_to(dead, n), home, periods > 0,
        state_support=np.full(n, int(support)), team_support=np.full(n, int(support)),
        team_source=np.full(n, int(support)))


def prior():
    p = np.full((3, 3), .0025)
    np.fill_diagonal(p, .995)
    return {'version': 'symmetric-markov-v1', 'class_order': ['H','A','D'], 'transition_probability': p.tolist()}


def features(n=40):
    player = np.broadcast_to(np.array([[.2,.3],[.25,.6],[.7,.3],[.75,.6]], dtype=np.float32), (n,4,2)).copy()
    ball = np.broadcast_to(np.array([.21,.3], dtype=np.float32), (n,2)).copy()
    matrix = build_features(FeatureInputs(player, ball, np.array(['H','H','A','A']),
        np.arange(n), np.ones(n, dtype=int), 25., (100.,60.)))
    matrix.diagnostics['fps'] = 25.
    return matrix


def changed(matrix, **columns):
    result = replace(matrix, values=matrix.values.copy(), valid=matrix.valid.copy())
    for name, value in columns.items():
        result.values[:, result.names.index(name)] = value
    result.valid[:] = np.isfinite(result.values)
    return result


def decoded(home, dead=.01, periods=None, allowed=None, support=True):
    score = scores(home, dead, periods, support)
    ids = np.ones(len(home), dtype=int) if periods is None else np.asarray(periods)
    return decode(score, np.arange(len(home)), ids, base_costs(prior()), options(), allowed_states=allowed)


class ExactViterbiTests(unittest.TestCase):
    def test_static_objective_matches_exhaustive_search(self):
        rng = np.random.default_rng(5)
        for n in range(1, 6):
            e, c = rng.normal(size=(n,3)), rng.uniform(.1, 3., size=(3,3))
            result = viterbi(e,c)
            candidates = [path_objective(np.array(path),e,c) for path in product(range(3),repeat=n)]
            self.assertAlmostEqual(result.objective,max(candidates),places=12)
            self.assertAlmostEqual(path_objective(result.path,e,c),result.objective,places=12)

    def test_time_dependent_costs_and_forced_state_match_exhaustive_search(self):
        rng = np.random.default_rng(8)
        e, c = rng.normal(size=(5,3)), rng.uniform(.1,3.,size=(5,3,3))
        e[2,:2] = -np.inf
        initial = np.log([.2,.3,.5])
        result = viterbi(e,c,initial)
        best = max(path_objective(np.array(path),e,c,initial) for path in product(range(3),repeat=5))
        self.assertEqual(result.path[2],2)
        self.assertAlmostEqual(result.objective,best,places=12)

    def test_max_marginal_gaps_match_state_constrained_exhaustive_paths(self):
        rng=np.random.default_rng(12)
        e,c=rng.normal(size=(4,3)),rng.uniform(.1,2.,size=(3,3))
        result=viterbi(e,c)
        paths=[np.array(path) for path in product(range(3),repeat=4)]
        values=np.array([path_objective(path,e,c) for path in paths])
        for frame in range(4):
            conditional=sorted(max(values[i] for i,path in enumerate(paths) if path[frame]==state) for state in range(3))
            self.assertAlmostEqual(result.max_marginal_gap[frame],conditional[-1]-conditional[-2],places=12)

    def test_exact_ties_minimize_changes_and_expose_ambiguity(self):
        result=viterbi(np.zeros((8,3)),np.zeros((3,3)))
        self.assertEqual(result.changes,0)
        self.assertTrue((result.path==result.path[0]).all())
        np.testing.assert_array_equal(result.max_marginal_gap,0.)

    def test_hard_singleton_state_has_infinite_gap(self):
        result=viterbi(np.array([[-np.inf,-np.inf,0.]]),np.zeros((3,3)))
        self.assertEqual(result.path.tolist(),[2])
        self.assertTrue(np.isposinf(result.max_marginal_gap[0]))

    def test_inputs_are_not_modified(self):
        e,c=np.array([[0.,-1.,-2.],[-2.,0.,-1.]]),np.ones((3,3))
        original_e,original_c=e.copy(),c.copy()
        viterbi(e,c)
        np.testing.assert_array_equal(e,original_e);np.testing.assert_array_equal(c,original_c)

    def test_invalid_emissions_costs_and_initial_potentials_fail(self):
        for e in (np.empty((0,3)),np.full((2,3),np.nan),np.full((2,3),-np.inf),np.full((2,3),np.inf)):
            with self.assertRaises(ValueError): viterbi(e,np.ones((3,3)))
        e=np.zeros((2,3))
        for c in (np.zeros((2,2)),np.full((3,3),-.1),np.full((3,3),np.nan)):
            with self.assertRaises(ValueError): viterbi(e,c)
        with self.assertRaises(ValueError): viterbi(e,np.ones((3,3)),np.array([0.,np.nan,0.]))


class TemporalPriorTests(unittest.TestCase):
    def test_counts_never_bridge_unknowns_or_halves(self):
        target=ExternalTargets(np.array(list('HHXAADDHH')),np.r_[np.arange(6),100,101,102],np.array([1]*6+[2]*3))
        count=count_transitions(target)
        self.assertEqual(count[0,0],2);self.assertEqual(count[1,1],1)
        self.assertEqual(count[1,2],1);self.assertEqual(count[2,0],1)
        self.assertEqual(count[0,1],0);self.assertEqual(count[2,2],0)

    def test_learned_prior_is_team_symmetric_positive_and_duration_soft(self):
        target=ExternalTargets(np.array(list('HHHHHAAADDDDHHAD')),np.arange(16),np.ones(16,dtype=int))
        fitted=fit_transition_prior({'J03WMX':target})
        p=np.asarray(fitted['transition_probability']);exchange=np.array([1,0,2])
        np.testing.assert_allclose(p,p[np.ix_(exchange,exchange)])
        np.testing.assert_allclose(p.sum(axis=1),1.)
        self.assertTrue((p>0).all());self.assertIsNone(fitted['minimum_duration_frames'])

    def test_validation_or_test_cannot_fit_priors(self):
        target=ExternalTargets(np.array(list('HAD')),np.arange(3),np.ones(3,dtype=int))
        for match in ('J03WPY','J03WR9'):
            with self.assertRaises(PermissionError): fit_transition_prior({match:target})

    def test_missing_state_and_bad_timelines_fail(self):
        target=ExternalTargets(np.array(list('HHAA')),np.arange(4),np.ones(4,dtype=int))
        with self.assertRaises(ValueError): fit_transition_prior({'J03WMX':target})
        with self.assertRaises(ValueError): count_transitions(replace(target,frame_ids=np.array([0,1,9,10])))
        with self.assertRaises(ValueError): count_transitions(replace(target,labels=np.array(list('HZAA'))))
        with self.assertRaises(TypeError): count_transitions({'labels':target.labels})

    def test_invalid_stochastic_prior_is_rejected(self):
        bad=prior();bad['transition_probability'][0]=[0.,0.,0.]
        with self.assertRaises(ValueError): base_costs(bad)


class BoundaryCueTests(unittest.TestCase):
    def test_team_control_cannot_change_dead_transition_costs(self):
        matrix=features()
        second=changed(matrix,H_distance_kernel=0.,A_distance_kernel=1.,tag_H_minus_A=-10.)
        a=scores(np.full(40,.8));b=scores(np.r_[np.full(20,.9),np.full(20,.1)])
        first=boundary_cues(matrix,a,options());other=boundary_cues(second,b,options())
        np.testing.assert_array_equal(first.values[:,2:],other.values[:,2:])
        c1,c2=transition_costs(prior(),first),transition_costs(prior(),other)
        np.testing.assert_array_equal(c1[:,:2,2],c2[:,:2,2]);np.testing.assert_array_equal(c1[:,2,:2],c2[:,2,:2])

    def test_contact_alone_is_not_a_team_recovery(self):
        matrix=changed(features(),contact_acceleration_candidate=1.,contact_window_nearest_player_m=.1)
        cues=boundary_cues(matrix,scores(np.full(40,.9)),options())
        cost=transition_costs(prior(),cues);base=base_costs(prior())
        np.testing.assert_allclose(cost[:,0,1],base[0,1]);np.testing.assert_allclose(cost[:,1,0],base[1,0])

    def test_opposing_control_and_near_contact_soften_recovery_cost(self):
        matrix=changed(features(),contact_acceleration_candidate=1.,contact_window_nearest_player_m=.1)
        cues=boundary_cues(matrix,scores(np.r_[np.full(20,.95),np.full(20,.05)]),options())
        cost=transition_costs(prior(),cues)
        self.assertLess(cost[20,0,1],base_costs(prior())[0,1])
        self.assertAlmostEqual(cost[20,1,0],base_costs(prior())[1,0])

    def test_unavailable_cues_leave_base_costs_unchanged(self):
        cues=BoundaryCues(np.full((10,4),np.nan))
        np.testing.assert_array_equal(transition_costs(prior(),cues),np.broadcast_to(base_costs(prior()),(10,3,3)))

    def test_reductions_are_bounded_and_never_hard_transitions(self):
        cost=transition_costs(prior(),BoundaryCues(np.ones((5,4))),reduction=.5)
        base=np.broadcast_to(base_costs(prior()),cost.shape)
        self.assertTrue((cost>=.5*base).all());self.assertTrue((cost<=base).all())
        self.assertTrue((cost>0).all())

    def test_context_never_connects_control_across_halves(self):
        matrix=features();periods=np.r_[np.ones(20,dtype=int),np.full(20,2,dtype=int)]
        matrix=replace(matrix,period_ids=periods)
        cues=boundary_cues(matrix,scores(np.r_[np.full(20,.9),np.full(20,.1)],periods=periods),options())
        known=np.isfinite(cues.values[:,:2])
        self.assertTrue((cues.values[:,:2][known]==0).all())

    def test_invalid_cues_or_targets_are_rejected(self):
        for value in (np.full((4,4),2.),np.full((4,4),np.inf),np.zeros((4,3))):
            with self.assertRaises(ValueError): transition_costs(prior(),BoundaryCues(value))
        with self.assertRaises(ValueError): transition_costs(prior(),BoundaryCues(np.zeros((4,4))),reduction=1.)
        with self.assertRaises(TypeError): boundary_cues({'labels':['H']},scores(np.array([.5])),options())


class SequenceBehaviourTests(unittest.TestCase):
    def test_pass_with_one_weak_opponent_frame_stays_with_same_team(self):
        home=np.full(40,.9);home[20]=.45
        self.assertTrue((decoded(home).labels=='H').all())

    def test_brief_deflection_without_persistent_control_is_removed(self):
        home=np.full(40,.9);home[19:21]=.4
        self.assertTrue((decoded(home).labels=='H').all())

    def test_true_short_opponent_possession_with_strong_evidence_is_kept(self):
        home=np.full(50,.99);home[22:27]=.001
        self.assertTrue((decoded(home).labels[22:27]=='A').all())

    def test_one_frame_recovery_can_survive_no_minimum_duration(self):
        home=np.full(40,.99);home[20]=1e-12
        self.assertEqual(decoded(home).labels[20],'A')

    def test_one_frame_dead_spell_can_survive_strong_support(self):
        dead=np.full(40,.001);dead[20]=1.-1e-12
        self.assertEqual(decoded(np.full(40,.99),dead=dead).labels[20],'D')

    def test_duel_flicker_does_not_create_dozen_possessions(self):
        home=np.full(60,.9);home[20:40]=np.resize([.49,.51],20)
        self.assertTrue((decoded(home).labels=='H').all())

    def test_period_reset_and_excluded_frames_prevent_carry(self):
        periods=np.r_[np.ones(12,dtype=int),np.zeros(3,dtype=int),np.full(12,2,dtype=int)]
        home=np.r_[np.full(12,.99),np.full(3,.5),np.full(12,.45)]
        result=decoded(home,periods=periods)
        self.assertTrue((result.labels[:12]=='H').all());self.assertTrue((result.labels[12:15]=='X').all())
        self.assertTrue((result.labels[15:]=='A').all())

    def test_complete_unobserved_period_abstains_instead_of_using_dwell_prior(self):
        result=decoded(np.full(20,.9),dead=.95,support=False)
        self.assertTrue((result.labels=='X').all());self.assertTrue(result.allowed_unknown.all())

    def test_uniform_gap_in_observed_period_is_decoded_without_inventing_positions(self):
        home=np.full(40,.99);dead=np.full(40,.01)
        home[12:28]=.5;dead[12:28]=1./3.
        score=scores(home,dead);support=np.ones(40,dtype=int);support[12:28]=0
        score=replace(score,state_support=support,team_support=support)
        result=decode(score,np.arange(40),np.ones(40,dtype=int),base_costs(prior()),options())
        self.assertTrue((result.labels=='H').all())

    def test_published_dead_constraint_is_enforced_inside_optimization(self):
        allowed=np.ones((40,3),dtype=bool);allowed[10:15,:2]=False
        result=decoded(np.full(40,.999),dead=.0001,allowed=allowed)
        self.assertTrue((result.labels[10:15]=='D').all())
        self.assertTrue(np.isposinf(result.margin[10:15]).all())

    def test_blind_period_preserves_only_explicit_singleton_constraints(self):
        allowed=np.ones((20,3),dtype=bool);allowed[4:8,:2]=False
        result=decoded(np.full(20,.5),dead=1./3.,allowed=allowed,support=False)
        self.assertTrue((result.labels[4:8]=='D').all())
        self.assertTrue((result.labels[np.r_[0:4,8:20]]=='X').all())

    def test_boundary_envelope_exposes_timing_ambiguity_without_moving_path(self):
        home=np.r_[np.full(15,.99),np.full(6,.5),np.full(15,.01)]
        result=decoded(home)
        self.assertEqual(len(result.boundaries),1)
        profile=result.boundaries[0]
        self.assertIn(profile['frame'],profile['near_optimal_frames'])
        self.assertGreater(profile['envelope_end_frame'],profile['envelope_start_frame'])
        self.assertTrue(profile['envelope_not_statistical_interval'])

    def test_guard_never_silently_fills_an_unexpected_abstention(self):
        labels=np.array(['H','X','A']);periods=np.ones(3,dtype=int)
        with self.assertRaises(ValueError): guard_decoded_labels(labels,periods)
        np.testing.assert_array_equal(guard_decoded_labels(labels,periods,allowed_unknown=np.array([False,True,False])),labels)
        with self.assertRaises(ValueError): guard_decoded_labels(np.array(['H']),np.array([0]))

    def test_score_alignment_invalid_frames_and_impossible_constraints_fail(self):
        score=scores(np.full(10,.9))
        with self.assertRaises(ValueError): decode(score,np.arange(10)*2,np.ones(10,dtype=int),base_costs(prior()),options())
        with self.assertRaises(ValueError): decode(score,np.arange(10),np.ones(10,dtype=int),base_costs(prior()),options(),allowed_states=np.zeros((10,3),dtype=bool))
        with self.assertRaises(TypeError): decode({'labels':['H']},np.arange(1),np.ones(1),base_costs(prior()),options())

    def test_decoder_does_not_open_target_loaders(self):
        with patch('src.utils.external_data.load_targets',side_effect=AssertionError('No target reads')):
            result=decoded(np.full(20,.9))
        self.assertTrue((result.labels=='H').all())


class SequentialArtifactTests(unittest.TestCase):
    def test_archive_roundtrip_and_boundary_tampering(self):
        result=decoded(np.r_[np.full(20,.99),np.full(20,.01)])
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            save_sequence(result,np.arange(40),np.ones(40,dtype=int),folder,{'synthetic':True})
            arrays,manifest=load_sequence(folder)
            np.testing.assert_array_equal(arrays['labels'],result.labels)
            self.assertEqual(manifest['version'],'sequential-v1')
            (folder/'boundaries.json').write_text('{}')
            with self.assertRaises(ValueError): load_sequence(folder)

    def test_validation_selector_refuses_train_or_final_test_before_model_access(self):
        with patch('src.sequential_pipeline.load_model',side_effect=AssertionError('No model access')):
            for match in ('J03WMX','J03WR9'):
                with self.assertRaises(PermissionError): validate(match_id=match)

    def test_fixed_experiment_has_no_duration_minimum_or_public_search(self):
        opt=options()
        self.assertIsNone(opt['minimum_duration_frames'])
        self.assertEqual(opt['hyperparameter_search_budget'],0)
        self.assertEqual(opt['primary_decoder'],'dynamic')


if __name__=='__main__': unittest.main()
