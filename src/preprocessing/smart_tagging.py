"""Automatic tactical context, never a possession or dead-ball target."""
from __future__ import annotations
import numpy as np
from src.features.team_assignment import period_runs

OFFENSIVE = {'BUILD UP','PROGRESSION','LONG BALL','ATTACKING TRANSITION','CREATING CHANCES',
             'PLAYERS IN THE BOX','BALL IN FINAL THIRD','BALL IN THE BOX'}
DEFENSIVE = {'DEFENDING IN DEFENSIVE THIRD','DEFENDING IN MIDDLE THIRD',
             'DEFENDING IN ATTACKING THIRD','DEFENSIVE TRANSITION'}


def tagging_features(events,frame_ids,period_ids,fps):
    n = len(frame_ids)
    names = ('tag_active_n','tag_unknown_team_n','tag_unknown_code_n','tag_H_support_n','tag_A_support_n',
             'tag_H_minus_A','tag_conflict','restart_window_active','restart_unknown_team',
             'restart_until_next_start_s','restart_since_last_end_s','restart_kickoff_active')
    if events is None:
        return {name:np.full(n,np.nan) for name in names}
    result = {name:np.zeros(n,dtype=float) for name in names}
    result['restart_until_next_start_s'][:] = np.nan
    result['restart_since_last_end_s'][:] = np.nan
    for left,right in period_runs(period_ids):
        frames = np.asarray(frame_ids[left:right])
        starts,ends = [],[]
        for event in events.to_dict('records'):
            start,end = event['start_frame'],event['end_frame']
            if not isinstance(start,(int,np.integer)) or not isinstance(end,(int,np.integer)) or not 0<=start<end:
                raise ValueError("Invalid half-open Smart Tagging interval")
            if end<=frames[0] or start>frames[-1]:
                continue
            low = left+int(np.searchsorted(frames,start,side='left'))
            high = left+int(np.searchsorted(frames,end,side='left'))
            code = str(event.get('code','')).strip().upper()
            team = event.get('team_code')
            result['tag_active_n'][low:high] += 1
            if team not in ('H','A'):
                result['tag_unknown_team_n'][low:high] += 1
            if code in OFFENSIVE|DEFENSIVE and team in ('H','A'):
                support = team if code in OFFENSIVE else ('A' if team=='H' else 'H')
                result[f'tag_{support}_support_n'][low:high] += 1
            elif code not in OFFENSIVE|DEFENSIVE|{'SET PIECES','GOALS'}:
                result['tag_unknown_code_n'][low:high] += 1
            if code=='SET PIECES':
                result['restart_window_active'][low:high] = 1
                if team not in ('H','A'):
                    result['restart_unknown_team'][low:high] = 1
                if 'kick off' in str(event.get('phase_type','')).casefold():
                    result['restart_kickoff_active'][low:high] = 1
                # Boundaries outside the period are not imported from another half.
                if frames[0]<=start<=frames[-1]: starts.append(start)
                if frames[0]<=end<=frames[-1]+1: ends.append(end)
        for name,boundaries,future in (('restart_until_next_start_s',starts,True),('restart_since_last_end_s',ends,False)):
            if not boundaries: continue
            boundaries = np.sort(np.unique(boundaries))
            indices = np.searchsorted(boundaries,frames,side='left' if future else 'right')
            valid = indices<len(boundaries) if future else indices>0
            chosen = boundaries[np.minimum(indices,len(boundaries)-1)] if future else boundaries[np.maximum(indices-1,0)]
            result[name][left:right] = np.where(valid,(chosen-frames if future else frames-chosen)/fps,np.nan)
    result['tag_H_minus_A'] = result['tag_H_support_n']-result['tag_A_support_n']
    result['tag_conflict'] = ((result['tag_H_support_n']>0)&(result['tag_A_support_n']>0)).astype(float)
    return result
