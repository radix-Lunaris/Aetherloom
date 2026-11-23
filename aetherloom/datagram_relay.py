"""Authenticated datagram forwarding on the relay's public UDP port."""
import asyncio
import secrets
import time
from dataclasses import dataclass, field



MAGIC = b"CL1U"
LEASE = 8
MAX_PACKET = 65507


@dataclass
class Attachment:
    key: bytes = field(default_factory=lambda: secrets.token_bytes(16))
    addr: tuple = None
    seen: float = 0
    challenge: tuple = None


class DatagramRelay(asyncio.DatagramProtocol):
    def __init__(self):
        self.pairs = {}
        self.routes = {}
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport

    def datagram_received(self, packet, addr):
        if not 21 <= len(packet) <= MAX_PACKET or packet[:4] != MAGIC:
            return
        route = self.routes.get(packet[4:20])
        if route is None:
            return
        pair, side = route
        if time.monotonic()>pair.get(("expiry",side),0):return
        source = pair[side]
        target = pair.get(1 - side)
        now = time.monotonic()
        if len(packet) == 37 and packet[20] == 0:
            if addr == source.addr and now - source.seen <= LEASE:
                source.seen = now
                self.transport.sendto(MAGIC + source.key + b"\x00", addr)
            else:
                nonce = secrets.token_bytes(16)
                source.challenge = addr, nonce, now
                self.transport.sendto(MAGIC + source.key + b"\x02" + nonce, addr)
        elif len(packet) == 37 and packet[20] == 2 and source.challenge:
            wanted_addr, nonce, sent = source.challenge
            if wanted_addr == addr and now - sent <= LEASE and secrets.compare_digest(nonce, packet[21:]):
                source.addr, source.seen = addr, now
                source.challenge = None
                self.transport.sendto(MAGIC + source.key + b"\x00", addr)
        elif (len(packet) >= 25 and packet[20] == 1 and source.addr == addr
              and now - source.seen <= LEASE and target and now<pair.get(("expiry",1-side),0) and now - target.seen <= LEASE):
            self.transport.sendto(MAGIC + target.key + packet[20:], target.addr)

    def grant(self, sid, side):
        now=time.monotonic()
        for key,pair in list(self.pairs.items()):
            if pair["expires"]<=now:
                for index in (0,1):
                    if index in pair:
                        self.routes.pop(pair[index].key,None)
                self.pairs.pop(key)
        pair=self.pairs.setdefault(sid,{"direct":secrets.token_bytes(16)})
        pair["expires"]=now+8
        attachment=pair.setdefault(side,Attachment())
        self.routes[attachment.key]=pair,side
        pair[("expiry",side)]=now+8
        return {"relay":attachment.key.hex(),"direct":pair["direct"].hex(),
                "port":self.transport.get_extra_info("sockname")[1]}
