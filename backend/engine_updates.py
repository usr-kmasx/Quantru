"""Independent, transactional Vulkan release updates. No model downloads."""
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import tarfile
import tempfile
import threading
import time
import urllib.request
import zipfile

ROOT=pathlib.Path(__file__).resolve().parent
INTERVAL=3*24*3600
SPECS={
    'image': ('leejet/stable-diffusion.cpp', ROOT/'stable-diffusion.cpp', 'sd-cli'),
    'audio': ('0xShug0/audio.cpp', ROOT/'voice/native', 'audiocpp_cli'),
}
lock=threading.RLock()
state_file=ROOT/'engine-updates.json'
def state():
    try:return json.loads(state_file.read_text())
    except (OSError,ValueError):return {}
def save_state(data):
    with tempfile.NamedTemporaryFile(mode='w',dir=ROOT,delete=False) as f:
        tmp=pathlib.Path(f.name);json.dump(data,f,indent=2)
    tmp.replace(state_file)
def backup(kind):
    active=SPECS[kind][1]
    return active.with_name(active.name+'.previous')
def recover():
    for kind,(_,active,_) in SPECS.items():
        prev=backup(kind)
        if not active.exists() and prev.is_dir():
            prev.rename(active)
def run(path,args,timeout=25):
    env={**os.environ,'LD_LIBRARY_PATH':str(path.parent),'GGML_VK_VISIBLE_DEVICES':'0'}
    p=subprocess.run([str(path),*args],cwd=path.parent,env=env,stdout=subprocess.PIPE,
                     stderr=subprocess.STDOUT,text=True,timeout=timeout)
    if p.returncode:raise RuntimeError(f'{path.name} {args}: {p.stdout[-800:]}')
    return p.stdout
def version(kind, folder=None):
    _,active,binary=SPECS[kind]
    out=run((folder or active)/binary,['--version'])
    if kind=='image':
        m=re.search(r'master-(\d+)-([0-9a-f]+)',out)
        if m:return (int(m[1]),),m[0]
        # Official builds sometimes report only their commit. Keep the
        # verified release tag beside the binary, and match the actual hash.
        marker=(folder or active)/'.quantru-release'
        if marker.is_file():
            tag=marker.read_text().strip()
            release_match=re.fullmatch(r'master-(\d+)-([0-9a-f]+)',tag)
            commit=re.search(r'commit ([0-9a-f]+)',out)
            if release_match and commit and commit[1]==release_match[2]:
                return (int(release_match[1]),),tag
    else:
        m=re.search(r'audio\.cpp\s+(\d+\.\d+\.\d+)',out)
        if m:return tuple(map(int,m[1].split('.'))),'v'+m[1]
    raise RuntimeError('Unrecognized installed version')
def release(kind):
    repo=SPECS[kind][0]
    req=urllib.request.Request('https://api.github.com/repos/'+repo+'/releases?per_page=10',
                               headers={'User-Agent':'Quantru','Accept':'application/vnd.github+json'})
    with urllib.request.urlopen(req,timeout=20) as r: releases=json.load(r)
    candidates=[]
    for rel in releases:
        if rel['draft'] or rel['prerelease']:continue
        tag=rel['tag_name']
        if kind=='image':
            match=re.fullmatch(r'master-(\d+)-[0-9a-f]+',tag)
            if not match:continue
            key=(int(match[1]),)
            assets=[a for a in rel['assets'] if re.fullmatch(r'sd-master-[0-9a-f]+-bin-Linux-Ubuntu-[0-9.]+-x86_64-vulkan\.zip',a['name'])]
            assets.sort(key=lambda a:'24.04' not in a['name'])
        else:
            match=re.fullmatch(r'v(\d+\.\d+\.\d+)',tag)
            if not match:continue
            key=tuple(map(int,match[1].split('.')))
            assets=[a for a in rel['assets'] if a['name']==f'audio-{tag}-bin-ubuntu-x64-vulkan.tar.gz']
        if assets:candidates.append((key,tag,assets[0]))
    if not candidates:raise RuntimeError('No compatible official Vulkan release found')
    return max(candidates,key=lambda x:x[0])
def unpack(archive,dest):
    dest.mkdir()
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as z:
            for entry in z.infolist():
                if not (dest/entry.filename).resolve().is_relative_to(dest.resolve()):
                    raise ValueError('Unsafe ZIP path')
                if (entry.external_attr>>16)&0o170000==0o120000:raise ValueError('Unexpected ZIP symlink')
                z.extract(entry,dest)
                if not entry.is_dir():
                    mode=(entry.external_attr>>16)&0o777
                    if mode: (dest/entry.filename).chmod(mode)
    else:
        with tarfile.open(archive) as t:t.extractall(dest,filter='data')
