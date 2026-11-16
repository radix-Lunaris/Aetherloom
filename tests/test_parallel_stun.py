import asyncio,hashlib,io,json,socket,struct,tempfile,threading,time,unittest,urllib.request
from pathlib import Path
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from aetherloom.cloud import CloudWorld
from aetherloom.store import Authority
from aetherloom.sync import snapshot
from aetherloom.ranged import download
from aetherloom.vendor.craftlink import stun,stun_server
from aetherloom.presence import Presence

class ParallelTests(unittest.TestCase):
    def test_presence_endpoint_requires_membership_and_never_claims_host(self):
        from fastapi.testclient import TestClient
        from aetherloom.server import create_app,add_user
        with tempfile.TemporaryDirectory() as directory:
            app=create_app(directory)
            for actor in ('owner','guest'):add_user(app.state.store,actor,'123456','player')
            with TestClient(app) as client:
                def headers(actor):return {'Authorization':'Bearer '+client.post('/api/login',json=dict(username=actor,password='123456')).json()['token']}
                owner,guest=headers('owner'),headers('guest');room=client.post('/api/rooms',json={},headers=owner).json()['id']
                route='/api/rooms/'+room+'/presence';body={'device':'a'*32}
                self.assertEqual(client.post(route,json=body,headers=guest).status_code,403)
                self.assertEqual(client.post(route,json=body,headers=owner).json()['online'],1)
                client.post('/api/rooms/'+room+'/join',json={},headers=guest)
                self.assertEqual(client.post(route,json=body,headers=guest).json()['online'],2)
                self.assertEqual(client.get('/api/rooms',headers=owner).json()[0]['state'],'idle')
    def test_room_presence_is_scoped_deduplicated_and_expires(self):
        now=[0];presence=Presence(clock=lambda:now[0])
        self.assertEqual(presence.heartbeat('a','device1','room'),1)
        self.assertEqual(presence.heartbeat('a','device2','room'),1)
        self.assertEqual(presence.heartbeat('b','device3','other'),1)
        self.assertEqual(presence.heartbeat('b','device3','room'),2)
        self.assertEqual(presence.heartbeat('b','device3','room',False),1)
        now[0]=46;self.assertEqual(presence.heartbeat('b','device3','room'),1)
    def test_parallel_cloud_blocks_bounded_verified_and_cache_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);world=root/'source';world.mkdir();(world/'level.dat').write_bytes(b'world')
            for i in range(10):(world/str(i)).write_bytes(bytes([i])*65536)
            authority=Authority(root/'server');manifest=snapshot(world,authority)
            lock=threading.Lock();active=maximum=calls=0;events=[]
            def api(path,**kwargs):
                nonlocal active,maximum,calls
                if path.endswith('/head'):return dict(version='head',manifest=manifest)
                with lock:active+=1;maximum=max(maximum,active);calls+=1
                try:
                    time.sleep(.03);h=path.rsplit('/',1)[1];return (authority.root/'blobs'/h[:2]/h).read_bytes()
                finally:
                    with lock:active-=1
            cloud=CloudWorld(api,root/'cache',on_progress=events.append)
            cloud.download('room',root/'checkout')
            self.assertGreaterEqual(maximum,2);self.assertLessEqual(maximum,4)
            self.assertEqual(events[-1]['percent'],100)
            for entry in world.iterdir():self.assertEqual(entry.read_bytes(),(root/'checkout'/entry.name).read_bytes())
            before=calls;cloud.download('room',root/'checkout');self.assertEqual(calls,before)

    def test_ranges_concurrent_exact_bytes_and_invalid_ranges_rejected(self):
        payload=bytes(range(256))*8192;lock=threading.Lock();active=maximum=0;bad=False
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_GET(self):
                nonlocal active,maximum
                start,end=map(int,self.headers['Range'].removeprefix('bytes=').split('-'))
                with lock:active+=1;maximum=max(maximum,active)
                try:
                    self.send_response(206);self.send_header('Content-Range',f'bytes {start}-{end}/{len(payload)+(1 if bad else 0)}');self.send_header('Content-Length',str(end-start+1));self.end_headers()
                    time.sleep(.03);self.wfile.write(payload[start:end+1])
                finally:
                    with lock:active-=1
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        def opener(url,headers):return urllib.request.urlopen(urllib.request.Request(url,headers=headers),timeout=3)
        try:
            with tempfile.TemporaryDirectory() as directory:
                path=Path(directory)/'runtime.part';events=[];url='http://127.0.0.1:'+str(server.server_port)
                self.assertTrue(download(url,path,len(payload),opener,threading.Event(),lambda n,total:events.append(n)))
                self.assertEqual(path.read_bytes(),payload);self.assertGreaterEqual(maximum,2);self.assertLessEqual(maximum,4)
                self.assertEqual(events,sorted(events));self.assertEqual(events[-1],len(payload))
                bad=True
                with self.assertRaisesRegex(ValueError,'范围'):download(url,Path(directory)/'bad.part',len(payload),opener,threading.Event(),lambda *args:None)
        finally:server.shutdown();server.server_close();thread.join(timeout=3)

class StunWireTests(unittest.TestCase):
    def test_console_encoding_failure_cannot_break_responder(self):
        with patch('builtins.print',side_effect=UnicodeEncodeError('cp1252','就绪',0,1,'unrepresentable')):
            stun_server._log('STUN socket 就绪')

    def test_real_udp_alternate_port_and_strict_filter_simulation(self):
        asyncio.run(self.exercise())

    async def exercise(self):
        probes=[]
        for _ in range(2):
            sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind(('127.0.0.1',0));probes.append(sock)
        ports=tuple(s.getsockname()[1] for s in probes)
        for sock in probes:sock.close()
        with patch.object(stun_server,'STUN_HOST','127.0.0.1'),patch.object(stun_server,'STUN_PORTS',ports),patch.object(stun_server,'STUN_ENABLED',True):
            try:
                self.assertTrue(await stun_server.start_stun_server())
                def client():
                    with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
                        sock.bind(('127.0.0.1',0))
                        return stun.stun_filtering(sock,'127.0.0.1',ports[0],timeout=.08)
                value=await asyncio.to_thread(client)
                self.assertIn(value,('eif','adf','adf_or_eif'))
                # Model a port-restricted firewall by dropping the actual
                # alternate-port response while normal canaries still work.
                alternate=stun_server._server['transports'][1]
                with patch.object(alternate,'sendto',side_effect=lambda *args:None):
                    self.assertEqual(await asyncio.to_thread(client),'apdf')
            finally:await stun_server.stop_stun_server()
