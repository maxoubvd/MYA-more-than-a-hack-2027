"""V2 observation stresses, fold isolation, weighted aggregation and budgets."""
import copy
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import numpy as np
from src import config
from src.delivery import load_release,read_json
from src.utils.external_data import ExternalInputs,ExternalTargets,INPUT_KEYS
from src.features.team_assignment import from_external
from src.models.observations import factor_scores
from src.bonus.contracts import PositionLayers,ScoreArtifact,validate_inputs
from src.bonus.protocol import protocol,conditions,fold,require_use,validate_fit_sources,aggregate
from src.bonus.degradation import degrade,observation_digest
from src.bonus.budget import BudgetLedger
from src.bonus import preflight


def fixture(n=508):
    periods=np.r_[np.ones(250,dtype=int),np.zeros(8,dtype=int),np.full(250,2,dtype=int)]
    players=np.tile(np.array([[.2,.3],[.2,.6],[.8,.3],[.8,.6]],dtype=np.float32),(len(periods),1,1))
    ball=np.column_stack((np.linspace(.1,.9,len(periods)),np.full(len(periods),.5))).astype(np.float32)
    return ExternalInputs(players,ball,np.isfinite(players).all(axis=-1),np.isfinite(ball).all(axis=-1),
        np.array(['H','H','A','A']),np.arange(len(periods)),periods,25.,(105.,68.))


def provenance(matches):
    return {key:list(matches) for key in ('fit_matches','context_matches','preprocessing_matches','prior_matches','calibration_matches')}


class DegradationTests(unittest.TestCase):
    def test_all_22_conditions_exact_period_counts_and_no_mutation(self):
        x=fixture(); initial=observation_digest(x)
        self.assertEqual(len(conditions()),22)
        for scenario,seed in conditions():
            r=degrade(x,scenario['id'],seed); y=r.observations
            for period in (1,2):
                mask=x.period_ids==period
                self.assertEqual(int((~y.ball_observed[mask]).sum()),round(mask.sum()*scenario['missing_fraction']))
            np.testing.assert_array_equal(y.ball_xy_normalized[x.period_ids==0],x.ball_xy_normalized[x.period_ids==0])
            np.testing.assert_array_equal(y.players_xy_normalized[x.period_ids==0],x.players_xy_normalized[x.period_ids==0])
            self.assertEqual(set(y.feature_dict()),INPUT_KEYS)
            self.assertEqual(observation_digest(x),initial)
            self.assertFalse(np.shares_memory(y.ball_xy_normalized,x.ball_xy_normalized))

    def test_reproducible_outputs_and_different_seeds(self):
        x=fixture()
        self.assertEqual(observation_digest(degrade(x,'S6',20261102).observations),
                         observation_digest(degrade(x,'S6',20261102).observations))
        self.assertNotEqual(observation_digest(degrade(x,'S6',20261102).observations),
                            observation_digest(degrade(x,'S6',20261103).observations))

    def test_each_half_has_independent_rng_and_context(self):
        x=fixture(); changed=x.ball_xy_normalized.copy(); changed[x.period_ids==1]=.001
        other=replace(x,ball_xy_normalized=changed)
        for name in ('S2','S3','S5','S6'):
            a=degrade(x,name,20261102).observations
            b=degrade(other,name,20261102).observations
            np.testing.assert_array_equal(a.ball_xy_normalized[x.period_ids==2],b.ball_xy_normalized[x.period_ids==2])
            np.testing.assert_array_equal(a.players_xy_normalized[x.period_ids==2],b.players_xy_normalized[x.period_ids==2])

    def test_severity_pairing_and_no_gap_resurrection(self):
        x=fixture(); a=degrade(x,'S6',20261102).observations; b=degrade(x,'S7',20261102).observations
        self.assertTrue((~a.ball_observed<=~b.ball_observed).all())
        np.testing.assert_array_equal(a.players_xy_normalized,b.players_xy_normalized)
        ball=x.ball_xy_normalized.copy();ball[20:40]=np.nan
        native=replace(x,ball_xy_normalized=ball,ball_observed=np.isfinite(ball).all(axis=-1))
        out=degrade(native,'S2',20261102).observations
        self.assertTrue(np.isnan(out.ball_xy_normalized[20:40]).all())
        self.assertEqual(observation_digest(degrade(native,'S0',20261102).observations),observation_digest(native))

    def test_target_below_native_missingness_rejected(self):
        x=fixture(); ball=x.ball_xy_normalized.copy();ball[:200]=np.nan
        x=replace(x,ball_xy_normalized=ball,ball_observed=np.isfinite(ball).all(axis=-1))
        with self.assertRaises(ValueError): degrade(x,'S1',20261102)

    def test_visible_corruption_keeps_availability_but_changes_positions(self):
        x=fixture(); r=degrade(x,'S5',20261102)
        np.testing.assert_array_equal(r.observations.ball_observed,x.ball_observed)
        self.assertFalse(np.array_equal(r.observations.ball_xy_normalized,x.ball_xy_normalized))
        self.assertTrue(r.audit.ball_outlier.any())
        self.assertFalse(r.audit.quality['audit_masks_exposed_to_model'])
        with self.assertRaises(TypeError): from_external(r)
        from_external(r.observations).validate()

    def test_fragmentation_never_exchanges_teams(self):
        p=copy.deepcopy(protocol())
        for key in ('ball_noise_sigma_m','player_noise_sigma_m','ball_block_bias_sigma_m','outlier_sigma_m'): p['corruption'][key]=0.
        with patch('src.bonus.degradation.protocol',return_value=p): y=degrade(fixture(),'S6',20261102).observations
        for team,expected in (('H',.2),('A',.8)):
            points=y.players_xy_normalized[:,y.team_mapping==team,0]
            self.assertTrue((points[np.isfinite(points)]==np.float32(expected)).all())

    def test_targets_unknown_scenarios_and_seeds_rejected(self):
        with self.assertRaises(TypeError): degrade(ExternalTargets(np.array(['H']),np.array([0]),np.array([1])),'S0',20261102)
        for name,seed in (('custom',20261102),('S0',20261103),('S2',0)):
            with self.assertRaises(ValueError): degrade(fixture(),name,seed)


