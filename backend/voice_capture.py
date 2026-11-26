"""Native Vulkan voice isolation with recorded PCM and volatile audio output."""
import base64
import json
import math
import os
import pathlib
import secrets
import struct
import subprocess
import tempfile
import threading
import time
from . import engine_updates

ROOT = pathlib.Path(__file__).resolve().parent / 'voice'
NATIVE = ROOT / 'native'
CLI = NATIVE / 'audiocpp_cli'
MODEL = ROOT / 'models/denoiser.safetensors'
STT = ROOT / 'models/parakeet-tdt-0.6b-v3-q8_0.gguf'
lock = threading.RLock()
session = None

def available():
    return CLI.is_file() and MODEL.is_file() and STT.is_file() and (ROOT/'native-ready').is_file()

def close():
    global session
    old, session = session, None
    if not old: return
    p = old['process']
    try:
        if p is None: return
        if p.poll() is None:
            p.terminate()
            try: p.wait(3)
            except subprocess.TimeoutExpired: p.kill(); p.wait()
        if p.stdin and not p.stdin.closed: p.stdin.close()
    finally:
        old['log'].close()
        old['tmp'].cleanup()

def error_detail(s):
    f=s['log']
    f.seek(max(0,os.fstat(f.fileno()).st_size-4096))
    return f.read().decode(errors='replace').strip()[-1000:]

def handle(op, data):
    global session
    with lock:
        if session and time.monotonic()-session['last'] > 90: close()
        if op == 'start':
            if not available(): raise RuntimeError('Vulkan voice isolator is unavailable')
            if session: raise RuntimeError('Another recording is active')
            tmp=tempfile.TemporaryDirectory(prefix='quantru-voice-',dir='/dev/shm')
            output=pathlib.Path(tmp.name)/'isolated.wav'
            log=os.fdopen(os.memfd_create('quantru-voice-log'),'w+b')
            token=secrets.token_urlsafe(24)
            session={'id':token,'process':None,'pcm':bytearray(),'last':time.monotonic(),'start':time.monotonic(),
                     'samples':0,'tmp':tmp,'output':output,'log':log}
            return {'id':token}
        if not session or not secrets.compare_digest(str(data.get('id','')),session['id']):
            raise ValueError('No matching recording')
        s=session
        s['last']=time.monotonic()
        if op=='cancel':
            close()
            return {'cancelled':True}
        try:
            p=s['process']
            if op=='push':
                raw=base64.b64decode(data['pcm'],validate=True)
                if not raw or len(raw)%4 or len(raw)>48000*4 or s['samples']+len(raw)//4>48000*60:
                    raise ValueError('Invalid audio chunk or recording exceeds 60 seconds')
                if any(not math.isfinite(v[0]) for v in struct.iter_unpack('<f',raw)):
                    raise ValueError('Invalid PCM')
                s['pcm'].extend(raw)
                s['samples']+=len(raw)//4
                s['last']=time.monotonic()
                return {'samples':s['samples']}
            if op=='finish':
                if not s['samples']: raise ValueError('No recorded audio')
                source=pathlib.Path(s['tmp'].name)/'recorded.wav'
                subprocess.run(['ffmpeg','-v','error','-f','f32le','-ar','48000','-ac','1','-i','pipe:0','-c:a','pcm_f32le',str(source)],input=s['pcm'],check=True,timeout=15)
                s['pcm'].clear()
                cmd=[str(CLI),'--task','s2s','--mode','offline','--family','voice_isolator',
                     '--model',str(MODEL),'--backend','vulkan','--device','0','--threads','6',
                     '--audio',str(source),'--out',str(s['output']),'--log']
                started=time.monotonic()
                p=subprocess.Popen(cmd,stdout=s['log'],stderr=s['log'],
                    env={**os.environ,'LD_LIBRARY_PATH':str(NATIVE)},cwd=NATIVE)
                s['process']=p
                if p.wait(timeout=120)!=0: raise RuntimeError('Vulkan isolation failed: '+error_detail(s))
                isolation_seconds=time.monotonic()-started
                # Release the isolator before loading the dedicated STT model.
                transcript=pathlib.Path(s['tmp'].name)/'transcript.txt'
                log=s['log']
                log.seek(0)
                log.truncate()
                cmd=[str(CLI),'--task','asr','--mode','offline','--family','parakeet_tdt',
                     '--model',str(STT),'--backend','vulkan','--device','0','--threads','6',
                     '--audio',str(s['output']),'--text-out',str(transcript),
                     '--session-option','parakeet_tdt.offline_mode=auto','--log']
                started=time.monotonic()
                p=subprocess.Popen(cmd,stdout=log,stderr=log,
                    env={**os.environ,'LD_LIBRARY_PATH':str(NATIVE)},cwd=NATIVE)
                s['process']=p
                if p.wait(timeout=120)!=0: raise RuntimeError('Transcription failed: '+error_detail(s))
                result={'text':transcript.read_text().strip(),'seconds':s['samples']/48000,
                        'isolation_seconds':isolation_seconds,'stt_seconds':time.monotonic()-started,
                        'wall_seconds':time.monotonic()-s['start']}
                close()
                engine_updates.confirmed('audio')
                return result
            raise ValueError('Unknown recording action')
        except Exception as e:
            close()
            if op=='finish' and isinstance(e,(RuntimeError,subprocess.TimeoutExpired)):
                engine_updates.rejected('audio')
            raise

def cleanup_loop():
    while True:
        time.sleep(10)
        with lock:
            if session and time.monotonic()-session['last']>90: close()

