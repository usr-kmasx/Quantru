import time, urllib.error
import hashlib, json, os, pathlib, re, subprocess, tarfile, tempfile, threading, urllib.request, shutil
try:
    from . import settings
except ImportError:
    import settings
ROOT = pathlib.Path(__file__).resolve().parent
PORT = 8766
API = 'https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=10'
def current():
    p = ROOT / 'current'
    return p.resolve() if p.is_symlink() and p.exists() else None
release_lock=threading.RLock()

def update():
    with release_lock:return _update()

def _update():
    req = urllib.request.Request(API, headers={'User-Agent':'Quantru'})
    with urllib.request.urlopen(req, timeout=20) as r:
        releases = json.load(r)
    candidates = [(int(r['tag_name'][1:]), r, a) for r in releases if re.fullmatch(r'b[0-9]+',r['tag_name']) and not r['draft'] for a in r['assets'] if a['name'].endswith('-bin-ubuntu-vulkan-x64.tar.gz')]
    _, release, asset = max(candidates, key=lambda x:x[0])
    tag = release['tag_name']
    old = current()
    if old and re.fullmatch(r'b[0-9]+', old.name) and int(old.name[1:]) >= int(tag[1:]):
        print('llama.cpp up to date:', old.name, flush=True)
        return old
    dest = ROOT / tag
    if not dest.exists():
        with tempfile.TemporaryDirectory(dir=ROOT) as tmp:
            tmp = pathlib.Path(tmp)
            archive = tmp / 'release.tar.gz'
            subprocess.run(['curl','-fL','--retry','3','--retry-delay','1','--connect-timeout','10','--max-time','120','-sS','-o',str(archive),asset['browser_download_url']],check=True)
            if asset.get('digest'):
                actual = hashlib.file_digest(archive.open('rb'),'sha256').hexdigest()
                if asset['digest'] != 'sha256:'+actual: raise RuntimeError('Release checksum mismatch')
            unpack = tmp / 'unpack'
            unpack.mkdir()
            with tarfile.open(archive) as t: t.extractall(unpack, filter='data')
            binary = next(unpack.rglob('llama-server'))
            binary.chmod(binary.stat().st_mode | 0o111)
            env = os.environ.copy()
            env['LD_LIBRARY_PATH'] = str(binary.parent) + ':' + env.get('LD_LIBRARY_PATH','')
            subprocess.run([str(binary),'--version'], env=env, check=True, timeout=20)
            binary.parent.rename(dest)
    if not (dest/'llama-server').is_file(): raise RuntimeError('Missing server')
    link = ROOT / '.current-next'
    link.unlink(missing_ok=True)
    link.symlink_to(tag)
    link.replace(ROOT/'current')
    print('llama.cpp available:',tag,flush=True)
    return dest
def prune_obsolete(confirmed):
    """Remove older installed releases only after the selected release is healthy."""
    with release_lock:
        if current()!=confirmed or not re.fullmatch(r'b[0-9]+',confirmed.name):return
        old=[p for p in ROOT.iterdir() if p.is_dir() and not p.is_symlink()
             and re.fullmatch(r'b[0-9]+',p.name) and int(p.name[1:])<int(confirmed.name[1:])
             and (p/'llama-server').is_file()]
        if not old:return
        # Keep a release used by any running local llama process, including
        # executables and shared libraries. If inspection is denied, keep it.
        protected=set()
        for proc in pathlib.Path('/proc').glob('[0-9]*'):
            try:
                if proc.stat().st_uid!=os.getuid():continue
                name=(proc/'comm').read_text().strip()
            except OSError:continue
            relevant='llama' in name or 'ggml' in name
            try:
                exe=(proc/'exe').readlink()
                for p in old:
                    if exe.is_relative_to(p):protected.add(p)
                if relevant or 'llama' in exe.name or 'ggml' in exe.name:
                    maps=(proc/'maps').read_text(errors='replace')
                    for p in old:
                        if str(p)+'/' in maps:protected.add(p)
            except FileNotFoundError:continue
            except PermissionError:
                if relevant:return
            except OSError:
                if relevant:return
        for p in old:
            if p in protected:continue
            try:
                shutil.rmtree(p)
                print('Removed obsolete llama.cpp:',p.name,flush=True)
            except OSError as e:print('Release cleanup deferred:',e,flush=True)

