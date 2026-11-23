import asyncio
from types import SimpleNamespace
import unittest

from aetherloom.datagram_relay import DatagramRelay
from aetherloom.vendor.craftlink.udp_forward import Forwarder, Receiver


class ApplicationUdp(unittest.IsolatedAsyncioTestCase):
    async def test_relay_preserves_datagrams_and_routes_replies(self):
        loop=asyncio.get_running_loop()
        relay_transport,relay=await loop.create_datagram_endpoint(DatagramRelay,local_addr=("127.0.0.1",0))
        echo,_=await loop.create_datagram_endpoint(lambda:Receiver(lambda data,addr:echo.sendto(data,addr)),local_addr=("127.0.0.1",0))
        jobs=[]
        def spawn(coro):
            jobs.append(asyncio.create_task(coro))
            return jobs[-1]
        def core(side):
            grant=relay.grant("test",side)
            return SimpleNamespace(running=True,peers={},spawn=spawn,url="http://127.0.0.1",
                log=lambda _:None,mc_host="127.0.0.1",mc_port=echo.get_extra_info("sockname")[1],
                request=lambda _:grant)
        player=Forwarder(core(1),None,False)
        host=Forwarder(core(0),None,True)
        received=asyncio.Queue()
        sender,_=await loop.create_datagram_endpoint(lambda:Receiver(lambda data,_:received.put_nowait(data)),local_addr=("127.0.0.1",0))
        try:
            await player.bind(0)
            info=dict(sid="test",mode="RELAY",host="a",player="b")
            player.attach(info)
            host.attach(info)
            async with asyncio.timeout(4):
                while not all(next(iter(f.peers.values()))[0].relay_seen for f in (host,player)):
                    await asyncio.sleep(.01)
            for packet in (b"hello",bytes(range(220))):
                sender.sendto(packet,player.listener.get_extra_info("sockname"))
                self.assertEqual(await asyncio.wait_for(received.get(),2),packet)
        finally:
            for task in jobs:task.cancel()
            await asyncio.gather(*jobs,return_exceptions=True)
            player.close()
            host.close()
            sender.close()
            echo.close()
            relay_transport.close()
