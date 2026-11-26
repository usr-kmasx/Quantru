"""Fresh-user bootstrap: pinned public models and official Vulkan release packages."""
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.parse

ROOT=pathlib.Path(__file__).resolve().parent
BACKEND=ROOT/'backend'
APP_ID='io.github.quantru.App'
# repo, immutable revision, upstream path, local path, SHA-256, bytes.
MODELS=[
 ('Inworld/voice-isolator','9b0285b3fe8403aa8e2f1dbb2165a80a4294c970','denoiser.safetensors','voice/models/denoiser.safetensors','647335a6aeb4dc706b895532c209d51e0e84a4849d17b339f00d4392a050ae53',256260128),
 ('audio-cpp/audio.cpp-gguf','dac3915042a8ddfbb79f87b108214fda57e4b753','Parakeet-TDT-0.6B-v3-GGUF/parakeet-tdt-0.6b-v3-q8_0.gguf','voice/models/parakeet-tdt-0.6b-v3-q8_0.gguf','6fa498f10f8cb606f041aa9512733cfee842a932359b00b0c45b9b723c4f4f4b',915735760),
]
def check():
    if sys.version_info < (3,12):raise RuntimeError('Python 3.12 or newer is required.')
    import gi
    gi.require_version('Gtk','4.0')
    gi.require_version('Adw','1')
    gi.require_version('WebKit','6.0')
    from gi.repository import Gtk,Adw,WebKit
    for module,attribute in [(Gtk,'FileDialog'),(Gtk,'WindowControls'),(Adw,'AlertDialog'),(WebKit,'NetworkSession')]:
        if not hasattr(module,attribute):raise RuntimeError('Missing required API: '+attribute)
    import sqlite3
    with sqlite3.connect(':memory:') as db:db.execute('CREATE VIRTUAL TABLE test USING fts5(content)')
    print('PASS: Python, GTK4, libadwaita, WebKitGTK 6, SQLite FTS5.',flush=True)
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def download_models():
    remaining=0
    for _,_,_,local,_,size in MODELS:
        path=BACKEND/local
        if not path.exists():remaining+=max(0,size-(path.with_suffix(path.suffix+'.part').stat().st_size if path.with_suffix(path.suffix+'.part').exists() else 0))
    if shutil.disk_usage(BACKEND).free < remaining+1024**3:
        raise RuntimeError('Insufficient free space for model and engine downloads.')
    for repo,rev,name,local,digest,size in MODELS:
        path=BACKEND/local;path.parent.mkdir(parents=True,exist_ok=True)
        if path.is_file() and path.stat().st_size==size and sha(path)==digest:
            print('Verified:',path.name,flush=True);continue
        if path.exists():raise RuntimeError('Unexpected existing file: '+str(path))
        part=path.with_suffix(path.suffix+'.part')
        url=f'https://huggingface.co/{repo}/resolve/{rev}/'+urllib.parse.quote(name,safe='/')
        print('Downloading:',name,flush=True)
        if not part.exists() or part.stat().st_size!=size:
            subprocess.run(['curl','--fail','--location','--retry','3','--connect-timeout','20','--continue-at','-','--output',str(part),url],check=True)
        if part.stat().st_size!=size or sha(part)!=digest:
            part.unlink(missing_ok=True)
            raise RuntimeError('Model integrity check failed: '+name+'; rerun to download again.')
        part.replace(path)
def install_engines():
    from backend import engine,engine_updates as updates
    llama=engine.current()
    if llama is None:llama=engine.update()
    # Detect loader/ABI issues and actual Vulkan device access without loading weights.
    devices=updates.run(llama/'llama-server',['--list-devices'])
    if 'vulkan' not in devices.lower():raise RuntimeError('llama.cpp: no Vulkan device.')
    for kind,(_,active,binary) in updates.SPECS.items():
        if not active.exists():
            active.parent.mkdir(parents=True,exist_ok=True)
            key,tag,asset=updates.release(kind)
            print('Installing official Vulkan engine:',tag,flush=True)
            with tempfile.TemporaryDirectory(prefix='.install-engine-',dir=active.parent) as t:
                folder=updates.prepare(kind,key,tag,asset,pathlib.Path(t))
                if 'vulkan' not in updates.run(folder/binary,['--list-devices']).lower():
                    raise RuntimeError(kind+': no Vulkan device.')
                folder.rename(active)
        updates.version(kind)
        if 'vulkan' not in updates.run(active/binary,['--list-devices']).lower():raise RuntimeError(kind+': no Vulkan device.')
    (BACKEND/'voice/native-ready').touch()
def register_desktop():
    data=pathlib.Path(os.environ.get('XDG_DATA_HOME',str(pathlib.Path.home()/'.local/share')))
    icon=data/'icons/hicolor/scalable/apps'/(APP_ID+'.svg')
    desktop=data/'applications'/(APP_ID+'.desktop')
    icon.parent.mkdir(parents=True,exist_ok=True);desktop.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(ROOT/'web/logo.svg',icon)
    executable=str(ROOT/'run.sh')
    escaped=executable.replace('\\','\\\\').replace('"','\\"').replace('$','\\$').replace('`','\\`').replace('%','%%')
    desktop.write_text('[Desktop Entry]\nType=Application\nName=Quantru\nComment=Local multimodal AI\nExec="'+escaped+'"\nIcon='+APP_ID+'\nTerminal=false\nCategories=Utility;\nStartupNotify=true\nStartupWMClass='+APP_ID+'\n')
    desktop.chmod(0o644);icon.chmod(0o644)
def install():
    if not (ROOT/'.installing').is_file():raise RuntimeError('Use install.sh to create a separate installation.')
    check()
    install_engines()
    download_models()
    from backend import settings,image_settings,voice_capture,chat_history
    settings.load()
    image_settings.load()
    if not voice_capture.available():raise RuntimeError('Voice backend unavailable.')
    chat_history.init()
    register_desktop()
    print('PASS: clean defaults, model integrity, engines, history and desktop entry.',flush=True)
if __name__=='__main__':
    try:
        if sys.argv[1:]==['--check']:check()
        elif sys.argv[1:]==['--install']:install()
        else:raise ValueError('Use install.sh.')
    except Exception as e:
        print('Installation error:',e,file=sys.stderr);sys.exit(1)
