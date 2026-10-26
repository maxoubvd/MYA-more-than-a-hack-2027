"""Directional temporal context, strictly bounded by the current period."""
from __future__ import annotations
import numpy as np
from src.features.team_assignment import period_runs


def temporal_context(values,period_ids,window_frames):
    values = np.asarray(values,dtype=float)
    if values.ndim != 1 or type(window_frames) is not int or window_frames<1:
        raise ValueError("Invalid context window")
    result = {key:np.full(len(values),np.nan) for key in ('past_mean','future_mean','past_support','future_support','future_minus_past')}
    for start,end in period_runs(period_ids):
        v = values[start:end]
        good = np.isfinite(v)
        sums = np.r_[0,np.cumsum(np.where(good,v,0))]
        counts = np.r_[0,np.cumsum(good)]
        index = np.arange(len(v))
        for name,low,high in (('past',np.maximum(0,index-window_frames),index),
                               ('future',index+1,np.minimum(len(v),index+window_frames+1))):
            count = counts[high]-counts[low]
            total = sums[high]-sums[low]
            width = high-low
            result[name+'_mean'][start:end] = np.divide(total,count,out=np.full(len(v),np.nan),where=count>0)
            result[name+'_support'][start:end] = np.divide(count,width,out=np.full(len(v),np.nan),where=width>0)
    result['future_minus_past'] = result['future_mean']-result['past_mean']
    return result
