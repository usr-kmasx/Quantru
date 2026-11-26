"""Persistent settings for the local stable-diffusion.cpp engine."""
import json
import pathlib
import tempfile

ROOT = pathlib.Path(__file__).resolve().parent
MODELS = ROOT / 'models' / 'image'
KLEIN = MODELS
QWEN = MODELS / 'Qwen Image 2.1'
QWEN_DIFFUSION = QWEN/'qwen-image-2.1-step90000-Q8_0.gguf'
QWEN_ENCODER = QWEN/'qwen3-vl-8b-instruct-q4_k_m.gguf'
QWEN_VISION = QWEN/'mmproj-Qwen3VL-8B-Instruct-F16.gguf'
FILE = ROOT / 'image-settings.json'
SAMPLERS = ('euler','euler_a','heun','dpm2','dpm++2s_a','dpm++2m','dpm++2mv2','ipndm','ipndm_v','lcm','ddim_trailing','tcd','res_multistep','res_2s','er_sde','euler_cfg_pp','euler_a_cfg_pp','euler_ge','dpm++2m_sde','dpm++2m_sde_bt','lms')
SCHEDULERS = ('discrete','karras','exponential','ays','gits','sgm_uniform','simple','smoothstep','kl_optimal','lcm','bong_tangent','ltx2','logit_normal','flux2','flux','beta','llada_image')
DEFAULTS = {
    'diffusion':'',
    'encoder':'',
    'vae':'',
    'width':512,'height':512,'steps':4,'cfg':1.0,
    'sampler':'euler','scheduler':'flux2','seed':-1,
    'encoder_backend':'cpu','weight_mode':'offload',
    'mmap':True,'vae_tiling':True,'vae_tile_size':256,
    'threads':0,'compatibility':True,'auto_update':True,
    'loras':[],'lora_apply_mode':'auto',
    'llm_vision':'','clip_vision':'',
}
INTS = {'width':(128,2048),'height':(128,2048),'steps':(1,150),'seed':(-1,2147483647),'vae_tile_size':(64,1024),'threads':(0,64)}
CHOICES = {'sampler':SAMPLERS,'scheduler':SCHEDULERS,'encoder_backend':('cpu','vulkan0'),'weight_mode':('offload','auto'),'lora_apply_mode':('auto','immediately','at_runtime')}
def validate(data):
    if not isinstance(data,dict) or set(data)-set(DEFAULTS):
        raise ValueError('Unknown image setting.')
    result={**DEFAULTS,**data}
    for key,value in result.items():
        if key in INTS:
            lo,hi=INTS[key]
            if type(value) is not int or not lo<=value<=hi:raise ValueError(f'Invalid {key}.')
        elif key in CHOICES:
            if value not in CHOICES[key]:raise ValueError(f'Invalid {key}.')
        elif key=='cfg':
            if type(value) not in (int,float) or not 0<=value<=30:raise ValueError('Invalid CFG.')
        elif key=='loras':
            if not isinstance(value,list) or len(value)>16:raise ValueError('Choose up to 16 LoRAs.')
            adapters=[];seen=set()
            for entry in value:
                if not isinstance(entry,dict) or set(entry)!={'path','strength','enabled'}:raise ValueError('Invalid LoRA entry.')
                path,strength,enabled=entry['path'],entry['strength'],entry['enabled']
                if not isinstance(path,str) or not path.strip() or not pathlib.Path(path).is_absolute():raise ValueError('LoRA: enter an absolute file path.')
                if type(strength) not in (int,float) or not -10<=strength<=10 or type(enabled) is not bool:raise ValueError('Invalid LoRA strength or state.')
                file=pathlib.Path(path).resolve()
                if file.suffix.lower() not in ('.safetensors','.ckpt'):raise ValueError('LoRA: use a .safetensors or .ckpt file.')
                if enabled and not file.is_file():raise ValueError(f'LoRA not found: {file}')
                if file in seen:raise ValueError('Duplicate LoRA file.')
                seen.add(file);adapters.append({'path':str(file),'strength':strength,'enabled':enabled})
            result[key]=adapters
        elif type(DEFAULTS[key]) is bool:
            if type(value) is not bool:raise ValueError(f'Invalid {key}.')
        elif key in ('llm_vision','clip_vision'):
            if not isinstance(value,str):raise ValueError(f'Invalid {key}.')
            if value.strip():
                path=pathlib.Path(value).expanduser()
                if not path.is_absolute() or path.suffix.lower() not in ('.gguf','.safetensors') or not path.is_file():
                    raise ValueError(f'{key}: choose an existing GGUF or safetensors file.')
                result[key]=str(path.resolve())
            else:result[key]=''
        elif key in ('diffusion','encoder','vae'):
            if not isinstance(value,str):raise ValueError(f'Invalid {key}.')
            if not value.strip():
                result[key]='';continue
            path=pathlib.Path(value).expanduser().resolve()
            if not pathlib.Path(value).expanduser().is_absolute() or path.suffix.lower() not in ('.gguf','.safetensors') or not path.is_file():
                raise ValueError(f'{key}: choose an existing local model.')
            result[key]=str(path)
    if any(result[k]%16 for k in ('width','height','vae_tile_size')):
        raise ValueError('Width, height and VAE tile size must be multiples of 16.')
    return result
def reference_projector(c):
    if c.get('llm_vision'):return c['llm_vision']
    if (pathlib.Path(c['diffusion']).name==QWEN_DIFFUSION.name
        and pathlib.Path(c['encoder']).name==QWEN_ENCODER.name):
        projector=pathlib.Path(c['encoder']).parent/QWEN_VISION.name
        if not projector.is_file():raise ValueError('Qwen reference editing requires its original vision projector (mmproj).')
        return str(projector)
    return ''

def load():
    return validate(json.loads(FILE.read_text()) if FILE.exists() else DEFAULTS)
def save(data):
    data=validate(data)
    with tempfile.NamedTemporaryFile(mode='w',dir=FILE.parent,delete=False) as f:
        tmp=pathlib.Path(f.name);json.dump(data,f,indent=2);f.write('\n')
    tmp.replace(FILE)
    return data