class ContractTests(unittest.TestCase):
    def test_position_layers_keep_observed_and_imputed_separate(self):
        raw=np.array([[.1,.2],[np.nan,np.nan]])
        imputed=np.array([[np.nan,np.nan],[.3,.4]])
        PositionLayers(raw,imputed,np.array([np.nan,1.])).validate()
        with self.assertRaises(ValueError): PositionLayers(raw,np.zeros((2,2)),np.ones(2)).validate()
        with self.assertRaises(ValueError): PositionLayers(raw,imputed,np.array([np.nan,-1.])).validate()
        with self.assertRaises(ValueError): PositionLayers(raw,imputed,np.array([0.,1.])).validate()

    def test_masks_must_match_delivered_coordinates(self):
        x=fixture()
        with self.assertRaises(ValueError): validate_inputs(replace(x,ball_observed=np.zeros(len(x.frame_ids),dtype=bool)))

    def test_score_contract_rejects_timeline_or_provenance_mismatch(self):
        periods=np.array([1,1,0,2,2]); active=periods>0
        score=factor_scores(np.full(5,.1),np.full(5,.8),active,state_support=np.ones(5),team_support=np.ones(5),team_source=np.ones(5))
        prov={**provenance(['J03WN1','J03WOH','J03WOY']),'candidate_id':'fixture','code_sha256':'x','configuration_sha256':'y'}
        ScoreArtifact(score,np.arange(5),periods,prov).validate()
        with self.assertRaises(ValueError): ScoreArtifact(score,np.array([0,2,3,4,5]),periods,prov).validate()
        with self.assertRaises(ValueError): ScoreArtifact(score,np.arange(5),periods,{}).validate()


class FoldAndAggregationTests(unittest.TestCase):
    def test_training_and_evaluation_roles_never_overlap(self):
        for held in protocol()['train_matches']:
            others=fold(held)['training_matches']
            self.assertEqual(len(others),3)
            for match in others: require_use(match,'fit',held_out=held)
            require_use(held,'internal_evaluation',held_out=held)
            with self.assertRaises(PermissionError): require_use(held,'fit',held_out=held)
            validate_fit_sources(held,provenance(others))
            with self.assertRaises(PermissionError): validate_fit_sources(held,provenance(protocol()['train_matches']))
            bad=provenance(others);bad['calibration_matches']=[held]
            with self.assertRaises(PermissionError): validate_fit_sources(held,bad)

    def test_confirmation_consumed_test_public_and_new_source_unavailable(self):
        for name in ('J03WPY','J03WQQ','J03WR9','BAR-ATH','2017461'):
            with self.assertRaises(PermissionError): require_use(name,'setup_observations')
            with self.assertRaises(PermissionError): fold(name)

    def test_S41_and_R4_weight_families_and_levels_not_seed_counts(self):
        scores={'S0':.2,'S1':.6,'S2':.9,'S3':.6,'S4':.2,'S5':.8,'S6':.3,'S7':.4}
        rows=[{'match_id':'J03WMX','scenario_id':s['id'],'seed':seed,'spell_f1':scores[s['id']]} for s,seed in conditions()]
        out=aggregate(rows)
        self.assertAlmostEqual(out['S41'],.6)
        self.assertAlmostEqual(out['R4'],.5)
        with self.assertRaises(ValueError): aggregate(rows[:-1])
        with self.assertRaises(ValueError): aggregate(rows+[rows[0]])
        with self.assertRaises(PermissionError): aggregate([{**r,'match_id':'J03WR9'} for r in rows])

    def test_historical_package_remains_valid(self):
        package,manifest=load_release()
        self.assertEqual(package['dead_scale'],2.)
        self.assertEqual(manifest['expected_csv_sha256'],'8b1e2c851cd64f840b6aae8ff932e3aaa599507446fe4fa4a6fbbedbfad4c8f7')


