"""Authenticated single-endpoint UDP punch; difficult NATs retain the relay.

Successful sockets are handed to CraftLink AutoPeer's reliable UDP carrier.
There is no port scanning or external STUN service dependency.
"""
import asyncio
import hashlib
import hmac
import json
import secrets
import socket
import time
from types import SimpleNamespace
from urllib.parse import urlsplit
from .vendor.craftlink.auto_peer import AutoPeer
from .vendor.craftlink import punch as craftlink, stun


def punch(info,api,url,stopped):
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0',0));sock.settimeout(.15)
    sid=bytes.fromhex(info['sid']);side=b'H' if info['side']=='host' else b'P'
    shared=bytes.fromhex(info['shared']);nonce=secrets.token_bytes(16)
    payload=b'ALPH'+sid+side+nonce
    packet=payload+hmac.digest(shared,payload,'sha256')
    discovery=secrets.token_hex(8)
    target=None;deadline=time.monotonic()+15;poll_at=0;next_send=0
    try:
        while time.monotonic()<deadline and not stopped.is_set():
            now=time.monotonic()
            if now>=poll_at:
                response=api('/api/connections/'+info['sid']+'/punch')
                if not response['available']:raise ConnectionError('P2P discovery unavailable')
                if target is None:target=(socket.gethostbyname(urlsplit(url).hostname),response['port'])
                sock.sendto(json.dumps({'key':info['punch_key'],'nonce':discovery}).encode(),target)
                peer=tuple(response['peer']) if response.get('peer') else None
                poll_at=now+.5
            if peer and now>=next_send:
                sock.sendto(packet,peer);next_send=now+.2
            try:data,addr=sock.recvfrom(1024)
            except socket.timeout:continue
            if len(data)!=69 or data[:20]!=b'ALPH'+sid or data[20:21]==side:continue
            if not hmac.compare_digest(hmac.digest(shared,data[:37],'sha256'),data[37:]):continue
            # The endpoint must also have been discovered by the authoritative service.
            if not peer or addr!=peer:continue
            for _ in range(3):sock.sendto(packet,addr);time.sleep(.05)
            return sock,addr
        raise TimeoutError('UDP punch timed out; relay remains available')
    except BaseException:
        sock.close();raise


async def authenticate_punched_socket(sock, addr, info):
    """CraftLink discovers the candidate. Only the pair secret admits it."""
    scope = b'ALCP' + bytes.fromhex(info['sid'])
    side = b'H' if info['side']=='host' else b'P'
    opposite = b'P' if side==b'H' else b'H'
    payload = scope + side
    key = bytes.fromhex(info['shared'])
    packet = payload + hmac.digest(key,payload,'sha256')
    expected = scope + opposite
    expected += hmac.digest(key,expected,'sha256')
    loop = asyncio.get_running_loop()
    sock.setblocking(False)
    for _ in range(20):
        await loop.sock_sendto(sock,packet,addr)
        try:
            data,origin = await asyncio.wait_for(loop.sock_recvfrom(sock,1024),.2)
        except asyncio.TimeoutError:
            continue
        if origin==addr and hmac.compare_digest(data,expected):
            for _ in range(3):
                await loop.sock_sendto(sock,packet,addr)
                await asyncio.sleep(.03)
            return
    raise ConnectionError('CraftLink candidate failed scoped authentication')


async def craftlink_candidate(info,api,url,stopped):
    host=urlsplit(url).hostname
    async def request(path):
        return await asyncio.to_thread(api,path)
    health=await request('/health')
    ports=health.get('stun_ports',[])
    if not ports:
        raise ConnectionError('CraftLink traversal needs STUN')
    hub=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    hub.bind(('0.0.0.0',0))
    chosen=None
    success=False
    try:
        from .diagnostics import event
        def log(line):
            event('p2p.craftlink',message=line)
        profile=await stun.measure(hub,servers=[(host,port) for port in ports],timeout=1.2,log=log)
        local_type=craftlink.NatSub(getattr(profile.nat_type,'value','unknown'))
        local_filter=craftlink.Filter(getattr(profile.filtering,'value','unknown'))
        path='/api/connections/'+info['sid']+'/punch'
        target=await asyncio.to_thread(socket.gethostbyname,host)
        beacon=json.dumps({'key':info['punch_key'],'nonce':secrets.token_hex(8),
                           'nat':{'type':local_type.value,'filter':local_filter.value,
                                  'per_ip_pool':bool(profile.per_ip_pool)}}).encode()
        deadline=time.monotonic()+8
        hub.setblocking(False)
        loop=asyncio.get_running_loop()
        while not stopped.is_set() and time.monotonic()<deadline:
            response=await request(path)
            if not response['available']:
                raise ConnectionError('P2P discovery unavailable')
            await loop.sock_sendto(hub,beacon,(target,response['port']))
            if response.get('peer') and response.get('peer_nat'):
                break
            await asyncio.sleep(.4)
        else:
            raise TimeoutError('Peer did not announce CraftLink capability')
        addr=tuple(response['peer'])
        remote=response['peer_nat']
        peer_id=info['player'] if info['side']=='host' else info['host']
        my_id=info[info['side']]
        result=await craftlink.run_punch(*addr,local_type,craftlink.NatSub(remote['type']),
                                        hub_sock=hub,log=log,timeout=12,
                                        my_filter=local_filter,peer_filter=craftlink.Filter(remote['filter']),
                                        per_ip_pool=bool(profile.per_ip_pool),my_id=my_id,peer_id=peer_id)
        chosen=result.sock
        if not result.ok or result.addr[0]!=addr[0]:
            raise ConnectionError('CraftLink did not find an authenticated peer candidate')
        await authenticate_punched_socket(chosen,result.addr,info)
        success=True
        return chosen,result.addr
    finally:
        if not success or chosen is not hub:
            hub.close()
        if chosen is not None and not success:
            chosen.close()


async def connect_peer(info,api,url,manager,stopped):
    try:
        sock,addr=await craftlink_candidate(info,api,url,stopped)
    except (OSError,ValueError,KeyError) as error:
        from .diagnostics import event
        event('p2p.craftlink.fallback',error=error)
        if stopped.is_set():
            raise
        sock,addr=await asyncio.to_thread(punch,info,api,url,stopped)
    link=SimpleNamespace(sock=sock,punched_sock=sock,peer_addr=addr,carried=False,
        stop_keepalive=lambda:None,start_keepalive=lambda:None)
    peer=AutoPeer(info['player'] if info['side']=='host' else info['host'],link,manager,peer_addr=addr)
    try:
        if not await peer.ensure_started():raise ConnectionError('Reliable UDP carrier did not start')
        return peer,sock
    except BaseException:
        peer.close();sock.close();raise
