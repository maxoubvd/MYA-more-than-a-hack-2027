"""Unsupervised descriptors fit ONLY on external training observations.

Two Gaussian modes describe log speed. Low mode is not P(dead ball). A high
acceleration quantile selects candidates, not validated physical contacts.
"""
from __future__ import annotations
import numpy as np
from src.utils.external_data import match_role


def fit_context_model(collective_speed,ball_acceleration,*,match_id,contact_quantile=.98):
    if match_role(match_id)!='train':
        raise PermissionError("Context descriptors may only fit external training observations")
    speed = np.asarray(collective_speed,dtype=float)
    z = np.log1p(speed[np.isfinite(speed)&(speed>=0)])
    if len(z)<20:
        raise ValueError("Too few valid observations for the activity descriptor")
    if len(z)>20000:
        z = z[np.linspace(0,len(z)-1,20000,dtype=int)]
    means = np.quantile(z,[.25,.75])
    variances = np.full(2,max(float(z.var()),.01))
    weights = np.full(2,.5)
    for _ in range(100):
        density = np.log(np.maximum(weights,1e-9))[None,:]-.5*(np.log(2*np.pi*variances)[None,:]+(z[:,None]-means)**2/variances)
        normalizer = np.logaddexp(density[:,0],density[:,1])
        responsibilities = np.exp(density-normalizer[:,None])
        counts = np.maximum(responsibilities.sum(axis=0),1e-9)
        new_means = (responsibilities*z[:,None]).sum(axis=0)/counts
        variances = np.maximum((responsibilities*(z[:,None]-new_means)**2).sum(axis=0)/counts,1e-4)
        weights = counts/counts.sum()
        change = np.max(np.abs(new_means-means))
        means = new_means
        if change<1e-6: break
    order = np.argsort(means)
    acceleration = np.asarray(ball_acceleration,dtype=float)
    acceleration = acceleration[np.isfinite(acceleration)]
    return {'version':'observation-context-v1','training_match':match_id,'labels_used':False,
        'activity_log_speed_means':means[order].tolist(),'activity_log_speed_variances':variances[order].tolist(),
        'activity_weights':weights[order].tolist(),'contact_quantile':contact_quantile,
        'contact_acceleration_threshold_mps2':float(np.quantile(acceleration,contact_quantile)) if len(acceleration) else None,
        'interpretation':'low-speed mode and high-acceleration candidates, not calibrated game states or contact labels'}


def low_activity_score(speed,model):
    speed = np.asarray(speed,dtype=float)
    result = np.full(len(speed),np.nan)
    valid = np.isfinite(speed)&(speed>=0)
    z = np.log1p(speed[valid])[:,None]
    means = np.asarray(model['activity_log_speed_means'])
    variances = np.asarray(model['activity_log_speed_variances'])
    weights = np.asarray(model['activity_weights'])
    if means.shape!=(2,) or variances.shape!=(2,) or weights.shape!=(2,) or not np.isfinite(np.r_[means,variances,weights]).all() or (variances<=0).any() or (weights<=0).any():
        raise ValueError("Invalid activity descriptor")
    density = np.log(weights)[None,:]-.5*(np.log(2*np.pi*variances)[None,:]+(z-means)**2/variances)
    result[valid] = np.exp(density[:,0]-np.logaddexp(density[:,0],density[:,1]))
    return result
