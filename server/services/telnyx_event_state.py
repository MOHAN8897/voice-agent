"""Separate carrier leg, media, and recording transitions (no I/O)."""
from datetime import datetime

_LEG = {'call.initiated':'initiated','call.ringing':'ringing','call.answered':'answered',
        'call.bridged':'bridged','call.hangup':'hangup'}
_RANK = {'initiated':0,'ringing':1,'answered':2,'bridged':3,'hangup':4,'completed':4,'failed':4,'ended':4}

def event_state_patch(existing: dict, event: str, *, event_id: str = '', occurred_at: str = '') -> dict:
    channel = 'leg' if event in _LEG else 'media' if event.startswith('streaming.') else 'recording' if event.startswith('call.recording.') else None
    if channel is None:
        return {'last_event': event}
    if event_id and existing.get(f'{channel}_event_id') == event_id:
        return {}
    try:
        stamp = datetime.fromisoformat(occurred_at.replace('Z','+00:00')).timestamp() if occurred_at else None
    except (ValueError,TypeError):
        stamp = None
    previous = existing.get(f'{channel}_event_at')
    if stamp is not None and previous is not None and stamp < float(previous):
        return {}
    if channel == 'leg':
        status = _LEG[event]
        if _RANK.get(status,0) < _RANK.get(str(existing.get('status','')).replace('call.',''),0):
            return {}
        patch = {'status':status}
    elif channel == 'media':
        patch = {'media_status':event.removeprefix('streaming.')}
    else:
        patch = {'recording_status':event.removeprefix('call.recording.')}
    patch['last_event'] = event
    if event_id:patch[f'{channel}_event_id']=event_id
    if stamp is not None:patch[f'{channel}_event_at']=stamp
    return patch