def check_update():
    try: update()
    except Exception as e: print('Update check failed:',e,flush=True)
def speculative_args(c):
    method = c['spec_method']
    args = ['--spec-type', method]
    if method != 'none':
        args += ['--spec-draft-n-max', str(c['draft_tokens']), '--spec-draft-n-min', str(c['draft_min'])]
        if c['draft_model']:
            args += ['--spec-draft-model', c['draft_model']]
    return args

active_profile = None
def start(config=None, check_updates=True):
    global active_profile
    active_profile = None
    c = settings.validate(config if config is not None else settings.load())
    if not c['model']:raise ValueError('Choose a chat model in llama.cpp settings first.')
    model = pathlib.Path(c['model'])
    mmproj = pathlib.Path(c['mmproj']) if c['mmproj'] else None
    version = current()
    if version is None: version = update()
    elif check_updates and c['auto_update']: threading.Thread(target=check_update,daemon=True).start()
    env = os.environ.copy()
    env['LD_LIBRARY_PATH'] = str(version) + ':' + env.get('LD_LIBRARY_PATH','')
    env['GGML_VK_VISIBLE_DEVICES'] = '0'
    base = [str(version/'llama-server'),'-m',str(model),'--host','127.0.0.1','--port',str(PORT),'-c',str(c['context']),'-np','1','-fa',c['flash_attention'],'-ctk',c['cache_k'],'-ctv',c['cache_v'],'-b',str(c['batch']),'-ub',str(c['ubatch']),'-t',str(c['threads']),'-tb',str(c['threads_batch']),'--reasoning','auto','--reasoning-budget',str(c['reasoning_budget']),'--cache-prompt' if c['cache_prompt'] else '--no-cache-prompt']
    if mmproj:
        base += ['--mmproj',str(mmproj)]
        if not c['mmproj_offload']: base += ['--no-mmproj-offload']
    else: base += ['--no-mmproj']
    base += speculative_args(c)
    # Reserve room for Vulkan compute, KV cache, projector and desktop.
    required = model.stat().st_size + (mmproj.stat().st_size if mmproj and c['mmproj_offload'] else 0) + 1024**3
    if c['spec_method'] != 'none' and c['draft_model']:
        required += pathlib.Path(c['draft_model']).stat().st_size
    free = None
    for total in pathlib.Path('/sys/class/drm').glob('card*/device/mem_info_vram_total'):
        try:
            capacity = int(total.read_text())
            if capacity >= 4 * 1024**3:
                available = capacity - int(total.with_name('mem_info_vram_used').read_text())
                free = available if free is None else max(free, available)
        except (OSError, ValueError):
            pass
    profiles = []
    if c['gpu_mode'] == 'vram-first' and (free is None or free >= required):
        profiles.append(('VRAM-first', ['-ngl','all','-fit','off','-ot',r'^(per_layer_token_embd|token_embd)\.weight$=Vulkan0']))
    elif c['gpu_mode'] == 'vram-first':
        print(f'VRAM-first skipped: available {free/1024**3:.2f} GiB, estimated requirement {required/1024**3:.2f} GiB',flush=True)
    profiles.append(('automatic hybrid fallback', ['-ngl','auto','-fit','on','-fitt',str(c['gpu_margin'])]))
    for name, options in profiles:
        if c['spec_method'] != 'none':
            options += ['--spec-draft-ngl', 'all' if name == 'VRAM-first' else 'auto']
        print('Loading profile:', name, flush=True)
        process = subprocess.Popen(base+options,env=env,cwd=ROOT)
        try:
            for _ in range(240):
                if process.poll() is not None:
                    raise RuntimeError(f'llama-server exited: {process.returncode}')
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health',timeout=1) as r:
                        if r.status == 200:
                            print('Active profile:',name,flush=True)
                            active_profile = name
                            prune_obsolete(version)
                            return process
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(.5)
            raise RuntimeError('Model loading timed out')
        except Exception as e:
            print(name,'failed:',e,flush=True)
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
    raise RuntimeError('All loading profiles failed')
if __name__ == '__main__':
    update()
