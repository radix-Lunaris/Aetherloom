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


async def connect_peer(info,api,url,manager,stopped):
    sock,addr=await asyncio.to_thread(punch,info,api,url,stopped)
    link=SimpleNamespace(sock=sock,punched_sock=sock,peer_addr=addr,carried=False,
        stop_keepalive=lambda:None,start_keepalive=lambda:None)
    peer=AutoPeer(info['player'] if info['side']=='host' else info['host'],link,manager,peer_addr=addr)
    try:
        if not await peer.ensure_started():raise ConnectionError('Reliable UDP carrier did not start')
        return peer,sock
    except BaseException:
        peer.close();sock.close();raise
