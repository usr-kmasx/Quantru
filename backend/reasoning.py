"""Official llama.cpp reasoning effort / thinking budget controls."""
import json
import urllib.request

BUDGETS={'low':512,'medium':2048,'high':8192,'max':32768}
NATIVE=('minimal','low','medium','high','xhigh','max')
_cache={}

def capabilities(config,port,process=None):
    key=(config['model'],config.get('mmproj',''))
    previous=_cache.get(key)
    if process is not None and process.poll() is None:
        pid=process.pid
        if previous is None or previous[0]!=pid:
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/props',timeout=2) as r:
                    props=json.load(r)
                caps=props.get('chat_template_caps',{})
                levels=[x for x in caps.get('reasoning_effort_levels',[]) if x in NATIVE]
                # Use the server's thinking support if advertised; older
                # builds may expose it only as a chat-template capability.
                supported=props.get('supports_thinking',caps.get('supports_thinking'))
                if supported is None:
                    supported=props.get('has_reasoning',caps.get('supports_reasoning'))
                if supported is None:
                    supported=bool(levels) or any(x in props.get('chat_template','') for x in ('enable_thinking','<think>','<|think|>','reasoning_content','reasoning_effort'))
                previous=(pid,{'native':levels,'supported':bool(supported)})
                _cache.clear();_cache[key]=previous
            except (OSError,ValueError,TypeError):
                pass
    result=dict(previous[1]) if previous else {'native':[],'supported':None}
    result['model']=config['model']+'\n'+config.get('mmproj','')
    result['unlimited_default']=bool(config['thinking'] and config['reasoning_budget']==-1 and not result['native'])
    return result

def apply(payload,choice,caps,config):
    if choice is None:return
    if not isinstance(choice,str) or choice not in ('default','off',*NATIVE):
        raise ValueError('Invalid reasoning level.')
    kwargs=payload.setdefault('chat_template_kwargs',{})
    if choice=='default':return
    if choice=='off':
        kwargs['enable_thinking']=False
        payload['reasoning_effort']='none'
        payload['thinking_budget_tokens']=0
        return
    if caps['native']:
        if choice not in caps['native']:return
        kwargs['enable_thinking']=True
        payload['reasoning_effort']=choice
        # /apply-template must also receive the selected level for accurate counting.
        kwargs['reasoning_effort']=choice
        kwargs['reasoning_strength']=choice
    elif choice in BUDGETS:
        kwargs['enable_thinking']=True
        payload['thinking_budget_tokens']=BUDGETS[choice]
