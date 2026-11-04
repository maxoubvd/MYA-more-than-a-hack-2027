"""Bounded ball-only interpolation and constant-velocity Kalman/RTS smoothing.

Raw coordinates and masks stay separate. Only observed endpoints and their own
adjacent valid links may support a bridge; no extrapolation across periods.
Uncertainty is a fixed engineering proxy, not a calibrated coverage guarantee.
"""
from dataclasses import dataclass
import numpy as np
from src.bonus.contracts import PositionLayers,validate_inputs
from src.features.team_assignment import period_runs


@dataclass(frozen=True)
class BallBridge:
    layers: PositionLayers
    age_s: np.ndarray
    gap_frames: np.ndarray
    audit: dict

    @property
    def filled(self):
        return np.isfinite(self.layers.imputed_xy).all(axis=1)


def kalman_bridge(left_previous,left,right,right_next,length,fps,options):
    dt=1./fps; R=options['measurement_sigma_m']**2
    F=np.array([[1.,dt],[0.,1.]])
    Q=options['acceleration_sigma_mps2']**2*np.array([[dt**4/4,dt**3/2],[dt**3/2,dt**2]])
    x=np.column_stack((left,(left-left_previous)/dt))
    P=np.array([[R,R/dt],[R/dt,2*R/dt**2]])
    filtered=[x.copy()]; covariance=[P.copy()]; predicted=[x.copy()]; predicted_cov=[P.copy()]
    H=np.array([1.,0.]); eye=np.eye(2)
    for k in range(1,length+3):
        x=x@F.T; P=F@P@F.T+Q
        predicted.append(x.copy()); predicted_cov.append(P.copy())
        if k>=length+1:
            z=right if k==length+1 else right_next
            K=P[:,0]/(P[0,0]+R)
            x=x+(z-x[:,0])[:,None]*K
            A=eye-np.outer(K,H);P=A@P@A.T+R*np.outer(K,K)
        filtered.append(x.copy());covariance.append(P.copy())
    smoothed=[a.copy() for a in filtered];smooth_cov=[a.copy() for a in covariance]
    for k in range(len(filtered)-2,-1,-1):
        C=np.linalg.solve(predicted_cov[k+1],F@covariance[k]).T
        smoothed[k]=filtered[k]+(smoothed[k+1]-predicted[k+1])@C.T
        smooth_cov[k]=covariance[k]+C@(smooth_cov[k+1]-predicted_cov[k+1])@C.T
    points=np.array([a[:,0] for a in smoothed[1:length+1]])
    sigma=np.sqrt(np.maximum([a[0,0] for a in smooth_cov[1:length+1]],0.))
    return points,sigma


def impute_ball(inputs,method,maximum_frames,options):
    validate_inputs(inputs)
    if method not in ('linear','kalman_rts') or maximum_frames not in (5,10,25) or inputs.fps!=25.:
        raise ValueError('Only registered J10 methods, limits and 25 Hz are supported')
    raw=np.asarray(inputs.ball_xy_normalized);pitch=np.asarray(inputs.pitch_dims,float)
    metric=raw.astype(float)*pitch;observed=np.isfinite(raw).all(axis=1)
    fill=np.full_like(raw,np.nan);sigma=np.full(len(raw),np.nan);age=sigma.copy()
    lengths=np.zeros(len(raw),dtype=np.int16)
    counts={k:0 for k in ('missing_runs','too_long','unbounded_or_missing_anchor','incompatible','accepted')}
    gate=options['maximum_ball_speed_mps'];acceleration=options['maximum_bridge_acceleration_mps2']
    for start,end in period_runs(inputs.period_ids):
        missing=~observed[start:end]
        edges=np.flatnonzero(np.diff(np.r_[False,missing,False].astype(np.int8)))+start
        for a,b in zip(edges[::2],edges[1::2]):
            counts['missing_runs']+=1;length=b-a
            if length>maximum_frames:
                counts['too_long']+=1;continue
            # Two observed points on each side, inside the same contiguous period.
            if (a-2<start or b+1>=end or not observed[[a-2,a-1,b,b+1]].all()
                    or (np.diff(inputs.frame_ids[a-2:b+2])!=1).any()):
                counts['unbounded_or_missing_anchor']+=1;continue
            previous,left,right,following=metric[[a-2,a-1,b,b+1]]
            T=(length+1)/inputs.fps;vl=(left-previous)*inputs.fps;vr=(following-right)*inputs.fps
            bridge=(right-left)/T
            if (max(np.linalg.norm(vl),np.linalg.norm(vr),np.linalg.norm(bridge))>gate
                    or max(np.linalg.norm(vl-bridge),np.linalg.norm(vr-bridge))>acceleration*T):
                counts['incompatible']+=1;continue
            t=np.arange(1,length+1)/inputs.fps;u=t/T
            proxy=np.sqrt(((1-u)**2+u*u)*options['measurement_sigma_m']**2
                           +(.5*options['acceleration_sigma_mps2']*t*(T-t))**2)
            if method=='linear':
                points=(1-u[:,None])*left+u[:,None]*right;uncertainty=proxy
            else:
                points,uncertainty=kalman_bridge(previous,left,right,following,length,inputs.fps,options)
                uncertainty=np.maximum(uncertainty,proxy)
            path=np.vstack([left,points,right]);step=np.linalg.norm(np.diff(path,axis=0),axis=1)*inputs.fps
            if (not np.isfinite(points).all() or not np.isfinite(uncertainty).all()
                    or (uncertainty>options['maximum_uncertainty_m']).any() or (step>gate).any()):
                counts['incompatible']+=1;continue
            fill[a:b]=points/pitch;sigma[a:b]=uncertainty;age[a:b]=t;lengths[a:b]=length
            counts['accepted']+=1
    layers=PositionLayers(raw.copy(),fill,sigma).validate()
    return BallBridge(layers,age,lengths,{'method':method,'maximum_frames':maximum_frames,
        'counts':counts,'imputed_frames':int(np.isfinite(fill).all(axis=1).sum()),
        'observations_overwritten':False,'extrapolation':False,'uncertainty_calibrated':False})
