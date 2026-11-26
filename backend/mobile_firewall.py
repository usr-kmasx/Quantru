"""Optional firewall integrations for desktop-authorized LAN access."""
import ipaddress
import json
import os
import tempfile
import pathlib
import re
import shutil
import subprocess

RULES=pathlib.Path('/etc/ufw/user.rules')
CONF=pathlib.Path('/etc/ufw/ufw.conf')
TAG='Quantru mobile access'
TAG_HEX=TAG.encode().hex()
PORT='8765'

def enabled():
    try:
        if re.search(r'^ENABLED\s*=\s*yes\s*$',CONF.read_text(),re.M|re.I):return True
    except OSError:pass
    return service_active('ufw')

def rules():
    try:return [line.split('### tuple ### ',1)[1].split() for line in RULES.read_text().splitlines() if line.startswith('### tuple ### ')]
    except OSError:return None

def scope(network,address,interface):
    network=ipaddress.IPv4Network(network)
    address=ipaddress.IPv4Address(address)
    if address not in network or not any(network.subnet_of(ipaddress.IPv4Network(n)) for n in ('10.0.0.0/8','172.16.0.0/12','192.168.0.0/16')):raise ValueError('Invalid local network.')
    if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,15}',interface):raise ValueError('Invalid network interface.')
    return str(network),str(address),interface

def tuple_matches(row,network,address,interface):
    if len(row)<7:return False
    try:
        return (row[1:3]==['tcp',PORT] and ipaddress.IPv4Network(row[3],strict=False)==ipaddress.IPv4Network(address+'/32')
           and row[4]=='any' and ipaddress.IPv4Network(row[5],strict=False)==ipaddress.IPv4Network(network) and row[6]=='in_'+interface)
    except ValueError:return False

def change(action,network,address,interface):
    network,address,interface=scope(network,address,interface)
    ufw=next((str(p) for p in (pathlib.Path('/usr/bin/ufw'),pathlib.Path('/usr/sbin/ufw')) if p.is_file()),None)
    if not ufw or not pathlib.Path('/usr/bin/pkexec').is_file():
        raise ValueError('Polkit or UFW is missing. Install the system packages or configure your firewall manually.')
    args=['/usr/bin/pkexec','--disable-internal-agent',ufw]
    if action=='delete':args+=['--force','delete']
    args+=['allow','in','on',interface,'from',network,'to',address,'port',PORT,'proto','tcp','comment',TAG]
    try:
        r=subprocess.run(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=120)
    except subprocess.TimeoutExpired:raise ValueError('Firewall authorization timed out. Try again.')
    if r.returncode:
        detail=(r.stderr or r.stdout).strip()
        print(f'Firewall {action} failed (exit {r.returncode}): {detail}',flush=True)
        if r.returncode in (126,127):
            raise ValueError('Firewall authorization was cancelled or unavailable. Check your desktop Polkit agent and try again.')
        raise ValueError('UFW could not apply the rule: '+(detail.splitlines()[0][:240] if detail else f'exit {r.returncode}'))
    return r.stdout

def ensure_ufw(network,address,interface):
    if not enabled():return 'not_required'
    network,address,interface=scope(network,address,interface)
    existing=rules()
    if existing is None:raise ValueError('Cannot inspect UFW rules safely. Configure the local firewall manually.')
    for row in existing:
        if tuple_matches(row,network,address,interface):
            if row[0].split('_')[0]=='allow':return 'already_allowed'
            raise ValueError('UFW already has a conflicting rule for this connection. Review it before pairing.')
    change('allow',network,address,interface)
    after=rules()
    if after is None or not any(tuple_matches(row,network,address,interface) and row[0]=='allow' and 'comment='+TAG_HEX in row for row in after):
        raise ValueError('UFW did not confirm the local access rule. Check your firewall.')
    return 'allowed'

def remove_ufw():
    existing=rules()
    if existing is None:
        if enabled():raise ValueError('Access revoked, but UFW rules could not be inspected.')
        return
    for row in existing:
        if len(row)!=8 or row[0:3]!=['allow','tcp',PORT] or row[4]!='any' or not row[6].startswith('in_') or row[7]!='comment='+TAG_HEX:continue
        address=str(ipaddress.IPv4Network(row[3],strict=False).network_address)
        change('delete',row[5],address,row[6][3:])
    after=rules()
    if after is not None and any('comment='+TAG_HEX in row for row in after):raise ValueError('Access revoked, but the Quantru firewall rule remains.')

FIREWALLD_STATE=pathlib.Path(__file__).resolve().parent/'mobile-firewalld.json'

def service_active(name):
    try:
        return subprocess.run(['systemctl','is-active','--quiet',name],timeout=3).returncode==0
    except (OSError,subprocess.SubprocessError):return False

def firewalld_binary():
    return next((str(p) for p in (pathlib.Path('/usr/bin/firewall-cmd'),pathlib.Path('/usr/sbin/firewall-cmd')) if p.is_file()),None)

