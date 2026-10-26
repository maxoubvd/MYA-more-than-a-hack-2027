"""Label-free feature matrix, explicit validity, units and source-independent schema."""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from src.features.team_assignment import FeatureInputs
from src.imputation.gap_analyzer import gap_features
from src.preprocessing.player_denoising import track_kinematics,duplicate_weights
from src.preprocessing.smart_tagging import tagging_features
from src.features.k_nearest import proximity_features
from src.features.relative_kinematics import relative_features
from src.features.collective_dynamics import collective_features
from src.features.context_features import temporal_context
from src.features.physical import physical_features,contact_window_distance
from src.features.activity import low_activity_score

FEATURE_VERSION = 'mya-features-v1'
DEFAULTS = {'player_link_speed_gate_mps':20.,'ball_link_speed_gate_mps':100.,'duplicate_radius_m':.15,
 'control_offset_m':.5,'control_sigma_m':1.5,'relative_velocity_sigma_mps':5.,
 'low_motion_scale_mps':.5,'boundary_band_m':5.,'temporal_window_s':1.,'contact_quantile':.98,
 'contact_half_window_frames':2}


@dataclass
class FeatureMatrix:
    values: np.ndarray
    valid: np.ndarray
    names: tuple[str,...]
    schema: list[dict]
    frame_ids: np.ndarray
    period_ids: np.ndarray
    diagnostics: dict

    def column(self,name):
        return self.values[:,self.names.index(name)]

    def apply_context_model(self,model):
        assignments = {'collective_low_activity_score':low_activity_score(self.column('collective_median_speed_mps'),model)}
        threshold = model.get('contact_acceleration_threshold_mps2')
        peak = self.column('ball_acceleration_local_peak')
        acceleration = self.column('ball_acceleration_mps2')
        available = np.isfinite(peak)&np.isfinite(acceleration)
        assignments['contact_acceleration_candidate'] = np.where(available,(peak>0)&(acceleration>=threshold),np.nan) if threshold is not None else np.full(len(peak),np.nan)
        for name,values in assignments.items():
            index = self.names.index(name)
            self.values[:,index] = values
            self.values[self.period_ids<=0,index] = np.nan
            self.valid[:,index] = np.isfinite(self.values[:,index])
        self.diagnostics['context_model'] = model
        return self


def _unit(name):
    for suffix,unit in (('_mps2','m/s^2'),('_mps','m/s'),('_m','m'),('_s','s'),('_n','count')):
        if name.endswith(suffix): return unit
    return '1'


