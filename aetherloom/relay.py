"""Authenticated TLS-WebSocket carrier for CraftLink end-to-end AUTO frames.

Control accounts are checked by the control API. Per-stream side secrets and
host epochs isolate members, generations and resumed physical attachments.
This is the relay carrier, not a claim that NAT traversal is complete.
"""
import asyncio
import secrets
import time
import uuid
from dataclasses import dataclass, field
from fastapi import HTTPException, WebSocket, WebSocketDisconnect
from .vendor.craftlink.auto_stream import Decoder,Kind


@dataclass
class Pair:
    room: str
    epoch: int
    host: str
    player: str
    sid: str = field(default_factory=lambda: uuid.uuid4().hex)
    secrets: dict = field(default_factory=lambda: {s:secrets.token_urlsafe(32) for s in ('host','player')})
    ends: dict = field(default_factory=dict)
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    touched: float = field(default_factory=time.monotonic)
    channel: str = 'data'
    punch_keys: dict = field(default_factory=lambda: {s:secrets.token_urlsafe(32) for s in ('host','player')})
    shared: str = field(default_factory=lambda:secrets.token_hex(32))
    mode: str = 'AUTO'
    reports: dict = field(default_factory=dict)
    revoked: bool = False
    identity: dict | None = None


class Relay:
    def __init__(self, store, authenticate,authorize=None):
        self.store,self.authenticate=store,authenticate
        self.pairs={}
        self.rendezvous=None
        self.authorize=authorize

    def room(self, room):
        with self.store.connect() as c:
            r=c.execute('SELECT * FROM rooms WHERE id=?',(room,)).fetchone()
        if not r:raise HTTPException(404,'房间不存在')
        if not r['token'] or r['expires']<=time.time():raise HTTPException(409,'当前Host租约已失效')
        return r

    def collect(self):
        for sid,p in list(self.pairs.items()):
            if not p.ends and time.monotonic()-p.touched>45:self.pairs.pop(sid,None)

    def rename(self,old,new):
        for pair in self.pairs.values():
            if pair.host==old:pair.host=new
            if pair.player==old:pair.player=new

    def create(self,room,actor,identity=None):
        self.collect();r=self.room(room)
        if r['state']!='ready':raise HTTPException(409,'Host世界和网络尚未就绪')
        if actor==r['host']:raise HTTPException(409,'Host不能加入自己的联机通道')
        if len(self.pairs)>=256 or sum(p.player==actor for p in self.pairs.values())>=16:
            raise HTTPException(429,'联机通道数量已达到限制')
        with self.store.connect() as c:
            settings=c.execute('SELECT mode FROM room_settings WHERE room=?',(room,)).fetchone()
        mode=settings['mode'] if settings and settings['mode'] else 'AUTO'
        if identity is not None:
            from .game_accounts import profile
            from .launcher import game_uuid
            try:
                if not isinstance(identity,dict) or not isinstance(identity.get('name'),str):
                    raise ValueError('Invalid peer identity')
                player=profile({'name':identity['name'],'id':game_uuid(identity['name'],identity.get('uuid'))})
            except (ValueError,TypeError,KeyError):
                raise HTTPException(400,'游戏身份名称或 UUID 无效') from None
            identity={'name':player['name'],'uuid':player['id']}
            for pair in self.pairs.values():
                if pair.room!=room or pair.epoch!=r['epoch'] or not pair.identity:continue
                if pair.player==actor and pair.identity!=identity:raise HTTPException(409,'当前会话不能变更游戏身份')
                if pair.player!=actor and (pair.identity['name'].lower()==identity['name'].lower() or pair.identity['uuid']==identity['uuid']):
                    raise HTTPException(409,'游戏名称或UUID已被当前会话其他成员使用')
        group=next((p for p in self.pairs.values() if p.room==room and p.epoch==r['epoch'] and p.host==r['host'] and p.player==actor and p.channel=='network'),None)
        if not group:
            group=Pair(room,r['epoch'],r['host'],actor,channel='network',mode=mode,identity=identity);self.pairs[group.sid]=group
        p=Pair(room,r['epoch'],r['host'],actor,mode=mode,identity=identity);self.pairs[p.sid]=p
        return dict(self.info(p,'player'),network=self.info(group,'player'))

    @staticmethod
    def info(p,side):
        result=dict(sid=p.sid,room=p.room,epoch=p.epoch,host=p.host,player=p.player,resume=p.secrets[side],side=side,path='relay',channel=p.channel,mode=p.mode)
        if p.channel=='network':result.update(punch_key=p.punch_keys[side],shared=p.shared)
        if p.identity:result['identity']=dict(p.identity,actor=p.player)
        return result

    def punch(self,sid,user):
        p=self.pairs.get(sid)
        if not p or p.channel!='network':raise HTTPException(404,'P2P会话不存在')
        r=self.room(p.room)
        if r['epoch']!=p.epoch or r['host']!=p.host:raise HTTPException(409,'Host代次已变化')
        side='host' if user==p.host else 'player' if user==p.player else None
        if not side:raise HTTPException(403,'不是此通道成员')
        if not self.rendezvous:return {'available':False}
        for key in p.punch_keys.values():self.rendezvous.register(key)
        opposite='player' if side=='host' else 'host'
        return {'available':True,'peer':self.rendezvous.endpoint(p.punch_keys[opposite]),'peer_nat':self.rendezvous.profile(p.punch_keys[opposite]),'port':self.rendezvous.socket.getsockname()[1]}

    def pending(self,room,user):
        self.collect();r=self.room(room)
        if r['host']!=user:raise HTTPException(403,'需要当前Host身份')
        return [self.info(p,'host') for p in self.pairs.values() if p.room==room and p.epoch==r['epoch'] and p.host==user and not p.revoked]

    async def websocket(self,ws:WebSocket):
        await ws.accept()
        p=None;side=None
        try:
            hello=await asyncio.wait_for(ws.receive_json(),10)
            user=await asyncio.to_thread(self.authenticate,'Bearer '+hello.get('token',''))
            p=self.pairs.get(hello.get('sid'));side=hello.get('side')
            if not p or p.revoked or side not in ('host','player'):raise ValueError('Invalid stream')
            if self.authorize:await asyncio.to_thread(self.authorize,p.room,user)
            r=await asyncio.to_thread(self.room,p.room)
            if r['epoch']!=p.epoch or r['host']!=p.host or user['name']!=getattr(p,side) or not secrets.compare_digest(p.secrets[side],hello.get('resume','')):
                raise ValueError('Invalid stream scope')
            old=p.ends.get(side);p.ends[side]=ws;p.changed.set();p.touched=time.monotonic()
            if old and old is not ws:await old.close(code=1012)
            await ws.send_json({'ok':True})
            opposite='player' if side=='host' else 'host'
            checked=time.monotonic()
            while p.ends.get(side) is ws:
                data=await asyncio.wait_for(ws.receive_bytes(),30)
                if len(data)>65580:raise ValueError('Frame too large')
                decoder=Decoder();frames=decoder.feed(data)
                if len(frames)!=1 or decoder.buffer or frames[0].session!=p.sid:raise ValueError('Invalid frame scope')
                if p.mode=='DIRECT' and frames[0].kind==Kind.DATA:raise ValueError('Relay payload forbidden by direct-only policy')
                if time.monotonic()-checked>2:
                    current=await asyncio.to_thread(self.room,p.room)
                    current_user=await asyncio.to_thread(self.authenticate,'Bearer '+hello.get('token',''))
                    if self.authorize:await asyncio.to_thread(self.authorize,p.room,current_user)
                    if current['epoch']!=p.epoch or current['host']!=p.host or current_user['name']!=getattr(p,side):raise ValueError('Host/account changed')
                    checked=time.monotonic()
                # A physical attachment can retry without discarding the
                # logical stream. Bound orphan waits below server shutdown.
                deadline=time.monotonic()+4
                while not p.ends.get(opposite):
                    if p.ends.get(side) is not ws:return
                    p.changed.clear()
                    if p.ends.get(opposite):break
                    await asyncio.wait_for(p.changed.wait(),max(.01,deadline-time.monotonic()))
                await asyncio.wait_for(p.ends[opposite].send_bytes(data),10)
                p.touched=time.monotonic()
        except (WebSocketDisconnect,TimeoutError,ValueError,HTTPException,RuntimeError,KeyError):
            pass
        finally:
            if p and p.ends.get(side) is ws:
                p.ends.pop(side,None)
                # Detach both physical ends of this one SID. This wakes a
                # counterpart waiting for reattachment when its socket closed;
                # logical streams retain their ACK/replay state and reconnect.
                other=p.ends.pop('player' if side=='host' else 'host',None)
                p.changed.set();p.touched=time.monotonic()
                if other:
                    try:await other.close(code=1012)
                    except (RuntimeError,WebSocketDisconnect):pass
            try:await ws.close()
            except (RuntimeError,WebSocketDisconnect):pass
