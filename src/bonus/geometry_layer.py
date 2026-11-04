"""H/A-only geometry layer. Imputed ball positions never enter the D head."""
from dataclasses import replace
import numpy as np
from src.models.dataset import FeatureBlock,observation_design
from src.models.tabular import predict_logistic
from src.preprocessing.player_denoising import track_kinematics,duplicate_weights
from src.features.k_nearest import proximity_features
from src.features.relative_kinematics import relative_features
from src.bonus.contracts import validate_inputs

CONTROL_NAME='local_control_A_minus_H_arrival'


def local_control(players,velocity,ball,teams,options):
    """Bounded team-odd local arrival proxy, not an observed possession label.

Minimum arrival time makes exact duplicate slots contribute once. Missing player
velocity falls back explicitly to position-only arrival; no player is imputed.
"""
    v=np.where(np.isfinite(velocity),velocity,0.)
    speed=np.linalg.norm(v,axis=-1)
    v=v*np.minimum(1.,options['player_speed_mps']/np.maximum(speed,1e-12))[...,None]
    projected=players+options['reaction_time_s']*v
    time=options['reaction_time_s']+np.linalg.norm(projected-ball[:,None,:],axis=-1)/options['player_speed_mps']
    arrival=[]
    for team in ('H','A'):
        selected=time[:,np.asarray(teams)==team]
        arrival.append(np.min(np.where(np.isfinite(selected),selected,np.inf),axis=1,initial=np.inf))
    with np.errstate(invalid='ignore'):
        value=np.tanh((arrival[1]-arrival[0])/options['arrival_temperature_s'])
    value[~(np.isfinite(arrival[0])&np.isfinite(arrival[1]))]=np.nan
    return value.astype(np.float32)


def append_control(block,value):
    value=np.asarray(value,dtype=np.float32)
    if value.shape!=(len(block.values),) or not block.symmetric_team or np.isinf(value).any():
        raise ValueError('Named odd team block and aligned local control required')
    return FeatureBlock(np.column_stack((block.values,value.astype(float))),block.names+(CONTROL_NAME,),True)


class Geometry:
    def __init__(self,inputs,matrix,options):
        validate_inputs(inputs)
        if not np.array_equal(inputs.frame_ids,matrix.frame_ids) or not np.array_equal(inputs.period_ids,matrix.period_ids):
            raise ValueError('Geometry and observation feature timelines differ')
        self.inputs=inputs;self.options=options;self.design=observation_design(matrix)
        scale=np.asarray(inputs.pitch_dims,dtype=np.float32)
        self.players=inputs.players_xy_normalized*scale;self.ball=inputs.ball_xy_normalized*scale
        self.players[inputs.period_ids<=0]=np.nan;self.ball[inputs.period_ids<=0]=np.nan
        self.velocity=track_kinematics(self.players,inputs.period_ids,inputs.frame_ids,inputs.fps,
                                       max_link_speed_mps=20.).velocity
        self.control=local_control(self.players,self.velocity,self.ball,inputs.team_mapping,options['control'])

    def imputed_block(self,bridge):
        rows=np.flatnonzero(bridge.filled)
        if not len(rows):return rows,None,None
        merged=self.ball.copy()
        merged[rows]=bridge.layers.imputed_xy[rows]*np.asarray(self.inputs.pitch_dims,dtype=np.float32)
        bv=track_kinematics(merged,self.inputs.period_ids,self.inputs.frame_ids,self.inputs.fps,
                            max_link_speed_mps=100.).velocity
        players=self.players[rows];ball=merged[rows];velocity=self.velocity[rows]
        weights,_=duplicate_weights(players,self.inputs.team_mapping,radius_m=.15)
        proximity,distances,delta=proximity_features(players,ball,self.inputs.team_mapping,weights)
        relative=relative_features(distances,delta,velocity,bv[rows],self.inputs.team_mapping)
        cols={**proximity,**relative}
        for t in ('H','A'):cols[t+'_motion_distance_kernel']=proximity[t+'_distance_kernel']*relative[t+'_velocity_coherence']
        # The frozen builder stores each physical column in float32 before design.
        get=lambda n:np.asarray(cols[n],dtype=np.float32).astype(float)
        positive=lambda x:np.log1p(np.maximum(x,0.))
        values=[self.design.collective_team.values[rows]]
        for rank in (1,2,3):values.append(positive(get(f'A_nearest_{rank}_m'))-positive(get(f'H_nearest_{rank}_m')))
        for suffix in ('distance_kernel','motion_distance_kernel','nearest_closing_speed_mps','velocity_coherence',
                       'within_1m_effective_n','within_2m_effective_n','within_5m_effective_n'):
            values.append(get('H_'+suffix)-get('A_'+suffix))
        values.append(positive(get('A_nearest_relative_speed_mps'))-positive(get('H_nearest_relative_speed_mps')))
        block=FeatureBlock(np.column_stack(values),self.design.visible_team.names,True)
        control=local_control(players,velocity,ball,self.inputs.team_mapping,self.options['control'])
        return rows,block,control


def update_home(base,rows,home,*,imputed=False):
    rows=np.asarray(rows,dtype=int);home=np.asarray(home,float)
    if not len(rows):return base
    if home.shape!=(len(rows),) or not np.isfinite(home).all() or ((home<0)|(home>1)).any():
        raise ValueError('Supported team probabilities required')
    probabilities=base.probabilities.copy();conditional=base.p_home_given_alive.copy()
    dead=base.p_dead[rows].astype(float)
    probabilities[rows,0]=(1-dead)*home;probabilities[rows,1]=(1-dead)*(1-home)
    conditional[rows]=home
    source=base.team_source.copy();support=base.team_support.copy()
    if imputed:source[rows]=4;support[rows]=np.maximum(support[rows],1)
    confidence=base.confidence.copy();p=probabilities[rows].astype(float)
    confidence[rows]=np.clip(1.+np.sum(p*np.log(np.maximum(p,1e-15)),axis=1)/np.log(3.),0.,1.)
    result=replace(base,probabilities=probabilities,p_home_given_alive=conditional,
                   team_source=source,team_support=support,confidence=confidence).validate()
    if not np.array_equal(result.p_dead,base.p_dead,equal_nan=True) or not np.array_equal(result.probabilities[:,2],base.probabilities[:,2],equal_nan=True):
        raise RuntimeError('J10 is forbidden to change the D observation')
    return result


def control_scores(geometry,base,head):
    mask=base.active&(base.team_source==1)
    rows=np.flatnonzero(mask)
    block=append_control(geometry.design.visible_team,geometry.control)
    probability=predict_logistic(FeatureBlock(block.values[rows],block.names,True),head)
    return update_home(base,rows,probability)


def bridge_scores(geometry,base,bridge,head,*,control=False):
    rows,block,potential=geometry.imputed_block(bridge)
    if not len(rows):return base
    both=geometry.design.both_teams[rows]
    keep=np.flatnonzero(both);selected=rows[keep]
    if not len(selected):return base
    if control:block=append_control(block,potential)
    block=FeatureBlock(block.values[keep],block.names,True)
    home=predict_logistic(block,head)
    alpha=np.exp(-.5*(bridge.layers.uncertainty_m[selected]/geometry.options['imputed_team_sigma_m'])**2)
    home=alpha*home+(1-alpha)*base.p_home_given_alive[selected]
    return update_home(base,selected,home,imputed=True)
