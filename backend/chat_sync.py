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
                    'timeline':[],'next_step':0,'status':'','version':0,'done':False,'failed':False}

def step(entry,kind,**fields):
    entry['next_step']+=1
    item={'id':entry['next_step'],'kind':kind,**fields}
    entry['timeline'].append(item)
    return item

def append_text(entry,kind,value):
    if not value:return False
    field='thinking' if kind=='thinking' else 'answer'
    start=len(entry[field])
    last=entry['timeline'][-1] if entry['timeline'] else None
    join=last and last['kind']==kind and last['end']==start
    separate=kind=='text' and bool(start) and not join
    if separate:
        entry[field]+='\n\n'
        start+=2
    entry[field]+=value
    end=len(entry[field])
    if join:last['end']=end
    else:step(entry,kind,start=start,end=end)
    return separate

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
        # Within a delta, reasoning precedes visible content consistently.
        changed=bool(delta.get('reasoning_content') or delta.get('content'))
        append_text(entry,'thinking',delta.get('reasoning_content') or '')
        if append_text(entry,'text',delta.get('content') or ''):chunk['answer_break']=True
        if chunk.get('generation_stats'):entry['generation_stats']=chunk['generation_stats']
        if chunk.get('image_status'):entry['status']=chunk['image_status']
        if chunk.get('image_generated'):
            entry['generated_image']=True
            entry['answer']+=('\n\n' if entry['answer'] else '')+'[Generated image: '+(chunk.get('image_prompt') or '')+']'
            step(entry,'generated_image');changed=True
        error=chunk.get('shell_error') or chunk.get('image_error') or chunk.get('error')
        if error:
            entry['failed']=True
            message=str(error.get('message') or error) if isinstance(error,dict) else str(error)
            step(entry,'error',message=message);changed=True
        e=chunk.get('shell_event')
        if e:
            if e['type']=='writing':
                id=e['draft_id']
                entry['shell_drafts'][id]={'draft_id':id,'command':e['command'],'status':'writing'}
                entry['status']='Writing command…'
            elif e['type']=='start':
                id=e.get('draft_id')
                entry['shell_drafts'].pop(id,None)
                entry['shell_runs'].append({'idx':e['idx'],'draft_id':id,'command':e['command'],'cwd':e['cwd'],'kind':e.get('kind','shell'),'output':'','status':'running','exit_code':None})
                step(entry,'tool',idx=e['idx']);changed=True
                entry['status']={'view_image':'Viewing image…','view_all_images':'Viewing images…','gallery_results':'Reading gallery results…'}.get(e.get('kind'),'Running terminal command…')
            else:
                run=next((r for r in entry['shell_runs'] if r['idx']==e['idx']),None)
                if run:
                    if e['type']=='gallery_total':run['gallery_total']=e['total'];run['gallery_items']=[]
                    elif e['type']=='gallery_items':run.setdefault('gallery_items',[]).extend(e['items'])
                    elif e['type']=='output':run['output']+=e.get('text','')
                    elif e['type']=='end':run.update(status=e['status'],exit_code=e['exit_code']);entry['status']=''
        if changed:chunk['timeline']=copy.deepcopy(entry['timeline'])
        entry['version']+=1

def final_timeline(entry,state):
    result=copy.deepcopy(entry.get('timeline',[]))
    for draft in entry.get('shell_drafts',{}).values():
        id=max((t['id'] for t in result),default=0)+1
        position=next((i for i,t in enumerate(result) if t['kind']=='error'),len(result))
        result.insert(position,{'id':id,'kind':'unfinished','command':draft.get('command',''),'status':'stopped' if state=='stopped' else 'error'})
    return result

def line(chat,line):
    if not chat or not line.startswith(b'data:'):return line
    raw=line[5:].strip()
    if raw==b'[DONE]':event(chat,'[DONE]')
    else:
        try:
            chunk=json.loads(raw)
            event(chat,chunk)
            if isinstance(chunk,dict) and 'timeline' in chunk:
                return ('data: '+json.dumps(chunk,ensure_ascii=False)+'\n').encode()
        except (ValueError,TypeError,KeyError,IndexError):pass
    return line

def get(chat):
    with LOCK:
        state=LIVE.get(chat)
        if state is None:return None
        return {k:copy.deepcopy(v) for k,v in state.items() if k not in ('owner','next_step')}

def finish(chat,owner):
    with LOCK:
        e=LIVE.get(chat)
        if e and e['owner']==owner:return LIVE.pop(chat)
