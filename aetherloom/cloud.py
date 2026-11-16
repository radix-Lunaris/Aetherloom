"""Explicit closed-world cloud transfers, never a periodic world scanner."""
import hashlib
import json
from pathlib import Path
import threading
import time
import urllib.error
import urllib.request
from .store import Authority
from .sync import snapshot, materialize
from .world_lock import closed_world
from .diagnostics import event


class API:
    def __init__(self,url,token):self.url,self.token=url.rstrip('/'),token

    def __call__(self,path,body=None,method=None,headers=None,raw=False):
        h={'Authorization':'Bearer '+self.token,**(headers or {})}
        if isinstance(body,bytes):data=body
        elif body is not None:data=json.dumps(body).encode();h['Content-Type']='application/json'
        else:data=None
        request=urllib.request.Request(self.url+path,data=data,headers=h,method=method)
        started=time.monotonic()
        event('api.request',method=request.get_method(),path=path,bytes=len(data or b''))
        try:
            with urllib.request.urlopen(request,timeout=60) as response:
                result=response.read() if raw else json.load(response)
                event('api.response',method=request.get_method(),path=path,status=response.status,elapsed_ms=round((time.monotonic()-started)*1000))
                return result
        except urllib.error.HTTPError as e:
            event('api.error',method=request.get_method(),path=path,status=e.code)
            try:detail=json.load(e).get('detail',str(e))
            except Exception:detail=str(e)
            raise ValueError(str(detail)) from None


class LeaseGuard:
    def __init__(self,api,room,lease):
        self.api,self.room=api,room
        self.lease={'token':lease['token'],'epoch':lease['epoch']}
        self.stopped=threading.Event();self.error=None
        self.last_renewed=time.monotonic()
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()

    def run(self):
        while not self.stopped.wait(5):
            try:
                self.api('/api/rooms/'+self.room+'/renew',self.lease)
                self.last_renewed=time.monotonic()
            except Exception as e:self.error=e;self.stopped.set();break

    def check(self):
        if time.monotonic()-self.last_renewed>45:
            raise ValueError('Host续租已超过保护时限，提前停止共享，保留本地数据')
        if self.error:raise ValueError('Host续租失败，保留本地数据并停止共享：'+str(self.error))

    def close(self):self.stopped.set();self.thread.join(timeout=2)


class CloudWorld:
    def __init__(self,api,cache,progress=None):
        self.api=api;self.cache=Authority(Path(cache));self.progress=progress or (lambda text:None)

    def upload(self,room,world,lease,parent):
        with closed_world(world):
            self.progress('正在流式校验已关闭世界，计算 SHA-256 增量')
            manifest=snapshot(world,self.cache)
            hashes=sorted({p[2] for e in manifest.values() for p in e['pieces']})
            base='/api/rooms/'+room
            sent=0
            for start in range(0,len(hashes),4096):
                result=self.api(base+'/missing',{'lease':lease,'hashes':hashes[start:start+4096]})
                for h in result['missing']:
                    data=(self.cache.root/'blobs'/h[:2]/h).read_bytes()
                    self.api(base+'/blobs/'+h,data,method='PUT',headers={'X-Lease':lease['token'],'X-Epoch':str(lease['epoch'])})
                    sent+=1
                    if sent==1 or sent%16==0 or h==result['missing'][-1]:
                        self.progress(f'增量上传：已发送 {sent} 块，本批缺失 {len(result["missing"])} 块')
            self.progress('增量上传完成，正在提交并确认权威版本')
            return self.api(base+'/commit',dict(lease,parent=parent,manifest=manifest))['version']

    def download(self,room,world):
        result=self.api('/api/rooms/'+room+'/head')
        if result['version'] is None:raise ValueError('此房间尚未发布共同存档，请由所有者先发布')
        hashes={p[2] for e in result['manifest'].values() for p in e['pieces']}
        for index,h in enumerate(sorted(hashes),1):
            if index==1 or index%16==0 or index==len(hashes):self.progress(f'权威存档校验／下载：{index} / {len(hashes)} 块')
            path=self.cache.root/'blobs'/h[:2]/h
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=h:
                data=self.api('/api/rooms/'+room+'/blobs/'+h,raw=True)
                if hashlib.sha256(data).hexdigest()!=h:raise ValueError('云端数据块校验失败')
                self.cache.put_blob(data)
        # A new checkout must have a level.dat before acquiring Minecraft's lock.
        world=Path(world);world.mkdir(parents=True,exist_ok=True)
        if (world/'level.dat').is_file():
            with closed_world(world):materialize(world,result['manifest'],self.cache)
        elif any(p.name not in ('.aetherloom','session.lock') for p in world.iterdir()):
            raise ValueError('目标目录非空且不是Minecraft世界，拒绝覆盖')
        else:
            with closed_world(world,require_level=False):materialize(world,result['manifest'],self.cache)
        return result['version']

    def candidate(self,room,world,parent):
        base='/api/rooms/'+room
        ticket=self.api(base+'/recoveries/start',{})['ticket']
        with closed_world(world):
            manifest=snapshot(world,self.cache)
            hashes=sorted({p[2] for e in manifest.values() for p in e['pieces']})
            for offset in range(0,len(hashes),4096):
                missing=self.api(base+'/missing',{'recovery':ticket,'hashes':hashes[offset:offset+4096]})['missing']
                for h in missing:
                    self.api(base+'/blobs/'+h,(self.cache.root/'blobs'/h[:2]/h).read_bytes(),method='PUT',headers={'X-Recovery':ticket})
            return self.api(base+'/recoveries',{'ticket':ticket,'parent':parent,'manifest':manifest})['candidate']
