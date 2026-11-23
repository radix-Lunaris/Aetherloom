"""Forward application datagrams over a punched link or an authenticated relay."""
import asyncio
import secrets
import struct
import threading
import time

from urllib.parse import urlsplit
from . import protocol as proto
from .common import close_writer

RELAY = b"CL1U"
DIRECT = b"CL1D"
MAX_PAYLOAD = 65507 - 25
FLOW_IDLE = 120
MAX_FLOWS = 32


class Receiver(asyncio.DatagramProtocol):
    def __init__(self, receive):
        self.receive = receive

    def datagram_received(self, data, addr):
        self.receive(data, addr)


class Peer:
    def __init__(self, forwarder, peer_id, mode):
        self.owner = forwarder
        self.peer_id = peer_id
        self.mode = mode
        self.relay = self.carrier = None
        self.relay_seen = self.direct_seen = 0
        self.challenge = b""
        self.backends = {}
        self.pending = {}
        self.direct_slots = threading.BoundedSemaphore(128)

    def send(self, flow, payload):
        if len(payload) > MAX_PAYLOAD:
            return
        frame = b"\x01" + struct.pack("!I", flow) + payload
        now = time.monotonic()
        if self.carrier and self.direct_seen and now - self.direct_seen < 4 and self.send_direct(frame):
            return
        if self.mode != "stun" and self.relay and self.relay_seen and now - self.relay_seen < 7:
            self.relay.sendto(RELAY + self.relay_key + frame)

    def send_direct(self, frame):
        carrier = self.carrier
        if carrier is None or carrier.stop.is_set():
            return False
        try:
            carrier.sock.sendto(DIRECT + self.direct_key + frame, carrier.tunnel.send_to)
            return True
        except OSError:
            return False

    def direct_receiver(self, carrier, loop):
        def receive(packet, addr):
            tunnel = carrier.tunnel
            if (tunnel and packet[:20] == DIRECT + self.direct_key and addr == tunnel.send_to
                    and self.direct_slots.acquire(blocking=False)):
                try:
                    loop.call_soon_threadsafe(self.receive_direct, carrier, packet[20:])
                except RuntimeError:
                    self.direct_slots.release()
        return receive

    def receive_direct(self, carrier, frame):
        self.direct_slots.release()
        if carrier is not self.carrier or not frame:
            return
        if frame[0] == 0 and len(frame) == 9:
            self.send_direct(b"\x02" + frame[1:])
        elif frame[0] == 2 and self.challenge and frame[1:] == self.challenge:
            self.direct_seen = time.monotonic()
        elif frame[0] == 1:
            self.deliver(frame)

    def receive_relay(self, packet, _addr):
        if packet[:20] != RELAY + self.relay_key:
            return
        frame = packet[20:]
        if frame == b"\x00":
            self.relay_seen = time.monotonic()
        elif len(frame) == 17 and frame[0] == 2:
            self.relay.sendto(RELAY + self.relay_key + frame)
        elif self.mode != "stun":
            self.deliver(frame)

    def deliver(self, frame):
        if len(frame) < 5 or frame[0] != 1:
            return
        flow = struct.unpack_from("!I", frame, 1)[0]
        payload = frame[5:]
        if not self.owner.is_host:
            slot = self.owner.clients_by_id.get(flow)
            if slot:
                self.owner.listener.sendto(payload, slot[0])
        elif flow in self.backends:
            transport, _ = self.backends[flow]
            self.backends[flow] = transport, time.monotonic()
            transport.sendto(payload)
        elif flow in self.pending:
            task, packets = self.pending[flow]
            if len(packets) < 8:
                packets.append(payload)
        elif len(self.backends) + len(self.pending) < MAX_FLOWS:
            packets = [payload]
            self.pending[flow] = asyncio.create_task(self.open_backend(flow, packets)), packets

    async def open_backend(self, flow, packets):
        core = self.owner.core
        try:
            transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
                lambda: Receiver(lambda data, _: self.send(flow, data)),
                remote_addr=(core.mc_host, core.mc_port))
            self.backends[flow] = transport, time.monotonic()
            for data in packets:
                transport.sendto(data)
        except OSError as exc:
            core.log(f"[UDP] local backend: {exc}")
        finally:
            self.pending.pop(flow, None)

    async def tick(self):
        loop = asyncio.get_running_loop()
        while True:
            if self.relay:
                self.relay.sendto(RELAY + self.relay_key + b"\x00" + bytes(16))
            carrier = self.owner.carrier(self.peer_id) if self.mode != "relay" else None
            if carrier is not self.carrier:
                self.detach_direct()
                self.carrier = carrier
                if carrier:
                    carrier.hub.application_datagrams = self.direct_receiver(carrier, loop)
            if carrier:
                self.challenge = secrets.token_bytes(8)
                self.send_direct(b"\x00" + self.challenge)
            now = time.monotonic()
            for flow, (transport, seen) in list(self.backends.items()):
                if now - seen > FLOW_IDLE:
                    self.backends.pop(flow)
                    transport.close()
            await asyncio.sleep(1)

    def detach_direct(self):
        if self.carrier and self.carrier.hub:
            self.carrier.hub.application_datagrams = None
        self.carrier = None
        self.direct_seen = 0

    async def run(self):
        core = self.owner.core
        loop = asyncio.get_running_loop()
        while core.running:
            writer = tick = None
            try:
                side = "host" if self.owner.is_host else "player"
                path = "/api/connections/"+self.info["sid"]+"/datagrams"
                grant=await asyncio.to_thread(core.request,path)
                self.relay_key=bytes.fromhex(grant["relay"])
                self.direct_key=bytes.fromhex(grant["direct"])
                if self.mode!="stun":
                    self.relay,_=await loop.create_datagram_endpoint(
                        lambda:Receiver(self.receive_relay),remote_addr=(urlsplit(core.url).hostname,grant["port"]))
                tick=asyncio.create_task(self.tick())
                while core.running:
                    await asyncio.sleep(3)
                    current=await asyncio.to_thread(core.request,path)
                    if current!=grant:
                        break
            except (OSError, ValueError, RuntimeError, asyncio.TimeoutError) as exc:
                core.log(f"[UDP] peer {self.peer_id}: {exc}")
            finally:
                if tick:
                    tick.cancel()
                    await asyncio.gather(tick, return_exceptions=True)
                self.detach_direct()
                if self.relay:
                    self.relay.close()
                    self.relay = None
                self.relay_seen = 0
                pending = [task for task, _ in self.pending.values()]
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                self.pending.clear()
                for transport, _ in self.backends.values():
                    transport.close()
                self.backends.clear()
                if writer:
                    await close_writer(writer)
            await asyncio.sleep(2)


