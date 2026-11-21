"""Bounded UDP endpoint discovery; only HTTPS-issued capabilities get replies."""
import json
from .vendor.craftlink.nat_types import NatSub, Filter
import socket
import threading
import time


class Rendezvous:
    def __init__(self,bind):
        host,port=bind.rsplit(':',1)
        self.socket=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.socket.bind((host,int(port)));self.socket.settimeout(.5)
        self.entries={};self.lock=threading.Lock();self.stopped=threading.Event()
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()

    def register(self,key):
        with self.lock:
            now=time.monotonic()
            self.entries={k:v for k,v in self.entries.items() if v[0]>now}
            if key not in self.entries and len(self.entries)>=512:raise ValueError('P2P注册数量已满')
            old=self.entries.get(key,(0,None,None))
            self.entries[key]=(now+30,old[1],old[2])

    def endpoint(self,key):
        with self.lock:
            entry=self.entries.get(key)
            return entry[1] if entry and entry[0]>time.monotonic() else None

    def profile(self,key):
        with self.lock:
            entry=self.entries.get(key)
            return entry[2] if entry and entry[0]>time.monotonic() else None

    def run(self):
        while not self.stopped.is_set():
            try:
                data,addr=self.socket.recvfrom(1024)
                if len(data)>512:continue
                message=json.loads(data);key=message.get('key');nonce=message.get('nonce')
                if not isinstance(key,str) or not isinstance(nonce,str) or len(nonce)>32:continue
                with self.lock:
                    entry=self.entries.get(key)
                    if not entry or entry[0]<time.monotonic():continue
                    raw=message.get('nat')
                    profile=None
                    if isinstance(raw,dict):
                        profile={'type':NatSub(raw.get('type')).value,'filter':Filter(raw.get('filter')).value,
                                 'per_ip_pool':raw.get('per_ip_pool') is True}
                    self.entries[key]=(entry[0],addr,profile)
                self.socket.sendto(json.dumps({'nonce':nonce,'observed':addr}).encode(),addr)
            except (socket.timeout,ValueError,TypeError,AttributeError):pass
            except OSError:
                if not self.stopped.is_set():raise

    def close(self):
        self.stopped.set();self.thread.join(timeout=2);self.socket.close()