def build_features(inputs,*,settings=None,smart_tags=None,homography=None,attack_directions=None,context_model=None,progress=None):
    if not isinstance(inputs,FeatureInputs):
        raise TypeError("Feature builder accepts observations only, never labels or mixed dictionaries")
    inputs.validate()
    options = dict(DEFAULTS)
    if settings:
        if set(settings)-set(options): raise ValueError("Unknown feature settings")
        options.update(settings)
    if any(not np.isfinite(v) or v<=0 for v in options.values()) or not 0<options['contact_quantile']<1:
        raise ValueError("Feature scales must be positive and finite")
    n = len(inputs.frame_ids)
    active = np.asarray(inputs.period_ids)>0
    scale = np.asarray(inputs.pitch_dims,dtype=np.float32)
    players = np.asarray(inputs.players_xy,dtype=np.float32)*scale
    ball = np.asarray(inputs.ball_xy,dtype=np.float32)*scale
    players[~active] = np.nan; ball[~active] = np.nan
    pk = track_kinematics(players,inputs.period_ids,inputs.frame_ids,inputs.fps,max_link_speed_mps=options['player_link_speed_gate_mps'])
    bk = track_kinematics(ball,inputs.period_ids,inputs.frame_ids,inputs.fps,max_link_speed_mps=options['ball_link_speed_gate_mps'])
    if progress: progress('Coordinate-derived kinematics computed inside valid fragments')
    weights,duplicates = duplicate_weights(players,inputs.team_mapping,radius_m=options['duplicate_radius_m'])
    columns,schema = {},[]
    def add(values,group,description):
        for name,value in values.items():
            if name in columns: raise ValueError('Duplicate feature name')
            a = np.asarray(value,dtype=np.float32)
            if a.shape!=(n,) or np.isinf(a).any(): raise ValueError('Invalid feature values')
            a = a.copy(); a[~active] = np.nan
            columns[name] = a
            schema.append({'name':name,'unit':_unit(name),'group':group,'description':description,
                           'missing':'NaN with valid=False; never a fabricated zero'})
    add({'ball_observed':bk.observed.astype(float),'ball_link_valid':bk.link_valid.astype(float),
         'ball_fragment_start':bk.fragment_start.astype(float)},'quality','Delivered availability or conservative continuity diagnostic; not a game-state label')
    for team in ('H','A'):
        slots = np.asarray(inputs.team_mapping)==team
        add({f'{team}_fragment_start_n':pk.fragment_start[:,slots].sum(axis=1)},'quality','New visible fragments, including first observations; not confirmed identity switches')
    gaps,last_seen,gap_runs = gap_features(bk.observed,inputs.period_ids,inputs.fps)
    add(gaps,'availability_context','Gap duration and previous/next observation distances, bounded by periods; future context is offline')
    collective = collective_features(players,pk.velocity,inputs.team_mapping,weights,duplicates,period_ids=inputs.period_ids,
                                     pitch_dims=inputs.pitch_dims,attack_directions=attack_directions)
    add(collective,'collective','Anonymous weighted team geometry and mean valid track velocities; extents are max-minus-min, spread is weighted standard deviation')
    proximity,distances,delta = proximity_features(players,ball,inputs.team_mapping,weights,
        control_offset_m=options['control_offset_m'],control_sigma_m=options['control_sigma_m'])
    add(proximity,'team_proximity','Metric proximity and Gaussian distance kernel; a potential control cue, not possession or ball-alive evidence')
    relative = relative_features(distances,delta,pk.velocity,bk.velocity,inputs.team_mapping,
                                  velocity_sigma_mps=options['relative_velocity_sigma_mps'])
    add(relative,'team_motion','Relative kinematics of actual nearest tracks; exact-distance ties averaged; positive closing means approaching')
    add({f'{team}_motion_distance_kernel':proximity[f'{team}_distance_kernel']*relative[f'{team}_velocity_coherence'] for team in ('H','A')},
        'team_motion','Distance kernel multiplied by a velocity consistency cue; unavailable velocity stays missing')
    del distances,delta
    physical = physical_features(ball,bk,inputs.period_ids,inputs.fps,inputs.pitch_dims,last_seen,
        low_motion_mps=options['low_motion_scale_mps'],boundary_band_m=options['boundary_band_m'])
    add(physical,'physical','Ball movement, line proximity and last-seen outward motion; none is a referee decision')
    nearest_player = np.fmin(proximity['H_nearest_1_m'],proximity['A_nearest_1_m'])
    add({'contact_nearest_player_m':nearest_player,
         'contact_window_nearest_player_m':contact_window_distance(nearest_player,bk.link_valid,options['contact_half_window_frames'])},
        'contact_geometry','Nearest-player distance now and minimum within a symmetric ball-fragment window; proximity supports a candidate but does not prove a touch')
    add({
         'collective_low_activity_score':np.full(n,np.nan),'contact_acceleration_candidate':np.full(n,np.nan)},
        'unlabelled_context','Low-activity mode and acceleration candidates require a model fitted only on external training observations; not calibrated labels')
    # Past/future support is exposed instead of filling temporal windows with zero.
    for name,series,unit in (('ball_speed',physical['ball_speed_mps'],'mps'),
                             ('collective_speed',collective['collective_median_speed_mps'],'mps'),
                             ('ball_visibility',bk.observed.astype(float),'')):
        context = temporal_context(series,inputs.period_ids,max(1,int(round(inputs.fps*options['temporal_window_s']))))
        renamed = {f'{name}_{key}_{unit}' if key in ('past_mean','future_mean','future_minus_past') and unit else f'{name}_{key}':value for key,value in context.items()}
        add(renamed,'temporal','Past and future windows exclude the current frame and never cross a period; support is the fraction of finite samples')
    add(tagging_features(smart_tags,inputs.frame_ids,inputs.period_ids,inputs.fps),'tactical',
        'Automatically inferred phase context; offensive/defensive polarity, conflicts and N/A retained; restart windows are not forced dead intervals')
    if homography is None:
        quality = {'homography_available':np.zeros(n),'homography_valid':np.full(n,np.nan),'homography_error_pixels':np.full(n,np.nan)}
    else:
        error,valid = (np.asarray(v) for v in homography)
        if error.shape!=(n,) or valid.shape!=(n,): raise ValueError('Homography feature alignment mismatch')
        quality = {'homography_available':np.ones(n),'homography_valid':valid.astype(float),'homography_error_pixels':np.where(valid & np.isfinite(error) & (error>=0),error,np.nan)}
    add(quality,'sensor_quality','Homography validity and nonnegative reprojection error are sensor confidence cues only')
    schema[-1]['unit'] = 'pixel'
    matrix = np.column_stack(list(columns.values())).astype(np.float32,copy=False)
    result = FeatureMatrix(matrix,np.isfinite(matrix),tuple(columns),schema,np.asarray(inputs.frame_ids).copy(),
        np.asarray(inputs.period_ids).copy(),{'version':FEATURE_VERSION,'settings':options,'gap_runs':gap_runs,
        'raw_positions_imputed':False,'identity_correction_claimed':False,'labels_used':False,
        'attack_direction_source':'caller metadata only; unavailable directions stay NaN',
        'optional_context_available':{'smart_tagging':smart_tags is not None,'homography':homography is not None}})
    if context_model is not None: result.apply_context_model(context_model)
    if progress: progress(f'Built {matrix.shape[1]} observation features with validity masks')
    return result
