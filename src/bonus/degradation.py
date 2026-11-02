"""Fixed observation-only stress tests; synthetic truth stays in audit, not inputs."""
from dataclasses import dataclass,replace
import hashlib
import numpy as np
from src.bonus.contracts import validate_inputs
from src.bonus.protocol import protocol
from src.features.team_assignment import period_runs


@dataclass(frozen=True)
class SyntheticAudit:
    ball_removed: np.ndarray
    ball_outlier: np.ndarray
    quality: dict


@dataclass(frozen=True)
class DegradedObservations:
    observations: object
    audit: SyntheticAudit


def _rng(seed,period,component):
    return np.random.default_rng(np.random.SeedSequence([int(seed),int(period),int(component)]))


def gap_mask(ball,period_ids,scenario,seed,*,weights=None,component=11):
    """Exact TOTAL missing count per period; no native missing observation is filled."""
    observed=np.isfinite(ball).all(axis=-1); missing=~observed
    output=missing.copy()
    if scenario['gap_frames'] is None: return output
    low,high=scenario['gap_frames']
    for start,end in period_runs(period_ids):
        rng=_rng(seed,period_ids[start],component)
        local=output[start:end]; target=int(round((end-start)*scenario['missing_fraction']))
        count=int(local.sum())
        if count>target: raise ValueError('Native missingness exceeds the requested total; never restore data')
        probability=np.ones(end-start) if weights is None else np.asarray(weights[start:end],dtype=float)
        if not np.isfinite(probability).all() or (probability<=0).any(): raise ValueError('Positive observation-only gap weights required')
        cdf=np.cumsum(probability); cdf/=cdf[-1]
        attempts=0
        while count<target:
            origin=min(len(local)-1,int(np.searchsorted(cdf,rng.random())))
            length=int(rng.integers(low,high+1))
            candidates=np.flatnonzero(~local[origin:min(len(local),origin+length)])+origin
            use=candidates[:target-count]; local[use]=True; count+=len(use)
            attempts+=1
            if attempts>len(local)*20: raise RuntimeError('Could not realize frozen gap target')
    return output


def _context_weights(inputs,p):
    scale=np.asarray(inputs.pitch_dims,dtype=np.float32)
    ball=inputs.ball_xy_normalized*scale; players=inputs.players_xy_normalized*scale
    weights=np.ones(len(ball)); opt=p['context_gap_weights']
    for left in range(0,len(ball),4096):
        right=min(len(ball),left+4096)
        delta=players[left:right]-ball[left:right,None,:]
        density=(np.linalg.norm(delta,axis=-1)<=opt['neighbour_radius_m']).sum(axis=1)
        b=ball[left:right]
        boundary=np.min(np.column_stack((b[:,0],scale[0]-b[:,0],b[:,1],scale[1]-b[:,1])),axis=1)
        line=np.where(np.isfinite(boundary),np.exp(-np.abs(boundary)/opt['line_scale_m']),0.)
        weights[left:right]+=opt['density_gain']*density+opt['line_gain']*line
    return weights


def degrade(inputs,scenario_id,seed):
    validate_inputs(inputs)
    p=protocol()
    if seed not in p['seeds']: raise ValueError('Seed outside the preregistered V2 set')
    scenario=next((s for s in p['scenarios'] if s['id']==scenario_id),None)
    if scenario is None or (scenario_id=='S0' and seed!=p['seeds'][0]):
        raise ValueError('Scenario/seed outside the 22-condition suite')
    players=inputs.players_xy_normalized.copy(); ball=inputs.ball_xy_normalized.copy()
    active=np.asarray(inputs.period_ids)>0
    weights=_context_weights(inputs,p) if scenario['correlated_gaps'] else None
    missing=gap_mask(ball,inputs.period_ids,scenario,seed,weights=weights)
    removed=missing&inputs.ball_observed&active
    ball[removed]=np.nan
    outliers=np.zeros(len(ball),dtype=bool)
    scale=np.asarray(inputs.pitch_dims,dtype=np.float32)
    if scenario['spatial_corruption']:
        opt=p['corruption']
        out_spec={'missing_fraction':opt['outlier_fraction'],'gap_frames':opt['outlier_burst_frames']}
        # Outlier scheduling is independent of native ball gaps; no target state involved.
        carrier=np.zeros_like(ball)
        outliers=gap_mask(carrier,inputs.period_ids,out_spec,seed,component=31)&active
        for a,b in period_runs(inputs.period_ids):
            rng=_rng(seed,inputs.period_ids[a],21)
            ball[a:b]+=rng.normal(size=ball[a:b].shape).astype(np.float32)*(opt['ball_noise_sigma_m']/scale)
            players[a:b]+=rng.normal(size=players[a:b].shape).astype(np.float32)*(opt['player_noise_sigma_m']/scale)
            for left in range(a,b,opt['bias_block_frames']):
                right=min(b,left+opt['bias_block_frames'])
                ball[left:right]+=rng.normal(size=2).astype(np.float32)*(opt['ball_block_bias_sigma_m']/scale)
            rows=np.flatnonzero(outliers[a:b])+a
            ball[rows]+=rng.normal(size=(len(rows),2)).astype(np.float32)*(opt['outlier_sigma_m']/scale)
        outliers&=np.isfinite(ball).all(axis=1)
    if scenario['fragment_players']:
        opt=p['fragmentation']
        for a,b in period_runs(inputs.period_ids):
            rng=_rng(seed,inputs.period_ids[a],41)
            for left in range(a,b,opt['block_frames']):
                right=min(b,left+opt['block_frames'])
                for team in ('H','A'):
                    slots=np.flatnonzero(inputs.team_mapping==team)
                    players[left:right,slots]=players[left:right,rng.permutation(slots)]
                dropout=rng.random(players.shape[1])<opt['dropout_probability']
                players[left:right,dropout]=np.nan
    result=replace(inputs,players_xy_normalized=players,ball_xy_normalized=ball,
        players_observed=np.isfinite(players).all(axis=-1),ball_observed=np.isfinite(ball).all(axis=-1))
    validate_inputs(result)
    per_period=[]
    for a,b in period_runs(inputs.period_ids):
        actual=int((~result.ball_observed[a:b]).sum())
        target=int(round((b-a)*scenario['missing_fraction'])) if scenario['gap_frames'] else int((~inputs.ball_observed[a:b]).sum())
        if actual!=target: raise RuntimeError('Degradation changed its total missing count')
        per_period.append({'period_id':int(inputs.period_ids[a]),'frames':b-a,'missing_frames':actual,'target_missing_frames':target})
    quality={'scenario_id':scenario_id,'seed':seed,'missing_ball_fraction':float((~result.ball_observed[active]).mean()),
        'missing_player_fraction':float((~result.players_observed[active]).mean()),
        'delivered_ball_outlier_fraction':float(outliers[active].mean()),'per_period':per_period,
        'labels_used':False,'audit_masks_exposed_to_model':False,'raw_input_mutated':False}
    return DegradedObservations(result,SyntheticAudit(removed,outliers,quality))


def observation_digest(inputs):
    validate_inputs(inputs); h=hashlib.sha256()
    for key,value in sorted(inputs.feature_dict().items()):
        array=np.ascontiguousarray(value)
        h.update(key.encode());h.update(str(array.shape).encode());h.update(array.dtype.str.encode());h.update(array.tobytes())
    return h.hexdigest()
