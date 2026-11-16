"""CraftLink logical streams carried by authenticated TLS WebSockets."""
import asyncio
import contextlib
import json
import threading
import weakref
from urllib.parse import urlsplit, urlunsplit
from .vendor.craftlink.auto_stream import AutoManager, AutoStream, Config, TcpPath, Kind


class PolicyStream(AutoStream):
    async def run(self):
        # Keep outer shutdown cancellation from interrupting the upstream
        # finally block while it joins readers and releases memory reservations.
        worker=asyncio.create_task(super().run())
        try:
            return await asyncio.shield(worker)
        except asyncio.CancelledError:
            self.reason='stopped';self.done.set()
            try:
                await asyncio.wait_for(asyncio.shield(worker),5)
            except asyncio.TimeoutError:
                worker.cancel()
                await asyncio.gather(worker,return_exceptions=True)
            except Exception:
                pass
            raise

    async def send_on(self,name,frame):
        if self.metadata.get('mode')=='DIRECT' and name=='relay' and frame.kind==Kind.DATA:
            return False
        return await super().send_on(name,frame)


class SocketWriter:
    def __init__(self,ws):
        self.ws=ws;self.pending=bytearray();self.closing=False

    def write(self,data):
        if len(self.pending)+len(data)>65580:raise ValueError('Frame buffer exceeded')
        self.pending.extend(data)

    async def drain(self):
        data=bytes(self.pending);self.pending.clear()
        await self.ws.send(data)

    def close(self):
        if not self.closing:
            self.closing=True;asyncio.create_task(self.ws.close())

    def is_closing(self):return self.closing


class WebSocketPath(TcpPath):
    def __init__(self,ws):
        self.ws=ws
        super().__init__(asyncio.StreamReader(limit=128*1024),SocketWriter(ws))
        self.pump=asyncio.create_task(self.receive())

    async def receive(self):
        try:
            async for data in self.ws:
                if not isinstance(data,bytes):raise ValueError('Unexpected control data')
                # Backpressure follows the bounded websocket receive queue.
                while len(self.reader._buffer)>128*1024:await asyncio.sleep(.01)
                self.reader.feed_data(data)
        except Exception as e:self.reader.set_exception(ConnectionError(type(e).__name__))
        finally:self.reader.feed_eof()

    def close(self):
        super().close();self.pump.cancel()


