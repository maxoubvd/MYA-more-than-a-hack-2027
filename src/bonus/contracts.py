"""Shared observation/imputation and score contracts, never target containers."""
from dataclasses import dataclass
import numpy as np
from src.features.team_assignment import FeatureInputs,period_runs
from src.models.observations import ObservationScores
from src.utils.external_data import ExternalInputs


def validate_inputs(inputs):
    if not isinstance(inputs,ExternalInputs):
        raise TypeError('ExternalInputs only; targets and mixed dictionaries forbidden')
    FeatureInputs(inputs.players_xy_normalized,inputs.ball_xy_normalized,inputs.team_mapping,
        inputs.frame_ids,inputs.period_ids,inputs.fps,inputs.pitch_dims).validate()
    for values,mask in ((inputs.players_xy_normalized,inputs.players_observed),(inputs.ball_xy_normalized,inputs.ball_observed)):
        if np.asarray(mask).dtype!=bool or not np.array_equal(np.isfinite(values).all(axis=-1),mask):
            raise ValueError('Delivered observation mask differs from finite x/y')
    return inputs


@dataclass(frozen=True)
class PositionLayers:
    observed_xy: np.ndarray
    imputed_xy: np.ndarray
    uncertainty_m: np.ndarray

    def validate(self):
        raw,filled,sigma=map(np.asarray,(self.observed_xy,self.imputed_xy,self.uncertainty_m))
        if (raw.ndim not in (2,3) or raw.shape[-1]!=2 or len(raw)==0 or filled.shape!=raw.shape
                or sigma.shape!=raw.shape[:-1] or np.isinf(raw).any() or np.isinf(filled).any()):
            raise ValueError('Positions require separate same-shaped x/y and metre uncertainty')
        observed=np.isfinite(raw).all(axis=-1); imputed=np.isfinite(filled).all(axis=-1)
        if (observed&imputed).any() or ((np.isfinite(filled).sum(axis=-1)>0)&~imputed).any():
            raise ValueError('Imputation must be complete and cannot overwrite observations')
        if not np.isfinite(sigma[imputed]).all() or (sigma[imputed]<0).any() or not np.isnan(sigma[~imputed]).all():
            raise ValueError('Uncertainty applies only to imputed points, in metres')
        return self


@dataclass(frozen=True)
class ScoreArtifact:
    scores: ObservationScores
    frame_ids: np.ndarray
    period_ids: np.ndarray
    provenance: dict

    def validate(self):
        if not isinstance(self.scores,ObservationScores): raise TypeError('Named observation scores required')
        self.scores.validate()
        frames,periods=np.asarray(self.frame_ids),np.asarray(self.period_ids)
        if (frames.shape!=self.scores.active.shape or periods.shape!=frames.shape
                or not np.issubdtype(frames.dtype,np.integer) or not np.issubdtype(periods.dtype,np.integer)
                or (periods<0).any() or not np.array_equal(periods>0,self.scores.active)):
            raise ValueError('Score timeline differs')
        for a,b in period_runs(periods):
            if (np.diff(frames[a:b])!=1).any(): raise ValueError('Noncontiguous frames inside a period')
        required={'candidate_id','fit_matches','context_matches','preprocessing_matches','prior_matches',
                  'calibration_matches','code_sha256','configuration_sha256'}
        if not required<=self.provenance.keys(): raise ValueError('Incomplete candidate provenance')
        return self
