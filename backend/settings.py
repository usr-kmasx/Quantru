"""Validated, persistent settings for Quantru's llama.cpp engine."""
import json
import pathlib
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
MODELS = ROOT / 'models'
FILE = ROOT / 'settings.json'
DEFAULTS = {
    'model': '',
    'mmproj': '',
    'context': 8192, 'thinking': True, 'max_tokens': -1,
    'gpu_mode': 'vram-first', 'gpu_margin': 768, 'flash_attention': 'on',
    'cache_k': 'q4_0', 'cache_v': 'q4_0', 'cache_prompt': True,
    'mmproj_offload': True, 'batch': 2048, 'ubatch': 512,
    'threads': 6, 'threads_batch': 6, 'reasoning_budget': -1,
    'temperature': 1.0, 'top_k': 64, 'top_p': .95, 'min_p': .05,
    'repeat_penalty': 1.0, 'presence_penalty': 0.0, 'frequency_penalty': 0.0,
    'seed': -1, 'auto_update': True,
    'spec_method': 'none', 'draft_model': '', 'draft_tokens': 3, 'draft_min': 0,
}
RUNTIME = {'thinking','max_tokens','temperature','top_k','top_p','min_p',
           'repeat_penalty','presence_penalty','frequency_penalty','seed','auto_update'}
INTS = {'draft_tokens':(1,128),'draft_min':(0,128),'context':(512,262144),'max_tokens':(-1,262144),'gpu_margin':(128,4096),
        'batch':(32,8192),'ubatch':(32,8192),'threads':(1,64),'threads_batch':(1,64),
        'reasoning_budget':(-1,262144),'top_k':(0,262144),'seed':(-1,4294967295)}
FLOATS = {'temperature':(0,5),'top_p':(0,1),'min_p':(0,1),'repeat_penalty':(.1,3),
          'presence_penalty':(-2,2),'frequency_penalty':(-2,2)}
SPEC_METHODS = ('none','draft-mtp','draft-simple','draft-eagle3','draft-dflash','draft-dflash2','draft-dspark','draft-lilicorr')
CHOICES = {'spec_method':SPEC_METHODS,'gpu_mode':('vram-first','auto'),'flash_attention':('on','auto','off'),
           'cache_k':('f16','q8_0','q4_0','q4_1','q5_0','q5_1'),
           'cache_v':('f16','q8_0','q4_0','q4_1','q5_0','q5_1')}
def validate(data):
    if not isinstance(data,dict) or set(data) - set(DEFAULTS):
        raise ValueError('Unknown setting')
    result = {**DEFAULTS, **data}
    for key,value in result.items():
        if key in INTS:
            lo,hi=INTS[key]
            if type(value) is not int or not lo <= value <= hi: raise ValueError(f'Invalid {key}')
        elif key in FLOATS:
            lo,hi=FLOATS[key]
            if type(value) not in (int,float) or not lo <= value <= hi: raise ValueError(f'Invalid {key}')
        elif key in CHOICES:
            if value not in CHOICES[key]: raise ValueError(f'Invalid {key}')
        elif type(DEFAULTS[key]) is bool:
            if type(value) is not bool: raise ValueError(f'Invalid {key}')
        elif key in ('model','mmproj','draft_model'):
            if value == '': continue
            if not isinstance(value,str): raise ValueError(f'Invalid {key}')
            path=pathlib.Path(value).expanduser().resolve()
            if not pathlib.Path(value).expanduser().is_absolute() or path.suffix.lower() != '.gguf' or not path.is_file():
                raise ValueError(f'{key}: choose an existing local GGUF')
            result[key]=str(path)
    method = result['spec_method']
    if method not in ('none','draft-mtp') and not result['draft_model']:
        raise ValueError('This method requires a compatible draft GGUF.')
    if method != 'none' and result['draft_model'] == result['model']:
        raise ValueError('Choose a separate draft model, or leave the path empty for integrated MTP.')
    if result['draft_min'] > result['draft_tokens']:
        raise ValueError('Minimum draft tokens cannot exceed maximum.')
    if result['ubatch'] > result['batch']: raise ValueError('Micro batch cannot exceed batch size')
    if result['max_tokens'] == 0: raise ValueError('Maximum tokens must be -1 or positive')
    if result['flash_attention']=='off' and result['cache_v']!='f16':
        raise ValueError('Quantized V cache requires Flash Attention')
    return result
def load():
    if not FILE.exists(): return validate(DEFAULTS)
    return validate(json.loads(FILE.read_text()))
def save(data):
    data=validate(data)
    with tempfile.NamedTemporaryFile(mode='w',dir=ROOT,delete=False) as f:
        tmp=pathlib.Path(f.name); json.dump(data,f,indent=2); f.write('\n')
    tmp.replace(FILE)
    return data