def prepare(kind,key,tag,asset,tmp):
    digest=asset.get('digest','')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}',digest):raise ValueError('Release lacks SHA-256')
    archive=tmp/'release'
    subprocess.run(['curl','-fL','--retry','2','--connect-timeout','15','--max-time','180','-sS',
                    '-o',str(archive),asset['browser_download_url']],check=True,timeout=200)
    with archive.open('rb') as f:
        if 'sha256:'+hashlib.file_digest(f,'sha256').hexdigest()!=digest:
            raise ValueError('Release checksum mismatch')
    unpack(archive,tmp/'unpacked')
    binary=SPECS[kind][2]
    matches=[p for p in (tmp/'unpacked').rglob(binary) if p.is_file() and not p.is_symlink()]
    if len(matches)!=1 or not matches[0].is_file():raise ValueError('Missing/ambiguous CLI')
    exe=matches[0]
    exe.chmod(exe.stat().st_mode|0o111)
    folder=exe.parent
    if kind=='image':
        # Metadata is only accepted after the archive checksum is verified.
        (folder/'.quantru-release').write_text(tag+'\n')
    if version(kind,folder)[0]!=key:raise ValueError('Binary version mismatch')
    help_text=run(exe,['--help'])
    required=('--diffusion-model','--llm_vision','--clip_vision','--backend','--offload-to-cpu','--auto-fit','--lora-apply-mode','--vae-tile-size','--sampling-method','--scheduler','--mmap') if kind=='image' else ('--task','--family','--backend','--session-option','--text-out','--out','--audio','--mode')
    if any(opt not in help_text for opt in required):raise ValueError('Incompatible CLI arguments')
    return folder
def check(kind,guard,idle,enabled):
    _,active,binary=SPECS[kind]
    prev=backup(kind)
    if prev.exists():return  # Wait for first real inference before another update.
    key,installed=version(kind)
    newest,tag,asset=release(kind)
    if newest<=key:
        print(f'{kind} engine up to date: {installed}',flush=True);return
    with lock:
        if state().get(kind,{}).get('rejected')==tag:return
    with tempfile.TemporaryDirectory(prefix='.engine-update-',dir=active.parent) as raw:
        folder=prepare(kind,newest,tag,asset,pathlib.Path(raw))
        # Download and static validation do not block inference. Only probe/swap when idle.
        for _ in range(600):
            with guard:
                if not enabled():return
                if idle():
                    devices=run(folder/binary,['--list-devices'])
                    if 'vulkan' not in devices.lower():raise RuntimeError('Vulkan device unavailable')
                    with lock:
                        if prev.exists():return
                        active.rename(prev)
                        try:folder.rename(active)
                        except BaseException:
                            prev.rename(active);raise
                        print(f'{kind} engine installed: {tag}; previous retained until successful inference',flush=True)
                    return
            time.sleep(1)
        print(f'{kind} engine update deferred: server busy',flush=True)
def confirmed(kind):
    with lock:
        prev=backup(kind)
        if prev.is_dir():
            try:shutil.rmtree(prev);print(f'{kind} engine validated; previous removed',flush=True)
            except OSError as e:print('Engine cleanup deferred:',e,flush=True)
def rejected(kind):
    # Called after the new executable has stopped, never during another inference.
    with lock:
        prev=backup(kind);active=SPECS[kind][1]
        if not prev.is_dir():return
        try:
            _,tag=version(kind)
            data=state();data.setdefault(kind,{})['rejected']=tag;save_state(data)
            with tempfile.TemporaryDirectory(prefix='.engine-rollback-',dir=active.parent) as tmp:
                failed=pathlib.Path(tmp)/'failed'
                active.rename(failed)
                try:prev.rename(active)
                except BaseException:failed.rename(active);raise
            print(f'{kind} engine reverted after inference failure: {tag}',flush=True)
        except Exception as e:print('Engine rollback failed:',e,flush=True)
def loop(kind,guard,idle,enabled):
    checked=False
    while True:
        try:
            if kind=='image':
                if not enabled():checked=False
                due=enabled() and not checked
            else:
                with lock: last=state().get(kind,{}).get('last_check',0)
                due=time.time()-last>=INTERVAL
            if due:
                if kind=='audio':
                    with lock:
                        data=state();data.setdefault(kind,{})['last_check']=time.time();save_state(data)
                checked=True
                check(kind,guard,idle,enabled)
        except Exception as e:print(f'{kind} engine update failed; current version preserved: {e}',flush=True)
        time.sleep(15)