class BudgetTests(unittest.TestCase):
    def ledger(self,root):
        return BudgetLedger(Path(root)/'budget.json',{'version':'fixture','max_configurations_by_stage':{'J9':2},
            'max_total_configurations':2,'max_cpu_seconds':10.,'max_gpu_job_wall_seconds':5.})

    def test_grid_required_frozen_and_stage_budget_enforced(self):
        with tempfile.TemporaryDirectory() as d:
            ledger=self.ledger(d)
            with self.assertRaises(PermissionError): ledger.register('J9',{'id':'a'})
            ledger.seal_grid('J9',[{'id':'a'},{'id':'b'}])
            ledger.register('J9',{'id':'a'});ledger.register('J9',{'id':'a'})
            ledger.register('J9',{'id':'b'})
            self.assertEqual(len(read_json(ledger.path)['configurations']),2)
            with self.assertRaises(PermissionError): ledger.register('J9',{'id':'c'})
            with self.assertRaises(ValueError): ledger.seal_grid('J9',[{'id':'a','changed':True}])
            with self.assertRaises(ValueError): ledger.seal_grid('J9',[{'id':'a'},{'id':'b'},{'id':'c'}])

    def test_actual_overrun_is_recorded_and_blocks_subsequent_jobs(self):
        with tempfile.TemporaryDirectory() as d:
            ledger=self.ledger(d)
            ledger.record_cost('setup',cpu_seconds=3.)
            ledger.record_cost('setup',cpu_seconds=3.)
            self.assertEqual(read_json(ledger.path)['cpu_seconds'],3.)
            with self.assertRaises(ValueError): ledger.record_cost('setup',cpu_seconds=4.)
            with self.assertRaises(RuntimeError): ledger.can_start(estimated_cpu_seconds=8.)
            with self.assertRaises(RuntimeError): ledger.record_cost('overrun',cpu_seconds=8.)
            state=read_json(ledger.path)
            self.assertEqual(state['cpu_seconds'],11.)
            self.assertTrue(state['over_budget'])
            with self.assertRaises(RuntimeError): ledger.can_start()
            with self.assertRaises(ValueError): ledger.record_cost('bad',cpu_seconds=float('nan'))

    def test_concurrent_writer_is_rejected_without_losing_state(self):
        with tempfile.TemporaryDirectory() as d:
            ledger=self.ledger(d)
            with ledger.locked():
                with self.assertRaises(RuntimeError): self.ledger(d).can_start()
            self.assertTrue(ledger.path.exists())
            self.assertFalse(ledger.path.with_suffix('.lock').exists())


class PreflightTests(unittest.TestCase):
    def test_complete_setup_validator_cannot_fit_or_read_labels(self):
        with tempfile.TemporaryDirectory() as d:
            with (patch.object(preflight,'OUT',Path(d)),patch.object(preflight,'register',return_value={'experiment_id':'fixture'}),
                  patch.object(preflight,'training_inputs',side_effect=lambda match:fixture()),
                  patch('src.utils.external_data.load_targets',side_effect=AssertionError('No targets')),
                  patch('src.utils.loaders.load_ground_truth',side_effect=AssertionError('No public labels')),
                  patch('src.models.tabular.fit_factorized',side_effect=AssertionError('No fitting'))):
                result=preflight.validate_suite(lambda text:None)
            self.assertEqual(len(result['runs']),88)
            self.assertEqual(result['model_fits'],0)
            self.assertEqual(result['candidate_scores_computed'],0)
            self.assertFalse(result['confirmation_opened'])


if __name__=='__main__': unittest.main()