def firewalld_active():
    cmd=firewalld_binary()
    if not cmd:return False
    try:return subprocess.run([cmd,'--state'],capture_output=True,text=True,timeout=4).stdout.strip()=='running'
    except (OSError,subprocess.SubprocessError):return service_active('firewalld')

def firewalld_call(args,authorize=False):
    cmd=firewalld_binary()
    if not cmd:raise ValueError('firewalld is unavailable.')
    command=[cmd,*args]
    if authorize:
        if not pathlib.Path('/usr/bin/pkexec').is_file():raise ValueError('Polkit is unavailable.')
        command=['/usr/bin/pkexec','--disable-internal-agent',*command]
    result=subprocess.run(command,stdin=subprocess.DEVNULL,capture_output=True,text=True,timeout=120 if authorize else 5)
    return result

def rich_rule(network,address):
    return f'rule family="ipv4" source address="{network}" destination address="{address}/32" port port="{PORT}" protocol="tcp" accept'

def firewalld_owned():
    try:
        d=json.loads(FIREWALLD_STATE.read_text())
        net,addr,dev=scope(d['network'],d['address'],d['interface'])
        zone=d['zone']
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',zone):return None
        return {'network':net,'address':addr,'interface':dev,'zone':zone}
    except (OSError,ValueError,TypeError,KeyError):return None

def save_firewalld(data):
    fd,tmp=tempfile.mkstemp(prefix='.firewall-',dir=FIREWALLD_STATE.parent)
    try:
        with os.fdopen(fd,'w') as f:json.dump(data,f)
        os.replace(tmp,FIREWALLD_STATE)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def remove_firewalld():
    owned=firewalld_owned()
    if not owned:return
    if not firewalld_active():
        # This is a runtime-only rule; it does not survive a daemon restart.
        if not service_active('firewalld'):
            FIREWALLD_STATE.unlink(missing_ok=True)
            return
        raise ValueError('Cannot inspect firewalld; review the local rule manually.')
    rule=rich_rule(owned['network'],owned['address'])
    zone='--zone='+owned['zone']
    result=firewalld_call([zone,'--query-rich-rule='+rule])
    if result.returncode==0:
        result=firewalld_call([zone,'--remove-rich-rule='+rule],True)
        if result.returncode:raise ValueError('Access revoked, but firewalld rule removal was not confirmed.')
    elif result.returncode!=1:raise ValueError('Could not inspect the firewalld rule.')
    FIREWALLD_STATE.unlink(missing_ok=True)

def ensure_firewalld(network,address,interface):
    result=firewalld_call(['--get-zone-of-interface='+interface])
    zone=result.stdout.strip()
    if result.returncode or not zone or zone=='no zone':
        result=firewalld_call(['--get-default-zone'])
        zone=result.stdout.strip()
    if result.returncode or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}',zone):
        raise ValueError('Cannot determine the firewalld zone.')
    data={'network':network,'address':address,'interface':interface,'zone':zone}
    owned=firewalld_owned()
    if owned and owned!=data:remove_firewalld()
    rule=rich_rule(network,address)
    args=['--zone='+zone]
    result=firewalld_call(args+['--query-rich-rule='+rule])
    if result.returncode==0:return 'already_allowed'
    if result.returncode!=1:raise ValueError('Cannot inspect firewalld rules.')
    result=firewalld_call(args+['--add-rich-rule='+rule,'--timeout=604800'],True)
    if result.returncode:raise ValueError('firewalld authorization or rule installation failed.')
    save_firewalld(data)
    if firewalld_call(args+['--query-rich-rule='+rule]).returncode!=0:
        raise ValueError('firewalld did not confirm the rule.')
    return 'allowed'

def ensure(network,address,interface):
    network,address,interface=scope(network,address,interface)
    # Only manage recognized, active firewalls. Never guess custom chain names,
    # change default policy, disable a firewall or install a firewall package.
    ufw=enabled()
    fw=firewalld_active()
    manager='manual'
    message=''
    try:
        if ufw and not fw:
            manager='UFW'
            ensure_ufw(network,address,interface)
        elif fw and not ufw:
            manager='firewalld'
            ensure_firewalld(network,address,interface)
        else:
            manager='manual'
            message='If your firewall blocks the connection, allow TCP '+PORT+' from '+network+' to '+address+' on '+interface+'. No firewall changes were made.'
    except (ValueError,OSError,subprocess.SubprocessError) as e:
        message=f'{manager}: {e} If needed, manually allow TCP {PORT} from {network} to {address} on {interface}.'
    return {'manager':manager,'message':message,'network':network,'address':address,'interface':interface,'port':int(PORT)}

def remove():
    errors=[]
    for cleanup in (remove_ufw,remove_firewalld):
        try:cleanup()
        except (ValueError,OSError,subprocess.SubprocessError) as e:errors.append(str(e))
    if errors:raise ValueError('Access revoked. '+ ' '.join(errors))
