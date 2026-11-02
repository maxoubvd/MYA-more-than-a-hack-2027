"""Aggregate delivered-coordinate diagnostics; no target or framewise export."""
import numpy as np
from src.bonus.contracts import validate_inputs
from src.features.team_assignment import period_runs


def summarize(values):
    a=np.asarray(values,dtype=float); a=a[np.isfinite(a)]
    if not len(a): return {'count':0,'mean':None,'median':None,'p90':None,'p99':None,'max':None}
    return {'count':len(a),'mean':float(a.mean()),'median':float(np.median(a)),
            'p90':float(np.quantile(a,.90)),'p99':float(np.quantile(a,.99)),'max':float(a.max())}


def observation_profile(inputs):
    validate_inputs(inputs)
    active=inputs.period_ids>0; ball_seen=inputs.ball_observed
    scale=np.asarray(inputs.pitch_dims,dtype=np.float32)
    lengths=[]; left_censored=right_censored=0
    visible_speed=[]; player_speed=[]; periods=[]
    for start,end in period_runs(inputs.period_ids):
        missing=~ball_seen[start:end]
        edges=np.diff(np.r_[False,missing,False].astype(np.int8))
        starts,ends=np.flatnonzero(edges==1),np.flatnonzero(edges==-1)
        lengths.extend((ends-starts).tolist())
        left_censored+=int((starts==0).sum()); right_censored+=int((ends==end-start).sum())
        ball=inputs.ball_xy_normalized[start:end]*scale
        both=ball_seen[start+1:end]&ball_seen[start:end-1]
        speed=np.linalg.norm(np.diff(ball,axis=0),axis=-1)*inputs.fps
        visible_speed.extend(speed[both].tolist())
        players=inputs.players_xy_normalized[start:end]*scale
        both_p=inputs.players_observed[start+1:end]&inputs.players_observed[start:end-1]
        ps=np.linalg.norm(np.diff(players,axis=0),axis=-1)*inputs.fps
        player_speed.append(ps[both_p])
        periods.append({'period_id':int(inputs.period_ids[start]),'frames':end-start,'ball_missing_frames':int(missing.sum()),
                        'ball_missing_fraction':float(missing.mean())})
    visible=inputs.ball_xy_normalized[active&ball_seen]
    outside=((visible<0)|(visible>1)).any(axis=1)
    bs=np.asarray(visible_speed); ps=np.concatenate(player_speed) if player_speed else np.array([])
    counts={team:inputs.players_observed[active][:,inputs.team_mapping==team].sum(axis=1) for team in ('H','A')}
    return {'frames':int(active.sum()),'delivered_slots':len(inputs.team_mapping),'fps':inputs.fps,
        'ball_missing_frames':int((active&~ball_seen).sum()),'ball_missing_fraction':float((~ball_seen[active]).mean()),
        'ball_gap_duration_s':summarize(np.asarray(lengths)/inputs.fps),'ball_gap_left_censored':left_censored,
        'ball_gap_right_censored':right_censored,'ball_visible_outside_field_fraction':float(outside.mean()) if len(outside) else None,
        'apparent_ball_step_speed_mps':summarize(bs),'ball_step_above_100mps_fraction':float((bs>100).mean()) if len(bs) else None,
        'apparent_player_step_speed_mps':summarize(ps),'player_step_above_20mps_fraction':float((ps>20).mean()) if len(ps) else None,
        'observed_player_count_by_team':{team:summarize(value) for team,value in counts.items()},'periods':periods,
        'labels_read':False,'positions_imputed':False,
        'interpretation':'delivered-coordinate availability and apparent motion; not visual visibility or true physical speed; player fractions depend on roster slot count'}
