"""Physical observations of possible stoppages; no H/A/D decision is made."""
from __future__ import annotations
import numpy as np
from src.features.team_assignment import period_runs


def contact_window_distance(nearest_distance, link_valid, half_window_frames):
    """Minimum player distance within an offline ball fragment, never across a gap.

    This retains timing uncertainty around an acceleration peak. It does not
    identify the touching player or assert that a contact occurred.
    """
    if type(half_window_frames) is not int or half_window_frames < 1:
        raise ValueError('Positive integer contact window required')
    distance = np.asarray(nearest_distance, dtype=float)
    links = np.asarray(link_valid, dtype=bool)
    if distance.ndim != 1 or links.shape != distance.shape:
        raise ValueError('Contact timeline mismatch')
    fragment = np.cumsum(~links)
    result = distance.copy()
    for offset in range(1, half_window_frames+1):
        if offset >= len(distance):
            break
        same = fragment[:-offset] == fragment[offset:]
        result[:-offset] = np.fmin(result[:-offset], np.where(same, distance[offset:], np.nan))
        result[offset:] = np.fmin(result[offset:], np.where(same, distance[:-offset], np.nan))
    # A missing current distance never becomes an invented observed contact.
    return np.where(np.isfinite(distance), result, np.nan)


def physical_features(ball,kinematics,period_ids,fps,pitch_dims,last_seen,*,low_motion_mps=.5,boundary_band_m=5.):
    x,y = ball[:,0],ball[:,1]
    distances = np.column_stack((x,pitch_dims[0]-x,y,pitch_dims[1]-y))
    boundary = np.min(distances,axis=1)
    speed = np.linalg.norm(kinematics.velocity,axis=-1)
    acceleration = np.linalg.norm(kinematics.acceleration,axis=-1)
    backwards = kinematics.backward_velocity
    outward_components = np.column_stack((-backwards[:,0],backwards[:,0],-backwards[:,1],backwards[:,1]))
    nearest = np.isfinite(distances)&(np.abs(distances-boundary[:,None])<=1e-5)
    support = nearest & np.isfinite(outward_components)
    denominator = support.sum(axis=1)
    outward = np.divide(np.where(support,outward_components,0).sum(axis=1),denominator,
        out=np.full(len(ball),np.nan),where=(denominator>0)&(boundary<=boundary_band_m))
    result = {'ball_speed_mps':speed,'ball_acceleration_mps2':acceleration,
              'ball_backward_speed_mps':np.linalg.norm(backwards,axis=-1),
              'ball_boundary_distance_m':boundary,'ball_backward_outward_speed_mps':outward,
              'ball_low_motion_score':np.exp(-.5*(speed/low_motion_mps)**2),
              'ball_low_motion_run_s':np.full(len(ball),np.nan),
              'ball_acceleration_local_peak':np.full(len(ball),np.nan),
              'ball_acceleration_peak_prominence_mps2':np.full(len(ball),np.nan),
              'ball_last_seen_boundary_distance_m':np.full(len(ball),np.nan),
              'ball_last_seen_outward_speed_mps':np.full(len(ball),np.nan),
              'ball_gap_after_boundary_exit':np.full(len(ball),np.nan)}
    for start,end in period_runs(period_ids):
        values = speed[start:end]
        index = np.arange(len(values))
        slow = np.isfinite(values)&(values<=low_motion_mps)
        last_reset = np.maximum.accumulate(np.where(~slow,index,-1))
        result['ball_low_motion_run_s'][start:end] = np.where(np.isfinite(values),np.where(slow,(index-last_reset)/fps,0),np.nan)
        if end-start>=3:
            a = acceleration[start:end]
            available = np.isfinite(a[:-2])&np.isfinite(a[1:-1])&np.isfinite(a[2:])
            peak = (a[1:-1]>a[:-2])&(a[1:-1]>=a[2:])
            result['ball_acceleration_local_peak'][start+1:end-1] = np.where(available,peak.astype(float),np.nan)
            result['ball_acceleration_peak_prominence_mps2'][start+1:end-1] = np.where(available&peak,np.maximum(a[1:-1]-(a[:-2]+a[2:])/2,0),np.where(available,0,np.nan))
    known = last_seen>=0
    chosen = np.maximum(last_seen,0)
    result['ball_last_seen_boundary_distance_m'][known] = boundary[chosen[known]]
    result['ball_last_seen_outward_speed_mps'][known] = outward[chosen[known]]
    evidence_known = known & np.isfinite(result['ball_last_seen_boundary_distance_m']) & np.isfinite(result['ball_last_seen_outward_speed_mps'])
    event = (~np.isfinite(ball).all(axis=-1))&(result['ball_last_seen_boundary_distance_m']<=boundary_band_m)&(result['ball_last_seen_outward_speed_mps']>0)
    result['ball_gap_after_boundary_exit'][evidence_known] = event[evidence_known].astype(float)
    return result
