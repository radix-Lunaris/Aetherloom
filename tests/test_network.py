import asyncio
import os
import socket
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import uvicorn
from aetherloom.cloud import API
from aetherloom.network import Network
from aetherloom.server import create_app,add_user
from aetherloom.vendor.craftlink.auto_stream import Frame,Kind


class NetworkTests(unittest.TestCase):
    def test_real_websocket_and_udp_transport(self):
        with tempfile.TemporaryDirectory() as d,patch.dict(os.environ,{'AETHERLOOM_P2P_BIND':'127.0.0.1:0'}),self.assertNoLogs('uvicorn.error',level='ERROR'):
            app=create_app(d)
            for name in ('host','guest'):add_user(app.state.store,name,'123456','player')
            sock=socket.socket();sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
            server=uvicorn.Server(uvicorn.Config(app,log_level='error',lifespan='on',timeout_graceful_shutdown=5))
            thread=threading.Thread(target=lambda:server.run(sockets=[sock]),daemon=True);thread.start()
            try:
                deadline=time.monotonic()+10
                while not server.started:
                    if time.monotonic()>deadline:raise TimeoutError('API startup')
                    time.sleep(.02)
                url='http://127.0.0.1:'+str(port)
                def login(name):
                    api=API(url,'');r=api('/api/login',dict(username=name,password='123456'));return API(url,r['token'])
                host,guest=login('host'),login('guest')
                room=host('/api/rooms',{'name':'transport fixture'})['id']
                guest('/api/rooms/'+room+'/join',{})
                lease=host('/api/rooms/'+room+'/claim',{})
                host('/api/rooms/'+room+'/ready',{'token':lease['token'],'epoch':lease['epoch']})
                asyncio.run(self.exercise(url,host,guest,room))
            finally:
                server.should_exit=True;thread.join(timeout=10);sock.close()
                self.assertFalse(thread.is_alive())

    async def exercise(self,url,host_api,guest_api,room):
        async def echo(reader,writer):
            try:
                while data:=await reader.read(65536):
                    writer.write(data);await writer.drain()
            finally:writer.close()
        echo_server=await asyncio.start_server(echo,'127.0.0.1',0)
        states=[]
        host=Network(url,host_api.token,host_api,on_status=lambda s:states.append(s))
        guest=Network(url,guest_api.token,guest_api,on_status=lambda s:states.append(s))
        host.spawn(host.host(room,echo_server.sockets[0].getsockname()[1]))
        reader=writer=None
        try:
            local=await guest.listen(room)
            reader,writer=await asyncio.open_connection('127.0.0.1',local)
            payload=os.urandom(256*1024)
            writer.write(payload);await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.readexactly(len(payload)),15),payload)
            deadline=time.monotonic()+20
            while not any(s.get('active_path')=='direct' for s in states):
                if time.monotonic()>deadline:
                    raise AssertionError('P2P never became validated direct: '+str([(s.get('active_path'),s.get('switch_phase')) for s in states[-6:]]))
                await asyncio.sleep(.1)
            # Multiple data flows share one reliable carrier; stopping one keeps the other alive.
            self.assertEqual(len(host.peers),1);self.assertEqual(len(guest.peers),1)
            writer.write(payload);await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.readexactly(len(payload)),10),payload)
            reader2,writer2=await asyncio.open_connection('127.0.0.1',local)
            writer2.write(b'second stream');await writer2.drain()
            self.assertEqual(await asyncio.wait_for(reader2.readexactly(13),10),b'second stream')
            writer2.close();await writer2.wait_closed()
            for peer in list(guest.peers.values()):peer.close()
            await asyncio.sleep(.5)
            writer.write(b'fallback');await writer.drain()
            self.assertEqual(await asyncio.wait_for(reader.readexactly(8),10),b'fallback')
            await asyncio.sleep(1.1)
            metrics=[s for s in states if s.get('channel')=='metrics']
            self.assertTrue(any(s['bytes_up']>=len(payload) and s['bytes_down']>=len(payload) for s in metrics))
            self.assertTrue(any(s['local_links']>=1 for s in metrics))
        finally:
            if writer:writer.close()
            await guest.close();await host.close()
            echo_server.close();await echo_server.wait_closed()
        # A client can close before the Host attaches; shutdown must not leave
        # that one-sided handler waiting for 15 seconds or emit ASGI errors.
        orphan=Network(url,guest_api.token,guest_api)
        info=await asyncio.to_thread(guest_api,'/api/rooms/'+room+'/connections',{})
        path=await orphan.path(info)
        await path.send(Frame(Kind.ACK,info['sid'],value=256*1024))
        await orphan.close()
