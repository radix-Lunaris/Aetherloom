"""Transient room presence; never used to elect or authorize a Host."""
import threading,time

class Presence:
    def __init__(self,clock=time.monotonic,ttl=45):self.clock,self.ttl=clock,ttl;self.rows={};self.lock=threading.Lock()
    def heartbeat(self,actor,device,room,active=True):
        now=self.clock()
        with self.lock:
            self.rows={key:value for key,value in self.rows.items() if now-value[1]<self.ttl}
            if active:self.rows[actor,device]=(room,now)
            else:self.rows.pop((actor,device),None)
            return len({key[0] for key,value in self.rows.items() if value[0]==room})