class Network:
    def __init__(self,url,token,request,on_status=None):
        self.url,self.token,self.request=url,token,request
        self.on_status=on_status or (lambda state:None)
        self.peers={};self.peer_sockets={};self.groups=set();self.stopped=threading.Event()
        self.manager=AutoManager(candidate=lambda peer:self.peers.get(peer),on_status=on_status,config=Config(memory_limit=64*1024*1024))
        self.bytes_up=self.bytes_down=0
        self.manager.on_traffic=self.traffic
        self.metrics_started=False
        self.tasks=set();self.server=None
        self.paths=weakref.WeakSet()

    def traffic(self,path,up,down):
        self.bytes_up+=up;self.bytes_down+=down

    async def metrics(self):
        import time
        last=time.monotonic();up=down=0
        while not self.stopped.is_set():
            now=time.monotonic();elapsed=max(.001,now-last)
            self.on_status(dict(session_id='metrics',channel='metrics',bytes_up=self.bytes_up,bytes_down=self.bytes_down,
                speed_up=(self.bytes_up-up)/elapsed,speed_down=(self.bytes_down-down)/elapsed,
                local_links=sum(not s.network_only for s in self.manager.streams.values())))
            last=now;up=self.bytes_up;down=self.bytes_down
            await asyncio.sleep(1)

    def start_metrics(self):
        if not self.metrics_started:self.metrics_started=True;self.spawn(self.metrics())

    async def path(self,info):
        from websockets.asyncio.client import connect
        parts=urlsplit(self.url)
        url=urlunsplit(('wss' if parts.scheme=='https' else 'ws',parts.netloc,'/api/relay','',''))
        ws=await connect(url,max_size=65580,max_queue=4,proxy=None,open_timeout=10)
        try:
            await ws.send(json.dumps(dict(token=self.token,sid=info['sid'],side=info['side'],resume=info['resume'])))
            response=json.loads(await asyncio.wait_for(ws.recv(),10))
            if not response.get('ok'):raise PermissionError('Relay attachment rejected')
            path=WebSocketPath(ws);self.paths.add(path);return path
        except BaseException:
            await ws.close();raise

    async def run_stream(self,info,reader,writer):
        async def reconnect():return await self.path(info)
        try:
            path=await self.path(info)
            stream=PolicyStream(self.manager,info['sid'],info['player'] if info['side']=='host' else info['host'],
                info['side']=='host',reader,writer,path,reconnect,metadata={'generation':info['epoch'],'mode':info.get('mode','AUTO'),'channel':info.get('channel','data')})
            await stream.run()
        finally:
            if writer:
                writer.close()
                with contextlib.suppress(Exception):await writer.wait_closed()

    async def peer_group(self,info):
        if info['sid'] in self.groups:return
        self.groups.add(info['sid'])
        self.spawn(self.run_stream(info,None,None))
        def progress(stage,attempt=0):
            self.on_status(dict(session_id=info['sid'],channel='network',peer=info['player'] if info['side']=='host' else info['host'],mode=info.get('mode','AUTO'),stage=stage,attempt=attempt))
        if info.get('mode')=='RELAY':
            progress('仅中继，不尝试打洞');return
        from .p2p import connect_peer
        async def attempt():
            peer_id=info['player'] if info['side']=='host' else info['host']
            for number,delay in enumerate((0,5,15,30,60),1):
                if self.stopped.is_set():return
                if delay:await asyncio.sleep(delay)
                try:
                    progress('认证端点发现与 UDP 打洞中',number)
                    peer,sock=await connect_peer(info,self.request,self.url,self.manager,self.stopped)
                    progress('UDP 承载已建立，等待流验证后迁移',number)
                    self.peers[peer_id]=peer;self.peer_sockets[peer_id]=sock
                    await peer.closed_event().wait()
                    self.peers.pop(peer_id,None);self.peer_sockets.pop(peer_id,None);sock.close()
                except (OSError,ValueError) as error:
                    progress('打洞失败：'+type(error).__name__+('；保留中继' if info.get('mode')!='DIRECT' else '；仅直连禁止中继游戏数据'),number)
            progress('本轮打洞重试结束；'+('继续使用中继' if info.get('mode')!='DIRECT' else '直连不可用，请修改房间策略后重试'),5)
        self.spawn(attempt())

    def spawn(self,coro):
        task=asyncio.create_task(coro);self.tasks.add(task)
        def finished(task):
            self.tasks.discard(task)
            if not task.cancelled() and task.exception():
                from .diagnostics import safe,event
                error=task.exception()
                event('network.task.failed',error=error)
                self.on_status(dict(session_id='engine',channel='network',stage='联机任务异常：'+safe(type(error).__name__+': '+str(error))))
        task.add_done_callback(finished)
        return task

    async def listen(self,room,identity=None):
        self.start_metrics()
        async def accepted(reader,writer):
            try:
                info=await asyncio.to_thread(self.request,'/api/rooms/'+room+'/connections',{'identity':identity} if identity else {})
                await self.peer_group(info['network'])
                await self.run_stream(info,reader,writer)
            except Exception as error:
                from .diagnostics import safe,event
                event('network.connect.failed',error=error)
                self.on_status(dict(session_id='engine',channel='network',stage='联机连接失败：'+safe(str(error))))
                writer.close()
        self.server=await asyncio.start_server(lambda r,w:self.spawn(accepted(r,w)),'127.0.0.1',0)
        return self.server.sockets[0].getsockname()[1]

    async def host(self,room,port,on_identity=None):
        self.start_metrics()
        attached=set()
        async def attach(info):
            if on_identity and info.get('identity'):on_identity(info['identity'])
            reader,writer=await asyncio.open_connection('127.0.0.1',port)
            await self.run_stream(info,reader,writer)
        while True:
            items=await asyncio.to_thread(self.request,'/api/rooms/'+room+'/connections')
            for info in items:
                if info['sid'] not in attached:
                    attached.add(info['sid'])
                    if info.get('channel')=='network':await self.peer_group(info)
                    else:self.spawn(attach(info))
            await asyncio.sleep(.5)

    async def close(self):
        self.stopped.set()
        if self.server:self.server.close();await self.server.wait_closed()
        self.manager.close()
        for task in list(self.tasks):task.cancel()
        await asyncio.gather(*list(self.tasks),return_exceptions=True)
        for path in list(self.paths):
            path.close()
            with contextlib.suppress(Exception):await asyncio.wait_for(path.ws.close(),3)
        for peer in self.peers.values():peer.close()
        for sock in self.peer_sockets.values():sock.close()
        self.peers.clear();self.peer_sockets.clear()
