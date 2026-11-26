"""Local image tool. Only an explicit @image in the current user turn enables it."""
import json
import base64
import io
import os
import pathlib
import re
import secrets
import subprocess
import tempfile
import threading
import time
from . import image_settings, chat_history, engine_updates

ROOT=pathlib.Path(__file__).resolve().parent
CLI=ROOT/'stable-diffusion.cpp'/'sd-cli'
TAG=re.compile(r'(?<!\w)@\s*image\b',re.I)
TOOL={'type':'function','function':{'name':'generate_image','description':'Generate or edit an image. For edits or image references, select reference_ids from the available image list. Image settings control size and sampling.','parameters':{'type':'object','properties':{'prompt':{'type':'string','description':'Faithful English visual description or editing instruction.'},'reference_ids':{'type':'array','items':{'type':'string'},'description':'IDs of actual images to edit or use as reference; omit or use [] for a new image without references.'}},'required':['prompt'],'additionalProperties':False}}}
# A stable state prefix, never written into conversation history.
INSTRUCTION = """Image tool: ON.
When the user requests an image, call generate_image with a prompt faithfully based on the current user request.
For edits, use the exact reference IDs from the available image list, and describe the requested changes while preserving unmentioned details. Do not invent reference IDs. For a fresh unrelated generation omit reference_ids. A text-only chat model can pass reference images without claiming to see them. Only native tool calls generate images. For another image, make another native call. Do not imitate tool results or claim success without a confirmed result. Image settings control resolution and sampling. For other requests, respond normally."""
UNAVAILABLE_INSTRUCTION = "Image tool: OFF. Enable with @image in composer. Never fake generation."
lock=threading.Lock()
child=None

def available():
    try:
        config=image_settings.load()
        return CLI.is_file() and all(config[k] for k in ('diffusion','encoder','vae'))
    except (OSError,ValueError):return False

def enabled(text):
    return isinstance(text,str) and bool(TAG.search(text))

def stop():
    global child
    with lock:
        if child is not None and child.poll() is None:
            child.terminate()
            try:child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                child.kill();child.wait()

MAX_REFERENCES=4
MAX_REFERENCE_BYTES=20*1024*1024

def reference_catalog(chat,seq):
    """Use only references belonging to this conversation, never arbitrary paths."""
    chat=chat_history.ident(chat);seq=chat_history.seqnum(seq)
    result={}
    with chat_history.connect() as db:
        rows=db.execute("""SELECT t.seq,t.files,EXISTS(SELECT 1 FROM generated_images g
            WHERE g.chat=t.chat AND g.seq=t.seq) AS generated
            FROM turns t WHERE t.chat=? AND t.seq<=? ORDER BY t.seq DESC LIMIT 64""",(chat,seq)).fetchall()
    for row in rows:
        n=row['seq']
        if row['generated'] and n<seq:
            result[f'generated_{n}']=(n,None,f'Generated image, message {n}')
        for i,meta in enumerate(json.loads(row['files']),1):
            if meta.get('type','').startswith('image/'):
                result[f'attached_{n}_{i}']=(n,i,f'Attachment {i}, message {n}: '+str(meta.get('name','image'))[:120])
        if len(result)>=16:break
    return dict(list(result.items())[:16])

def reference_instruction(catalog,seq):
    if not catalog:return 'No image references are available in this conversation.'
    lines=['Available image references (IDs only; do not invent IDs):']
    for id,(n,_,label) in catalog.items():
        lines.append(f'{id}: {label}'+(' [attached to current message]' if n==seq else ''))
    lines.append('References are forwarded in original conversation and attachment order, regardless of the order of selected IDs. In the editing prompt, use that same order when referring to image 1, image 2, and so on.')
    lines.append('For editing the image just attached, use its attached ID. For an edit of the previous generated result, use its generated ID. If multiple possible targets are ambiguous, ask which image. Do not use a reference for unrelated new images.')
    return '\n'.join(lines)

