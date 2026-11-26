#!/usr/bin/env python3
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import hashlib, os
import json, urllib.request, urllib.error, threading, signal, time
from backend import engine, settings, voice_capture, chat_history, context_memory, image_generation, image_settings, reasoning, shell_tool, mobile_access, chat_sync, engine_updates, token_stats
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent / 'web'
HOST, PORT = '127.0.0.1', 8765
config = settings.load()
state_lock = threading.RLock()
active_requests = 0
loading = False
image_busy = False
process = None
IDLE_TIMEOUT = 15 * 60
last_activity = time.monotonic()
sleeping = True
first_wake = True

def stop_engine(p):
    if p is not None and p.poll() is None:
        p.terminate()
        try: p.wait(timeout=10)
        except Exception:
            p.kill()
            p.wait()

def unload_if_idle():
    global process, sleeping, loading
    with state_lock:
        if (loading or active_requests or image_busy or voice_capture.session
                or process is None or process.poll() is not None
                or time.monotonic()-last_activity < IDLE_TIMEOUT):
            return False
        loading = True
        try:
            stop_engine(process)
            process = None
            engine.active_profile = None
            sleeping = True
            print('Chat model unloaded after inactivity.', flush=True)
            return True
        finally:
            loading = False

def idle_loop():
    while True:
        time.sleep(1)
        try:
            unload_if_idle()
        except Exception as e:
            print('Idle unload failed:', e, flush=True)

