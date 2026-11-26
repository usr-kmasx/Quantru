"""Transient streaming snapshots for other browsers. No extra disk logs."""
import threading
import time
import json
import copy
LOCK=threading.RLock()
LIVE={}

def start(chat,seq,owner):
    with LOCK:
        if chat in LIVE:raise ValueError('This chat is generating on another device.')
        LIVE[chat]={'seq':seq,'owner':owner,'answer':'','thinking':'','shell_runs':[],'shell_drafts':{},'thinking_boundaries':[],
                    'status':'','version':0,'done':False,'failed':False}

def event(chat,chunk):
    with LOCK:
        entry=LIVE.get(chat)
        if entry is None:return
        if chunk=='[DONE]':
            entry['done']=True;entry['version']+=1;return
        if not isinstance(chunk,dict):return
        delta=(chunk.get('choices') or [{}])[0].get('delta') or {}
        if chunk.get('shell_round'):
            entry['thinking_boundaries'].append({'after':chunk['shell_round']['after'],'offset':len(entry['thinking'])})
        entry['answer']+=delta.get('content') or ''
        entry['thinking']+=delta.get('reasoning_content') or ''
        if chunk.get('generation_stats'):entry['generation_stats']=chunk['generation_stats']
        if chunk.get('image_status'):entry['status']=chunk['image_status']
        if chunk.get('image_generated'):
            entry['generated_image']=True
            entry['answer']+=('\n\n' if entry['answer'] else '')+'[Generated image: '+(chunk.get('image_prompt') or '')+']'
        if chunk.get('shell_error') or chunk.get('image_error') or chunk.get('error'):entry['failed']=True
        e=chunk.get('shell_event')
        if e:
            if e['type']=='writing':
                entry['shell_drafts'][e['draft_id']]={'draft_id':e['draft_id'],'command':e['command'],'status':'writing'}
                entry['status']='Writing command…'
            elif e['type']=='start':
                entry['shell_drafts'].pop(e.get('draft_id'),None)
                entry['shell_runs'].append({'idx':e['idx'],'draft_id':e.get('draft_id'),'command':e['command'],'cwd':e['cwd'],'output':'','status':'running','exit_code':None})
                entry['status']='Running terminal command…'
            else:
                run=next((r for r in entry['shell_runs'] if r['idx']==e['idx']),None)
                if run:
                    if e['type']=='output':run['output']+=e.get('text','')
                    elif e['type']=='end':run.update(status=e['status'],exit_code=e['exit_code']);entry['status']=''
        entry['version']+=1

def line(chat,line):
    if not chat or not line.startswith(b'data:'):return
    raw=line[5:].strip()
    if raw==b'[DONE]':event(chat,'[DONE]')
    else:
        try:event(chat,json.loads(raw))
        except (ValueError,TypeError,KeyError,IndexError):pass

def get(chat):
    with LOCK:
        state=LIVE.get(chat)
        if state is None:return None
        return {k:copy.deepcopy(v) for k,v in state.items() if k!='owner'}

def finish(chat,owner):
    with LOCK:
        e=LIVE.get(chat)
        if e and e['owner']==owner:return LIVE.pop(chat)
