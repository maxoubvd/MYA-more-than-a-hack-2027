"""J9 state quality adapter and train-only calibration; C0 modules stay frozen."""
from dataclasses import replace
import numpy as np
from src.models.dataset import FeatureBlock, observation_design, training_examples
from src.models.tabular import fit_logistic, predict_logistic, sigmoid
from src.models.observations import factor_scores
from src.bonus.j9_logistic import fit_weighted_logistic

QUALITY = ('ball_link_valid','ball_fragment_start','gap_duration_s','since_observation_s',
           'until_observation_s','gap_left_censored','gap_right_censored',
           'observed_player_fraction','velocity_supported_player_fraction')


def quality_block(matrix, slots):
    if type(slots) is not int or slots < 1:
        raise ValueError('Delivered roster slot count required')
    base = observation_design(matrix).state
    extra = [matrix.column(n) for n in QUALITY[:7]]
    extra += [(matrix.column('H_observed_n')+matrix.column('A_observed_n'))/slots,
              (matrix.column('H_velocity_observed_n')+matrix.column('A_velocity_observed_n'))/slots]
    return FeatureBlock(np.column_stack([base.values]+extra), base.names+QUALITY)


def examples(match, scenario, matrix, targets, slots, quality):
    batch = training_examples(match, scenario, matrix, targets, maximum_rows=12000)
    if not quality:
        return batch
    # The ordinary sampler is deterministic, aligned and contains known targets only.
    rows = np.searchsorted(matrix.frame_ids, batch.frame_ids)
    if not np.array_equal(matrix.frame_ids[rows],batch.frame_ids):
        raise ValueError('Training sample frame alignment failed')
    block = quality_block(matrix,slots)
    return replace(batch,state=FeatureBlock(block.values[rows].copy(),block.names))


def fit(examples, *, balanced=False, shared_teams=None):
    labels = np.concatenate([b.labels for b in examples])
    visible = np.concatenate([b.ball_visible for b in examples])
    teams = np.concatenate([b.both_teams for b in examples])
    alive = np.isin(labels,['H','A'])
    heads = {}
    for name, mask, y in [('state',np.ones(len(labels),bool),labels=='D'),
                         ('visible_team',alive&visible&teams,labels=='H'),
                         ('collective_team',alive&teams,labels=='H')]:
        if name!='state' and shared_teams is not None:
            heads[name]=shared_teams[name]
            continue
        blocks = [getattr(b,name) for b in examples]
        if any(b.names!=blocks[0].names for b in blocks):
            raise ValueError('Training design mismatch')
        block = FeatureBlock(np.concatenate([b.values for b in blocks])[mask],
                             blocks[0].names,blocks[0].symmetric_team)
        heads[name] = (fit_weighted_logistic(block,y[mask],balanced=balanced)
                       if name=='state' else fit_logistic(block,y[mask]))
    return {'heads':heads,'training_matches':sorted({b.match_id for b in examples}),
            'quality':len(heads['state']['feature_names'])==30,'balanced':balanced}


def logit(p):
    p=np.clip(np.asarray(p,float),1e-6,1.-1e-6)
    return np.log(p)-np.log1p(-p)


def temperature(logits, targets):
    """Convex positive inverse-temperature fit, fixed [0.05,20] numerical bounds."""
    x=np.asarray(logits,float); y=np.asarray(targets,float)
    if x.shape!=y.shape or not len(y) or not np.isfinite(x).all() or not np.isin(y,[0,1]).all():
        raise ValueError('Invalid calibration samples')
    a,b=.05,20.
    for _ in range(80):
        c=a+(b-a)*.3819660112501051; d=a+(b-a)*.6180339887498949
        loss=lambda k: float(np.mean(np.logaddexp(0.,k*x)-y*k*x))
        if loss(c)<loss(d): b=d
        else: a=c
    return float((a+b)/2.)


def platt(logits, targets):
    x=np.column_stack([logits,np.ones(len(logits))]); y=np.asarray(targets,float)
    if x.shape!=(len(y),2) or not len(y) or not np.isfinite(x).all() or not np.isin(y,[0,1]).all():
        raise ValueError('Invalid Platt samples')
    beta=np.array([1.,0.]); penalty=np.array([1e-8,1e-8])
    loss=lambda z: float(np.mean(np.logaddexp(0.,x@z)-y*(x@z))+.5*np.sum(penalty*z*z))
    for _ in range(100):
        p=sigmoid(x@beta); gradient=x.T@(p-y)/len(y)+penalty*beta
        step=np.linalg.solve((x.T*np.maximum(p*(1-p),1e-8))@x/len(y)+np.diag(penalty),gradient)
        before=loss(beta); amount=1.
        for _ in range(30):
            proposed=np.clip(beta-amount*step,[.05,-10.],[20.,10.])
            if loss(proposed)<=before: break
            amount*=.5
        if np.max(np.abs(proposed-beta))<1e-7: break
        beta=proposed
    return {'slope':float(beta[0]),'intercept':float(beta[1]),'loss':loss(beta)}


def calibrator(dead, home, labels, state_supported, team_supported, mode, matches):
    state=state_supported & np.isin(labels,['H','A','D'])
    team=team_supported & np.isin(labels,['H','A'])
    result={'mode':mode,'training_matches':sorted(matches),'dead_slope':1.,'dead_intercept':0.,
            'team_slope':1.,'state_rows':int(state.sum()),'team_rows':int(team.sum())}
    if mode.startswith('temperature_dead'):
        result['dead_slope']=temperature(logit(dead[state]),labels[state]=='D')
    elif mode=='platt_dead':
        p=platt(logit(dead[state]),labels[state]=='D')
        result.update(dead_slope=p['slope'],dead_intercept=p['intercept'])
    elif mode!='none':
        raise ValueError('Unknown registered calibration')
    if mode=='temperature_dead_and_shared_team':
        result['team_slope']=temperature(logit(home[team]),labels[team]=='H')
    return result


def scores(matrix, model, slots, calibration=None):
    design=observation_design(matrix)
    state=quality_block(matrix,slots) if model['quality'] else design.state
    dead=predict_logistic(state,model['heads']['state'])
    visible=predict_logistic(design.visible_team,model['heads']['visible_team'])
    collective=predict_logistic(design.collective_team,model['heads']['collective_team'])
    physical=[i for i,n in enumerate(design.state.names) if not n.endswith('_support')]
    support=np.isfinite(design.state.values[:,physical]).sum(axis=1)
    geometry=design.ball_visible & np.isfinite(matrix.column('H_nearest_1_m')) & np.isfinite(matrix.column('A_nearest_1_m'))
    home=np.where(geometry,visible,collective)
    team_support=np.where(geometry,np.isfinite(design.visible_team.values).sum(axis=1),
                          np.isfinite(design.collective_team.values).sum(axis=1))
    if calibration:
        dead=sigmoid(calibration['dead_slope']*logit(dead)+calibration['dead_intercept'])
        home=sigmoid(calibration['team_slope']*logit(home))
    # Availability never overrides missing physical evidence, including after calibration.
    dead[support==0]=1./3.; home[~design.both_teams]=.5; team_support[~design.both_teams]=0
    source=np.where(design.both_teams,np.where(geometry,1,2),0)
    return factor_scores(dead,home,design.active,state_support=support,team_support=team_support,team_source=source)