def read_references(chat,ids,catalog):
    if not isinstance(ids,list) or len(ids)>MAX_REFERENCES or any(not isinstance(x,str) or x not in catalog for x in ids) or len(set(ids))!=len(ids):
        raise ValueError('Select up to four valid image references from this conversation.')
    # Canonical chronological order; attachments retain their original positions.
    # A generated result follows the attachments of the same turn.
    ordered=sorted(ids,key=lambda id:(catalog[id][0],catalog[id][1] is None,catalog[id][1] or 0))
    result=[];total=0
    for id in ordered:
        n,i,_=catalog[id]
        if i is None:raw=chat_history.generated_image(chat,n)
        else:
            parts=chat_history.content(chat,n)
            media=[p for p in parts if p.get('type')!='text'] if isinstance(parts,list) else []
            if i>len(media) or media[i-1].get('type')!='image_url':raise ValueError('Image reference is unavailable.')
            url=media[i-1].get('image_url',{}).get('url','')
            if not url.startswith('data:image/') or ';base64,' not in url:raise ValueError('Invalid stored image reference.')
            raw=base64.b64decode(url.split(',',1)[1],validate=True)
        if not raw or len(raw)>MAX_REFERENCE_BYTES:raise ValueError('Image references must be at most 20 MiB each.')
        total+=len(raw)
        if total>40*1024*1024:raise ValueError('Image references exceed the 40 MiB total limit.')
        result.append(raw)
    return result

def prepare_references(references,directory):
    from PIL import Image,ImageOps
    paths=[]
    for i,raw in enumerate(references,1):
        with Image.open(io.BytesIO(raw)) as img:
            if img.width*img.height>32_000_000:raise ValueError('Reference image exceeds 32 megapixels.')
            img=ImageOps.exif_transpose(img).convert('RGB')
            path=directory/f'reference-{i}.png'
            img.save(path,format='PNG')
            paths.append(path)
    return paths

def active_loras(c):
    return [entry for entry in c.get('loras',[]) if entry['enabled'] and entry['strength']!=0]

def prepare_loras(c,directory):
    adapters=active_loras(c)
    if not adapters:return
    directory.mkdir()
    for i,entry in enumerate(adapters,1):
        path=pathlib.Path(entry['path'])
        (directory/f'quantru_lora_{i}{path.suffix.lower()}').symlink_to(path)

def command(c,prompt,output,references=()):
    adapters=active_loras(c)
    # LoRA selection belongs to settings, not model-generated prompt text.
    prompt=re.sub(r'<lora:[^>]*>','',prompt,flags=re.I)
    for i,entry in enumerate(adapters,1):
        prompt+=f" <lora:quantru_lora_{i}:{entry['strength']:g}>"

    seed=c['seed'] if c['seed']>=0 else secrets.randbelow(2**31)
    cmd=[str(CLI),'--diffusion-model',c['diffusion'],'--llm',c['encoder'],'--vae',c['vae'],
         '-p',prompt,'-W',str(c['width']),'-H',str(c['height']),'--steps',str(c['steps']),
         '--cfg-scale',str(c['cfg']),'--scheduler',c['scheduler'],'--sampling-method',c['sampler'],
         '--seed',str(seed),'--backend',f"diffusion=vulkan0,te={c['encoder_backend']},vae=vulkan0",
         '-o',str(output)]
    cmd+=['--offload-to-cpu'] if c['weight_mode']=='offload' else ['--auto-fit','on']
    if c['mmap']:cmd.append('--mmap')
    if c['vae_tiling']:cmd+=['--vae-tiling','--vae-tile-size',str(c['vae_tile_size'])]
    if c['threads']:cmd+=['--threads',str(c['threads'])]
    if adapters:cmd+=['--lora-model-dir',str(pathlib.Path(output).parent/'loras'),'--lora-apply-mode',c['lora_apply_mode']]
    if references:
        projector=image_settings.reference_projector(c)
        if projector:cmd+=['--llm_vision',projector]
        if c.get('clip_vision'):cmd+=['--clip_vision',c['clip_vision']]
        for reference in references:cmd+=['-r',str(reference)]
    return cmd

