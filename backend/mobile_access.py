"""Expiring LAN pairing. The local desktop remains the only administrator."""
import base64
import hmac
import ipaddress
import json
import os
import pathlib
import secrets
import re
import subprocess
import tempfile
import threading
import time
from http.cookies import SimpleCookie

STATE=pathlib.Path(__file__).resolve().parent/'mobile-access.json'
LIFETIME=7*24*60*60
COOKIE='quantru_mobile'
LOCK=threading.RLock()
ADDRESS=None
NETWORK=None
INTERFACE=None
PRIVATE=[ipaddress.ip_network(s) for s in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')]

def discover():
    global ADDRESS,NETWORK,INTERFACE
    try:
        routes=json.loads(subprocess.check_output(['ip','-j','-4','route','show','default'],timeout=3))
        for route in sorted(routes,key=lambda r:r.get('metric',0)):
            dev=route.get('dev')
            if not dev:continue
            links=json.loads(subprocess.check_output(['ip','-j','link','show','dev',dev],timeout=3))
            if not links or links[0].get('link_type')!='ether':continue
            for link in json.loads(subprocess.check_output(['ip','-j','-4','addr','show','dev',dev],timeout=3)):
                for item in link.get('addr_info',[]):
                    addr=ipaddress.ip_address(item['local'])
                    if item.get('scope')!='global' or not any(addr in n for n in PRIVATE):continue
                    network=ipaddress.ip_interface(f"{addr}/{item['prefixlen']}").network
                    if network.prefixlen<8:continue
                    ADDRESS,NETWORK,INTERFACE=str(addr),network,dev
                    return ADDRESS
    except (OSError,ValueError,KeyError,subprocess.SubprocessError):pass
    return None

def allowed_peer(ip):
    try:return NETWORK is not None and ipaddress.ip_address(ip) in NETWORK
    except ValueError:return False

def read():
    try:
        data=json.loads(STATE.read_text())
        if isinstance(data.get('token'),str) and len(data['token'])>=43 and data['expires']>time.time():return data
    except (OSError,ValueError,TypeError,KeyError):pass
    return None

def write(data):
    fd,tmp=tempfile.mkstemp(prefix='.mobile-',dir=STATE.parent)
    try:
        with os.fdopen(fd,'w') as f:json.dump(data,f)
        os.replace(tmp,STATE)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def pair():
    with LOCK:
        if not ADDRESS:raise ValueError('No compatible local network connection.')
        from . import mobile_firewall
        firewall=mobile_firewall.ensure(str(NETWORK),ADDRESS,INTERFACE)
        data=read()
        if data is None:
            data={'token':secrets.token_urlsafe(32),'expires':int(time.time())+LIFETIME,'devices':[]}
            write(data)
        url=f"http://{ADDRESS}:8765/pair?token={data['token']}"
        png=subprocess.run(['qrencode','-o','-','-t','PNG','-s','8','-m','4'],input=url.encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,check=True,timeout=5).stdout
        return {'firewall':firewall,'url':url,'expires':data['expires'],'qr':'data:image/png;base64,'+base64.b64encode(png).decode()}

def revoke():
    with LOCK:
        STATE.unlink(missing_ok=True)
        from . import mobile_firewall
        mobile_firewall.remove()

def validate(token):
    with LOCK:
        data=read()
        return data if data and isinstance(token,str) and hmac.compare_digest(token,data['token']) else None

def token_from_cookie(header):
    try:
        jar=SimpleCookie();jar.load(header or '')
        return jar[COOKIE].value
    except (KeyError,ValueError):return ''

def device_name(agent):
    match=re.search(r'Android[^;)]*;\s*([^;)]+)',agent)
    if 'iPhone' in agent:return 'iPhone'
    if 'iPad' in agent:return 'iPad'
    if 'Android' in agent:
        model=match.group(1).split(' Build/')[0].strip() if match else ''
        return 'Android'+(' · '+model[:60] if model and model not in ('K','Mobile') else '')
    if 'Windows' in agent:return 'Windows'
    if 'Macintosh' in agent:return 'Mac'
    if 'Linux' in agent:return 'Linux'
    return 'Browser'

def find_device(data,token):
    if not token:return None
    return next((d for d in data.get('devices',[]) if hmac.compare_digest(d['session'],token)),None)

def enroll(invite,header,ip,agent):
    with LOCK:
        data=validate(invite)
        if not data:return None
        devices=data.setdefault('devices',[])
        device=find_device(data,token_from_cookie(header))
        if device is None:
            device={'id':secrets.token_hex(8),'session':secrets.token_urlsafe(32),'name':device_name(agent),'ip':ip,'seen':int(time.time())}
            devices.append(device)
        device.update(ip=ip,name=device_name(agent),seen=int(time.time()))
        write(data)
        return {'token':device['session'],'expires':data['expires']}

def authorized(header):
    with LOCK:
        data=read()
        return bool(data and find_device(data,token_from_cookie(header)))

def heartbeat(header,ip):
    with LOCK:
        data=read()
        if not data:return False
        device=find_device(data,token_from_cookie(header))
        if not device:return False
        now=int(time.time())
        if now-device['seen']>=4 or device['ip']!=ip:
            device.update(ip=ip,seen=now)
            write(data)
        return True

def status():
    with LOCK:
        data=read()
        if not data:return {'active':False,'devices':[]}
        now=time.time()
        return {'active':True,'expires':data['expires'],'devices':[
            {'id':d['id'],'name':d['name'],'ip':d['ip'],'seen':d['seen'],'online':now-d['seen']<=15}
            for d in data.get('devices',[])]}

def cookie(data):
    return f"{COOKIE}={data['token']}; Path=/; Max-Age={max(0,int(data['expires']-time.time()))}; HttpOnly; SameSite=Lax"