class Forwarder:
    def __init__(self, core, engine, is_host):
        self.core = core
        self.engine = engine
        self.is_host = is_host
        self.listener = None
        self.clients_by_id = {}
        self.clients = {}
        self.peers = {}

    def carrier(self, peer):
        return self.core.peers.get(peer)

    def local_packet(self, payload, addr):
        now=time.monotonic()
        if len(self.clients)>=MAX_FLOWS:
            for previous,(address,seen) in list(self.clients_by_id.items()):
                if now-seen>FLOW_IDLE:
                    self.clients.pop(address,None)
                    self.clients_by_id.pop(previous,None)
        flow = self.clients.get(addr)
        if flow is None:
            if len(self.clients) >= MAX_FLOWS:
                return
            flow = secrets.randbits(32)
            while flow in self.clients_by_id:
                flow = secrets.randbits(32)
            self.clients[addr] = flow
        self.clients_by_id[flow] = addr, time.monotonic()
        for peer, _ in self.peers.values():
            peer.send(flow, payload)

    async def bind(self,port):
        self.listener,_=await asyncio.get_running_loop().create_datagram_endpoint(
            lambda:Receiver(self.local_packet),local_addr=("127.0.0.1",port))

    def attach(self,info):
        target=info["player"] if self.is_host else info["host"]
        mode={"DIRECT":"stun","RELAY":"relay","AUTO":"auto"}[info["mode"]]
        key=(target,mode)
        if key not in self.peers:
            peer=Peer(self,target,mode)
            peer.info=info
            self.peers[key]=(peer,self.core.spawn(peer.run()))

    def close(self):
        if self.listener:
            self.listener.close()