class GenerationProgress:
    """Read the native CLI sampling progress, not a simulated timer."""
    STEP=re.compile(r'\|\s*(\d+)\s*/\s*(\d+)\s*-\s*([0-9]+(?:\.[0-9]+)?)\s*(s/it|it/s)')
    def __init__(self):
        self.phase='Preparing image'
        self.step=0
        self.total=0
        self.samples=[]
        self.updated=time.monotonic()
        self.buffer=''
    def feed(self,data,now=None):
        now=time.monotonic() if now is None else now
        self.buffer+=data
        # Upstream flushes each console progress update with ESC[K, but
        # intermediate steps have no trailing newline until the next update.
        lines=re.split(r'(?:[\r\n]|\x1b\[K)+',self.buffer)
        self.buffer=lines.pop()
        for line in lines:
            lower=line.lower()
            if 'generating image:' in lower or 'sampling using' in lower or 'sampling started:' in lower:
                self.phase='Generating image'
                self.step=self.total=0
                self.samples=[]
                self.updated=now
            elif 'sampling completed' in lower or 'generating 1 latent images completed' in lower or re.search(r'decoding \d+ latents',lower):
                self.phase='Decoding image'
            elif 'generate_image completed' in lower:
                self.phase='Finalizing image'
            elif self.phase=='Generating image':
                match=self.STEP.search(line)
                if match:
                    step,total=int(match[1]),int(match[2])
                    value=float(match[3])
                    if value>0 and 0<step<=total and step>self.step:
                        self.step,self.total=step,total
                        self.samples.append(value if match[4]=='s/it' else 1/value)
                        self.updated=now
    def label(self,now=None):
        if self.phase!='Generating image' or not self.samples:
            return self.phase+'…'
        if self.step>=self.total:
            return 'Decoding image…'
        now=time.monotonic() if now is None else now
        recent=self.samples[-3:]
        average=sum(recent)/len(recent)
        # Estimate only the remaining sampling work. VAE decoding is a separate phase.
        remaining=max(1,round(average*(self.total-self.step)-max(0,now-self.updated)))
        eta=f'{remaining//60}m {remaining%60:02d}s' if remaining>=60 else f'{remaining}s'
        return f'Generating image… {self.step}/{self.total} · ~{eta} sampling remaining'

def generate(args,progress,references=()):
    global child
    prompt=args.get('prompt')
    if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>12000 or '\0' in prompt:
        raise ValueError('Invalid image prompt.')
    if not available():raise RuntimeError('Image backend or model files unavailable.')
    c=image_settings.load()
    env=os.environ.copy()
    env['GGML_VK_VISIBLE_DEVICES']='0'
    env['LD_LIBRARY_PATH']=str(CLI.parent)+':'+env.get('LD_LIBRARY_PATH','')
    if c['compatibility']:env.update(GGML_VK_MAX_NODES_PER_SUBMIT='4',GGML_VK_SERIALIZE_SUBMISSIONS='1')
    with tempfile.TemporaryDirectory(prefix='quantru-image-',dir=ROOT) as tmp:
        output=pathlib.Path(tmp)/'image.png'
        log=pathlib.Path(tmp)/'generation.log'
        prepare_loras(c,output.parent/'loras')
        paths=prepare_references(references,output.parent)
        cmd=command(c,prompt,output,paths)
        with log.open('wb') as f:
            with lock:child=subprocess.Popen(cmd,cwd=tmp,env=env,stdout=f,stderr=subprocess.STDOUT)
            try:
                deadline=time.monotonic()+600
                tracker=GenerationProgress()
                with log.open('r',errors='replace',newline='') as reader:
                    while child.poll() is None:
                        if time.monotonic()>deadline:raise RuntimeError('Image generation timed out.')
                        tracker.feed(reader.read())
                        progress(tracker.label())
                        time.sleep(1)
                if child.returncode or not output.is_file():
                    with log.open('rb') as lf:
                        lf.seek(max(0,log.stat().st_size-1800));detail=lf.read().decode(errors='replace')
                    print('Image generation failed:',detail,flush=True)
                    raise RuntimeError('Image generation failed. Check the local backend log.')
                data=output.read_bytes()
                if not data.startswith(b'\x89PNG\r\n\x1a\n') or len(data)>20*1024*1024:
                    raise RuntimeError('Invalid generated image.')
                engine_updates.confirmed('image')
                return data
            except RuntimeError:
                stop()
                engine_updates.rejected('image')
                raise
            finally:
                stop()
                with lock:child=None