def settings_info():
    version = engine.current()
    return {'config': config, 'defaults': settings.DEFAULTS,
            'runtime': sorted(settings.RUNTIME),
            'version': version.name if version else None,
            'profile': engine.active_profile,
            'loading': loading}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('X-Content-Type-Options','nosniff')
        super().end_headers()

    def json_response(self, status, data):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def apply_settings(self):
        global config, loading, process, sleeping, last_activity
        origin = self.headers.get('Origin')
        if origin and origin != f'http://{self.headers.get("Host")}':
            return self.json_response(403, {'error':'Origin not allowed'})
        if self.headers.get_content_type() != 'application/json':
            return self.json_response(415, {'error':'Expected JSON'})
        try:
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 65536: raise ValueError('Invalid payload size')
            candidate = settings.validate(json.loads(self.rfile.read(length)))
        except (ValueError, TypeError, OSError) as e:
            return self.json_response(400, {'error':str(e)})
        with state_lock:
            if loading or active_requests or voice_capture.session:
                return self.json_response(409, {'error':'Wait until generation or loading finishes.'})
            old = config
            changed = {k for k in candidate if candidate[k] != old[k]}
            restart = bool(changed - settings.RUNTIME)
            if not restart or sleeping:
                try:
                    config = settings.save(candidate)
                    return self.json_response(200, settings_info())
                except OSError as e:
                    return self.json_response(500, {'error':str(e)})
            if not candidate['model']:
                try:
                    config = settings.save(candidate)
                    stop_engine(process)
                    process = None
                    engine.active_profile = None
                    sleeping = True
                    return self.json_response(200, settings_info())
                except OSError as e:
                    return self.json_response(500, {'error':str(e)})
            loading = True
            sleeping = False
        try:
            stop_engine(process)
            process = engine.start(candidate, check_updates=False)
            config = settings.save(candidate)
            result = 200, settings_info()
        except Exception as e:
            try:
                stop_engine(process)
                process = engine.start(old, check_updates=False)
                config = old
                result = 400, {'error':f'Configuration rejected; previous settings restored. {e}'}
            except Exception as rollback:
                result = 500, {'error':f'Load failed; rollback failed: {rollback}'}
        finally:
            with state_lock:
                loading = False
                last_activity = time.monotonic()
        if result[0] == 200: result = 200, settings_info()
        return self.json_response(*result)

    def apply_image_settings(self):
        origin=self.headers.get('Origin')
        if origin and origin!=f'http://{self.headers.get("Host")}':
            return self.json_response(403,{'error':'Origin not allowed'})
        if self.headers.get_content_type()!='application/json':
            return self.json_response(415,{'error':'Expected JSON'})
        try:
            size=int(self.headers.get('Content-Length','0'))
            if not 0<size<=65536:raise ValueError('Invalid payload size.')
            candidate=json.loads(self.rfile.read(size))
            with state_lock:
                if loading or active_requests or voice_capture.session:
                    return self.json_response(409,{'error':'Wait until generation or loading finishes.'})
                result=image_settings.save(candidate)
            return self.json_response(200,{'config':result,'defaults':image_settings.DEFAULTS,'runtime':list(result),'loading':False})
        except (ValueError,TypeError,OSError) as e:
            return self.json_response(400,{'error':str(e)})

    def voice_request(self):
        global active_requests, last_activity
        origin = self.headers.get('Origin')
        if origin and origin != f'http://{self.headers.get("Host")}':
            return self.json_response(403, {'error':'Origin not allowed'})
        if self.headers.get_content_type() != 'application/json':
            return self.json_response(415, {'error':'Expected JSON'})
        op = self.path.rsplit('/',1)[-1]
        if op not in ('start','push','finish','cancel'):
            return self.json_response(404, {'error':'Unknown operation'})
        registered = False
        try:
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 350000: raise ValueError('Invalid payload size')
            data = json.loads(self.rfile.read(length))
            if op in ('start','finish'):
                with state_lock:
                    if loading or active_requests:
                        raise RuntimeError('Wait for the model to become idle.')
                    active_requests += 1
                    registered = True
            result = voice_capture.handle(op,data)
            return self.json_response(200,result)
        except (ValueError, KeyError, RuntimeError, OSError) as e:
            return self.json_response(400, {'error':str(e)})
        finally:
            if registered:
                with state_lock:
                    active_requests -= 1
                    last_activity = time.monotonic()

    def is_desktop(self):
        return self.connection.getsockname()[0]=='127.0.0.1' and self.client_address[0]=='127.0.0.1'

    def request_allowed(self):
        # Trust the actual listener and peer, never merely a claimed Host.
        host=self.headers.get('Host','')
        if self.is_desktop():
            if host in ('127.0.0.1:8765','localhost:8765'):return True
            self.send_error(403);return False
        if host!=f'{mobile_access.ADDRESS}:8765' or not mobile_access.allowed_peer(self.client_address[0]):
            self.send_error(403);return False
        path=urlparse(self.path)
        if self.command=='GET' and path.path=='/pair':
            data=mobile_access.enroll(parse_qs(path.query).get('token',[''])[0],self.headers.get('Cookie'),self.client_address[0],self.headers.get('User-Agent',''))
            if data:
                self.send_response(303)
                self.send_header('Location','/')
                self.send_header('Set-Cookie',mobile_access.cookie(data))
                self.end_headers()
            else:self.send_error(403,'Pairing expired or revoked. Scan a new QR code.')
            return False
        if not mobile_access.authorized(self.headers.get('Cookie')):
            self.send_error(403,'Scan the QR code in Quantru on your computer.')
            return False
        if self.command=='POST':
            if self.headers.get('Origin')!='http://'+host or self.headers.get_content_type()!='application/json':
                self.send_error(403);return False
            allowed=path.path in ('/v1/chat/completions','/api/chats/begin','/api/chats/finish','/api/chats/delete','/api/chats/rename','/api/shell/stop')
        else:
            allowed=(path.path in ('/','/index.html','/__version','/api/health','/api/reasoning','/api/image/status','/api/voice/status','/api/chats','/api/chats/page','/api/chats/content','/api/chats/media','/api/chats/generated-image','/api/chats/sync','/api/mobile/heartbeat') or
                (not path.path.startswith('/api/') and self.static_allowed(path.path)))
        if not allowed:self.send_error(403)
        return allowed

    def static_allowed(self,path):
        from urllib.parse import unquote
        rel=unquote(path).lstrip('/')
        try:
            file=(ROOT/rel).resolve()
            return file.is_relative_to(ROOT) and file.is_file() and file.suffix.lower() in ('.js','.css','.svg','.png','.woff','.woff2','.ttf','.map')
        except (OSError,ValueError):return False

    def do_HEAD(self):
        if self.request_allowed():super().do_HEAD()

    def do_POST(self):
        global active_requests, image_busy, process, loading, sleeping, last_activity, first_wake
        if not self.request_allowed():return
        if self.path in ('/api/mobile/pair','/api/mobile/revoke'):
            if not self.local_shell_request():return self.json_response(403,{'error':'Desktop authorization required.'})
            # Drain the JSON body before closing the request.
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<=n<=1024:raise ValueError('Invalid request.')
                self.rfile.read(n)
                if self.path.endswith('/revoke'):
                    mobile_access.revoke()
                    return self.json_response(200,{'status':'revoked'})
                if not getattr(self.server,'lan_available',False):raise ValueError('Local network listener unavailable. Restart Quantru after connecting to Wi-Fi.')
                return self.json_response(200,mobile_access.pair())
            except (OSError,ValueError,RuntimeError) as e:return self.json_response(400,{'error':str(e)})
        if self.path=='/api/shell/stop':
            if not self.shell_request_allowed():return self.json_response(403,{'error':'Shell authorization required.'})
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=1024:raise ValueError('Invalid request.')
                shell_tool.stop(json.loads(self.rfile.read(n))['id'])
                return self.json_response(200,{'status':'stopping'})
            except (ValueError,TypeError,KeyError) as e:return self.json_response(400,{'error':str(e)})
        if self.path.startswith('/api/chats/'):
            origin=self.headers.get('Origin')
            if origin and origin!=f'http://{self.headers.get("Host")}':
                return self.json_response(403,{'error':'Origin not allowed'})
            try:
                if self.headers.get_content_type()!='application/json': raise ValueError('Expected JSON')
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=64*1024*1024: raise ValueError('Message too large')
                result=chat_history.mutate(self.path.rsplit('/',1)[-1],json.loads(self.rfile.read(n)))
                return self.json_response(200,result)
            except (ValueError,KeyError,TypeError,OSError) as e:
                return self.json_response(400,{'error':str(e)})
        if self.path.startswith('/api/voice/'): 
            return self.voice_request()
        if self.path == '/api/image/settings':
            return self.apply_image_settings()
        if self.path == '/api/settings':
            return self.apply_settings()
        if self.path != '/v1/chat/completions':
            self.send_error(404)
            return
        with state_lock:
            if loading or image_busy or shell_tool.sessions or voice_capture.session:
                return self.json_response(503, {'error':{'message':'Model is busy or loading.'}})
            if not config['model']:
                return self.json_response(409, {'error':{'message':'Choose a chat model in llama.cpp settings first.'}})
            wake = sleeping or process is None or process.poll() is not None
            if wake:
                loading = True
            active_requests += 1
            current_config = dict(config)
        try:
            if wake:
                try:
                    process = engine.start(current_config, check_updates=first_wake)
                    first_wake = False
                except Exception as e:
                    print('Model wake failed:', e, flush=True)
                    return self.json_response(503, {'error':{'message':'Unable to load the chat model. Retry the message.'}})
                else:
                    with state_lock:
                        sleeping = False
                finally:
                    with state_lock:
                        loading = False
            self.proxy_chat(current_config)
        finally:
            with state_lock:
                active_requests -= 1
                last_activity = time.monotonic()

    def local_shell_request(self):
        host=self.headers.get('Host','')
        return (self.is_desktop() and host in ('127.0.0.1:8765','localhost:8765') and
                self.headers.get('Origin')=='http://'+host and
                self.headers.get_content_type()=='application/json')

    def shell_request_allowed(self):
        if self.is_desktop():return self.local_shell_request()
        host=self.headers.get('Host','')
        return (host==f'{mobile_access.ADDRESS}:8765' and
                mobile_access.allowed_peer(self.client_address[0]) and
                mobile_access.authorized(self.headers.get('Cookie')) and
                self.headers.get('Origin')=='http://'+host and
                self.headers.get_content_type()=='application/json')

    def proxy_chat(self, current_config):
        shell_id=None
        session=None
        live_chat=None
        owner=None
        try:
            n=int(self.headers['Content-Length'])
            if not 0<n<=64*1024*1024:raise ValueError('Invalid request size.')
            payload = json.loads(self.rfile.read(n))
            archive=payload.pop('archive',None)
            owner=payload.pop('generation_id',None)
            if archive is not None and owner is not None:
                chat_history.verify_generation(archive['chat'],archive['seq'],owner)
                chat_sync.start(archive['chat'],archive['seq'],owner)
                live_chat=archive['chat']
                self.live_chat=live_chat
            image_permission=payload.pop('image_tool',None)
            effort=payload.pop('reasoning_level',None)
            allow_shell=payload.pop('shell_tool',False)
            requested_id=payload.pop('shell_request_id',None)
            if not self.is_desktop():
                if archive is None:raise ValueError('Archived chat required.')
                payload={k:v for k,v in payload.items() if k=='stream'}
            if type(allow_shell) is not bool:raise ValueError('Invalid shell permission.')
            if allow_shell:
                if archive is None or not self.shell_request_allowed():
                    return self.json_response(403,{'error':{'message':'Local shell authorization required.'}})
                if image_permission:raise ValueError('Enable only one tool at a time.')
                with state_lock:
                    if active_requests!=1:raise ValueError('Wait until other requests finish.')
                    session=shell_tool.register(requested_id)
                    shell_id=requested_id
            if image_permission is not None and type(image_permission) is not bool:
                raise ValueError('Invalid image tool permission.')
            for key in ('temperature','top_k','top_p','min_p','repeat_penalty','presence_penalty','frequency_penalty','seed'):
                payload.setdefault(key,current_config[key])
            if current_config['max_tokens'] > 0:
                payload.setdefault('max_tokens',current_config['max_tokens'])
            payload.setdefault('cache_prompt',current_config['cache_prompt'])
            kwargs = payload.setdefault('chat_template_kwargs', {})
            kwargs.setdefault('enable_thinking',current_config['thinking'])
            if effort is not None:
                reasoning.apply(payload,effort,reasoning.capabilities(current_config,engine.PORT,process),current_config)
            allow_image=archive is not None and (image_permission if image_permission is not None else image_generation.enabled(chat_history.user_text(archive['chat'],archive['seq'])))
            if archive is not None:
                payload['messages']=context_memory.build(archive['chat'],archive['seq'],current_config,engine.PORT,kwargs,allow_image_reference=allow_image)
            if payload.get('stream'):payload['timings_per_token']=True
            if allow_shell:
                return self.shell_chat(payload,archive,current_config,session)
            if allow_image:
                return self.image_chat(payload,archive,current_config)
            # Never expose the image tool without explicit permission in this turn.
            payload.pop('tools',None)
            payload.pop('tool_choice',None)
            if archive is not None:
                messages=payload['messages']
                if messages and messages[0]['role']=='system':
                    messages[0]['content']=image_generation.UNAVAILABLE_INSTRUCTION+'\n'+shell_tool.OFF+'\n\n'+messages[0]['content']
                else:
                    messages.insert(0,{'role':'system','content':image_generation.UNAVAILABLE_INSTRUCTION+'\n'+shell_tool.OFF})
            data = json.dumps(payload).encode()
            req = urllib.request.Request(f'http://127.0.0.1:{engine.PORT}/v1/chat/completions', data=data, headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req, timeout=300) as response:
                self.send_response(response.status)
                self.send_header('Content-Type', response.headers.get('Content-Type','application/json'))
                self.end_headers()
                stats=token_stats.TokenStats()
                for line in response:
                    if payload.get('stream') and line.startswith(b'data:'):
                        try:
                            chunk=json.loads(line[5:].strip())
                            if isinstance(chunk,dict):
                                metrics=stats.update(chunk)
                                if metrics:chunk['generation_stats']=metrics;line=('data: '+json.dumps(chunk,ensure_ascii=False)+'\n').encode()
                        except (ValueError,TypeError):pass
                    chat_sync.line(live_chat,line)
                    self.wfile.write(line)
                    self.wfile.flush()
        except (ValueError,KeyError,TypeError) as e:
            return self.json_response(400,{'error':{'message':str(e)}})
        except (BrokenPipeError, ConnectionResetError, InterruptedError):
            pass
        except urllib.error.HTTPError as e:
            self.send_response(e.code)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(e.read())
        except OSError:
            self.send_response(503)
            self.send_header('Content-Type','application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error':{'message':'Model is starting or unavailable.'}}).encode())

        finally:
            if shell_id is not None:shell_tool.unregister(shell_id)
            if live_chat is not None:
                entry=chat_sync.get(live_chat)
                try:
                    if entry:
                        state='error' if entry['failed'] else 'complete' if entry['done'] else 'stopped'
                        chat_history.mutate('finish',{'chat':live_chat,'seq':entry['seq'],'generation_id':owner,
                            'answer':entry['answer'],'thinking':entry['thinking'],'status':state,'generation_stats':entry.get('generation_stats')})
                except (ValueError,OSError) as e:print('Sync finish:',e,flush=True)
                finally:chat_sync.finish(live_chat,owner)

    def shell_chat(self,payload,archive,current_config,session):
        import uuid
        session.check()
        self.send_response(200)
        self.send_header('Content-Type','text/event-stream')
        self.end_headers()
        def send_event(delta=None,**extra):
            session.check()
            chunk={'choices':[{'delta':delta or {}}],**extra}
            chat_sync.event(getattr(self,'live_chat',None),chunk)
            self.wfile.write(('data: '+json.dumps(chunk,ensure_ascii=False)+'\n\n').encode())
            self.wfile.flush()
        messages=[dict(m) for m in payload['messages']]
        instruction=shell_tool.INSTRUCTION+'\n'+image_generation.UNAVAILABLE_INSTRUCTION
        if messages and messages[0]['role']=='system':
            messages[0]['content']=instruction+'\n\n'+messages[0]['content']
        else:messages.insert(0,{'role':'system','content':instruction})
        base=messages[:]
        rounds=[]
        stats=token_stats.TokenStats()
        idx=0
        tools=[shell_tool.TOOL]
        counter=context_memory.Engine(engine.PORT,payload.get('chat_template_kwargs'))
        budget=current_config['context']-min(512,max(128,current_config['context']//4))
        try:
            while True:
                session.check()
                # Retain the current user message and complete recent tool
                # exchanges; trim older context when it no longer fits.
                while counter.count(base+[m for group in rounds for m in group],tools)>budget:
                    if len(base)>2:base=base[:1]+base[2:]
                    elif len(rounds)>1:rounds.pop(0)
                    else:raise ValueError('Shell conversation exceeded model context. Continue in a new message.')
                    while len(base)>2 and base[1]['role']!='user':base.pop(1)
                plan={**payload,'messages':base+[m for group in rounds for m in group],
                      'tools':tools,'tool_choice':'auto','stream':True}
                stats.next_round()
                calls={}
                finish=None
                text=''
                thought=''
                req=urllib.request.Request(f'http://127.0.0.1:{engine.PORT}/v1/chat/completions',data=json.dumps(plan).encode(),headers={'Content-Type':'application/json'})
                with urllib.request.urlopen(req,timeout=300) as response:
                    for line in response:
                        session.check()
                        if not line.startswith(b'data:'):continue
                        raw=line[5:].strip()
                        if raw==b'[DONE]':break
                        chunk=json.loads(raw)
                        if chunk.get('error'):raise RuntimeError(str(chunk['error']))
                        metrics=stats.update(chunk)
                        if metrics:send_event(generation_stats=metrics)
                        choices=chunk.get('choices') or []
                        if not choices:continue
                        choice=choices[0]
                        delta=choice.get('delta') or {}
                        visible={k:delta[k] for k in ('content','reasoning_content') if delta.get(k)}
                        text+=delta.get('content') or ''
                        thought+=delta.get('reasoning_content') or ''
                        if visible:send_event(visible)
                        for call in delta.get('tool_calls') or []:
                            fn=calls.setdefault(call.get('index',0),{'id':'','name':'','arguments':''})
                            if call.get('id'):fn['id']+=call['id']
                            for k,v in (call.get('function') or {}).items():
                                if k in ('name','arguments') and isinstance(v,str):fn[k]+=v
                        finish=choice.get('finish_reason') or finish
                if not calls:break
                if finish!='tool_calls':raise RuntimeError('Incomplete shell tool call.')
                assistant={'role':'assistant','content':text,'tool_calls':[]}
                if thought:assistant['reasoning_content']=thought
                group=[assistant]
                for key in sorted(calls):
                    fn=calls[key]
                    if fn['name']!='run_shell':raise ValueError('Unexpected shell tool.')
                    id=fn['id'] or uuid.uuid4().hex[:12]
                    assistant['tool_calls'].append({'id':id,'type':'function','function':{'name':fn['name'],'arguments':fn['arguments']}})
                    session.check()
                    args=json.loads(fn['arguments'])
                    command,cwd=shell_tool.arguments(args)
                    idx+=1
                    chat,seq=archive['chat'],archive['seq']
                    chat_history.start_shell(chat,seq,idx,command,cwd)
                    try:
                        send_event(shell_event={'type':'start','idx':idx,'command':command,'cwd':cwd})
                    except (InterruptedError,BrokenPipeError,ConnectionResetError):
                        chat_history.finish_shell(chat,seq,idx,'',None,'stopped')
                        raise
                    result=shell_tool.execute(session,command,cwd,
                        lambda text:send_event(shell_event={'type':'output','idx':idx,'text':text}) if text else send_event(),
                        lambda output,code,state:chat_history.finish_shell(chat,seq,idx,output,code,state))
                    send_event(shell_event={'type':'end','idx':idx,'status':result['status'],'exit_code':result['exit_code']})
                    out=result['output']
                    if len(out)>4000:out=out[:1000]+'\n[Middle omitted from model context]\n'+out[-3000:]
                    group.append({'role':'tool','tool_call_id':id,'content':json.dumps({**result,'output':out},ensure_ascii=False)})
                rounds.append(group)
            chat_sync.event(getattr(self,'live_chat',None),'[DONE]')
            self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
        except (InterruptedError,BrokenPipeError,ConnectionResetError):
            session.stop()
        except Exception as e:
            print('Shell tool:',e,flush=True)
            try:send_event(shell_error=str(e))
            except (OSError,InterruptedError):pass

    def image_chat(self,payload,archive,current_config):
        global process,image_busy
        with state_lock:
            if active_requests!=1 or image_busy or voice_capture.session:
                return self.json_response(409,{'error':{'message':'Wait until other requests finish.'}})
            image_busy=True
        headers_sent=False
        def send_event(delta=None,**extras):
            chunk={'choices':[{'delta':delta or {}}],**extras}
            chat_sync.event(getattr(self,'live_chat',None),chunk)
            self.wfile.write(('data: '+json.dumps(chunk,ensure_ascii=False)+'\n\n').encode())
            self.wfile.flush()
        def status(text):
            send_event(image_status=text)
        try:
            if not image_generation.available():
                return self.json_response(503,{'error':{'message':'Image backend unavailable.'}})
            self.send_response(200)
            self.send_header('Content-Type','text/event-stream')
            self.end_headers()
            headers_sent=True
            plan=dict(payload)
            messages=[dict(x) for x in payload['messages']]
            catalog=image_generation.reference_catalog(archive['chat'],archive['seq'])
            instruction=image_generation.INSTRUCTION+'\n'+shell_tool.OFF+'\n\n'+image_generation.reference_instruction(catalog,archive['seq'])
            if messages and messages[0]['role']=='system':
                messages[0]['content']=instruction+'\n\n'+messages[0]['content']
            else:messages.insert(0,{'role':'system','content':instruction})
            plan.update(messages=messages,tools=[image_generation.TOOL],tool_choice='auto',stream=True)
            # The normal chat completion decides whether to call the tool.
            # Preserve the user's thinking and sampling settings; relay text
            # and reasoning as they arrive, and collect native tool deltas.
            calls={}
            finish=None
            visible_text=''
            stats=token_stats.TokenStats()
            req=urllib.request.Request(f'http://127.0.0.1:{engine.PORT}/v1/chat/completions',
                data=json.dumps(plan).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=300) as response:
                for line in response:
                    if not line.startswith(b'data:'):continue
                    raw=line[5:].strip()
                    if raw==b'[DONE]':break
                    chunk=json.loads(raw)
                    if chunk.get('error'):raise RuntimeError(str(chunk['error']))
                    metrics=stats.update(chunk)
                    if metrics:send_event(generation_stats=metrics)
                    choices=chunk.get('choices') or []
                    if not choices:continue
                    choice=choices[0]
                    delta=choice.get('delta') or {}
                    visible={k:delta[k] for k in ('content','reasoning_content') if delta.get(k)}
                    visible_text+=delta.get('content') or ''
                    if visible:send_event(visible)
                    for call in delta.get('tool_calls') or []:
                        index=call.get('index',0)
                        fn=calls.setdefault(index,{'name':'','arguments':''})
                        for key,value in (call.get('function') or {}).items():
                            if key in fn and isinstance(value,str):fn[key]+=value
                    finish=choice.get('finish_reason') or finish
            if calls and finish=='tool_calls':
                fn=calls[min(calls)]
                if fn['name']!='generate_image':raise ValueError('Unexpected tool.')
                args=json.loads(fn['arguments'])
                references=image_generation.read_references(archive['chat'],args.get('reference_ids',[]),catalog)
                send_event(image_tool_call=True)
                status('Loading image model…')
                stop_engine(process)
                process=None
                try:
                    png=image_generation.generate(args,status,references)
                    chat_history.store_image(archive['chat'],archive['seq'],png,args['prompt'])
                    send_event(image_generated=True,image_prompt=args['prompt'])
                finally:
                    # Restore the chat model on success, error and cancellation.
                    try:status('Restoring chat model…')
                    except (BrokenPipeError,ConnectionResetError):pass
                    process=engine.start(current_config,check_updates=False)
            elif calls:
                raise RuntimeError('The model did not complete its image tool call.')
            elif context_memory.IMAGE_MARKER.search(visible_text):
                raise RuntimeError('The model described an image without calling the image tool. No image was generated. Please retry.')
            chat_sync.event(getattr(self,'live_chat',None),'[DONE]')
            self.wfile.write(b'data: [DONE]\n\n');self.wfile.flush()
        except (BrokenPipeError,ConnectionResetError):
            pass
        except Exception as e:
            print('Image tool:',e,flush=True)
            if headers_sent:
                try:send_event(image_error=str(e))
                except OSError:pass
            else:self.json_response(500,{'error':{'message':str(e)}})
        finally:
            with state_lock:image_busy=False

    def do_GET(self):
        if not self.request_allowed():return
        path=urlparse(self.path)
        if path.path=='/api/mobile/status':
            if not self.is_desktop():return self.json_response(403,{'error':'Desktop authorization required.'})
            return self.json_response(200,mobile_access.status())
        if path.path=='/api/mobile/heartbeat':
            if self.is_desktop():return self.json_response(403,{'error':'Mobile connection required.'})
            if not mobile_access.heartbeat(self.headers.get('Cookie'),self.client_address[0]):
                return self.json_response(403,{'error':'Access revoked or expired.'})
            return self.json_response(200,{'status':'connected'})
        if path.path.startswith('/api/chats'):
            try:
                q=parse_qs(path.query)
                if path.path=='/api/chats':
                    return self.json_response(200,chat_history.list_chats(int(q.get('offset',['0'])[0])))
                if path.path=='/api/chats/sync':
                    return self.json_response(200,chat_history.sync_state(chat_history.ident(q['chat'][0])))
                if path.path=='/api/chats/page':
                    return self.json_response(200,chat_history.page(q['chat'][0],int(q.get('before',['1000000001'])[0])))
                if path.path=='/api/chats/content':
                    return self.json_response(200,{'content':chat_history.content(q['chat'][0],int(q['seq'][0]))})
                if path.path=='/api/chats/generated-image':
                    raw=chat_history.generated_image(q['chat'][0],int(q['seq'][0]))
                    if raw is None:return self.json_response(404,{'error':'Image not found'})
                    self.send_response(200);self.send_header('Content-Type','image/png');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
                if path.path=='/api/chats/media':
                    value=chat_history.content(q['chat'][0],int(q['seq'][0]))
                    import base64
                    items=[p for p in value if isinstance(p,dict) and p.get('type')!='text']
                    item=items[int(q['index'][0])]
                    if item['type']=='image_url':
                        header,data=item['image_url']['url'].split(',',1)
                        mime=header.split(';')[0].removeprefix('data:')
                        if mime not in ('image/png','image/jpeg','image/webp','image/gif'): raise ValueError('Unsupported media')
                    else:
                        data=item['input_audio']['data']; mime='application/octet-stream'
                    raw=base64.b64decode(data,validate=True)
                    self.send_response(200);self.send_header('Content-Type',mime);self.send_header('X-Content-Type-Options','nosniff');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw);return
                return self.json_response(404,{'error':'Not found'})
            except (ValueError,KeyError,IndexError,TypeError,OSError) as e:
                return self.json_response(400,{'error':str(e)})
        if self.path == '/api/image/settings':
            try:
                c=image_settings.load()
                return self.json_response(200,{'config':c,'defaults':image_settings.DEFAULTS,'runtime':list(c),'loading':loading or image_busy})
            except (ValueError,OSError) as e:return self.json_response(400,{'error':str(e)})
        if self.path == '/api/image/status':
            return self.json_response(200,{'available':image_generation.available()})
        if self.path == '/api/voice/status':
            return self.json_response(200,{'available':self.is_desktop() and voice_capture.available()})
        if self.path == '/api/settings':
            with state_lock: return self.json_response(200,settings_info())
        if self.path == '/api/reasoning':
            with state_lock:
                result=reasoning.capabilities(config,engine.PORT,None if loading or image_busy or sleeping else process)
            return self.json_response(200,result)
        if self.path == '/api/health':
            with state_lock:
                if active_requests or image_busy or shell_tool.sessions or voice_capture.session:
                    return self.json_response(503, {'status':'busy'})
                if loading:
                    return self.json_response(503, {'status':'loading'})
                if sleeping:
                    return self.json_response(200, {'status':'sleeping','configured':bool(config['model'])})
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{engine.PORT}/health',timeout=2) as r:
                    self.send_response(r.status)
                    self.send_header('Content-Type','application/json')
                    self.end_headers()
                    self.wfile.write(r.read())
            except OSError:
                self.send_response(503)
                self.end_headers()
            return
        if self.path == '/__instance' and self.is_desktop():
            body=hashlib.sha256((str(ROOT.parent)+':'+str(os.getuid())).encode()).hexdigest().encode()
            self.send_response(200)
            self.send_header('Content-Type','text/plain')
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == '/__version':
            digest = hashlib.sha256()
            for path in sorted(ROOT.rglob('*')):
                if path.is_file():
                    try:
                        digest.update(str(path.relative_to(ROOT)).encode())
                        digest.update(path.read_bytes())
                    except FileNotFoundError:
                        continue
            data = digest.hexdigest().encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            super().do_GET()

    def log_message(self, format, *args):
        pass

if __name__ == '__main__':
    engine_updates.recover()
    chat_history.init()
    def terminate(*_):
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, terminate)
    with ThreadingHTTPServer((HOST, PORT), Handler) as server:
        print(f'Quantru: http://{HOST}:{PORT}/', flush=True)
        lan_server=None
        server.lan_available=False
        addr=mobile_access.discover()
        if addr:
            try:
                lan_server=ThreadingHTTPServer((addr,PORT),Handler)
                server.lan_available=True
                threading.Thread(target=lan_server.serve_forever,daemon=True).start()
                print(f'LAN pairing available: http://{addr}:{PORT}/',flush=True)
            except OSError as e:print('LAN listener unavailable:',e,flush=True)
        print('Chat model on standby; loads on first message.', flush=True)
        threading.Thread(target=voice_capture.cleanup_loop,daemon=True).start()
        threading.Thread(target=idle_loop,daemon=True).start()
        def updates_idle():
            return not (loading or active_requests or image_busy or voice_capture.session or shell_tool.sessions)
        def image_updates_enabled():
            try:return image_settings.load()['auto_update']
            except (ValueError,OSError):return False
        threading.Thread(target=engine_updates.loop,args=('image',state_lock,updates_idle,image_updates_enabled),daemon=True).start()
        threading.Thread(target=engine_updates.loop,args=('audio',state_lock,updates_idle,lambda:True),daemon=True).start()
        try:
            server.serve_forever()
        finally:
            if lan_server is not None:
                lan_server.shutdown()
                lan_server.server_close()
            shell_tool.stop_all()
            image_generation.stop()
            with voice_capture.lock: voice_capture.close()
            if process is not None and process.poll() is None:
                process.terminate()
                process.wait(timeout=10)
