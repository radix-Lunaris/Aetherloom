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
from .transfer import TransferProgress


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
    def __init__(self,api,cache,progress=None,on_progress=None):
        self.api=api;self.cache=Authority(Path(cache));self.progress=progress or (lambda text:None);self.on_progress=on_progress

    def upload(self,room,world,lease,parent):
        return self._upload(room,world,parent,lease=lease)

    def _upload(self,room,world,parent,lease=None,recovery=None):
        operation='recovery' if recovery else 'upload'
        report=TransferProgress(operation,self.on_progress)
        report.emit('hash',message='正在计算存档 SHA-256')
        with closed_world(world):
            manifest=snapshot(world,self.cache,progress=lambda stage,done,total:report.emit(stage,done,total,0,35,message='计算存档 SHA-256'))
            sizes={piece[2]:piece[1] for entry in manifest.values() for piece in entry['pieces']}
            hashes=sorted(sizes);missing=[];base='/api/rooms/'+room
            for offset in range(0,len(hashes),4096):
                scope={'recovery':recovery} if recovery else {'lease':lease}
                batch=hashes[offset:offset+4096]
                result=self.api(base+'/missing',dict(scope,hashes=batch))['missing']
                if not set(result).issubset(batch):raise ValueError('服务器缺失块响应无效')
                missing.extend(result)
                report.emit('compare',min(offset+4096,len(hashes)),len(hashes),35,40,'blocks','比对云端缺失块')
            total=sum(sizes[h] for h in missing);sent=0
            report.emit('transfer',0,total,40,95,message='仅上传云端缺失的数据块')
            for h in missing:
                data=(self.cache.root/'blobs'/h[:2]/h).read_bytes()
                headers={'X-Recovery':recovery} if recovery else {'X-Lease':lease['token'],'X-Epoch':str(lease['epoch'])}
                self.api(base+'/blobs/'+h,data,method='PUT',headers=headers)
                sent+=len(data);report.emit('transfer',sent,total,40,95,message='增量上传')
            report.emit('commit',1,1,95,99,'steps','正在验证并提交云端版本')
            if recovery:version=self.api(base+'/recoveries',dict(ticket=recovery,parent=parent,manifest=manifest))['candidate']
            else:version=self.api(base+'/commit',dict(lease,parent=parent,manifest=manifest))['version']
            report.finish('恢复候选上传完成' if recovery else '权威存档提交成功')
            return version

    def download(self,room,world):
        report=TransferProgress('download',self.on_progress)
        report.emit('metadata',message='正在获取权威版本清单')
        result=self.api('/api/rooms/'+room+'/head')
        if result['version'] is None:raise ValueError('此房间尚未发布共同存档，请由所有者先发布')
        self.cache._validate(result['manifest'],check_blobs=False)
        sizes={p[2]:p[1] for e in result['manifest'].values() for p in e['pieces']}
        total=sum(sizes.values());checked=0;missing=[]
        for h in sorted(sizes):
            path=self.cache.root/'blobs'/h[:2]/h
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=h:missing.append(h)
            checked+=sizes[h];report.emit('verify',checked,total,5,20,message='校验本地数据块缓存')
        transfer_total=sum(sizes[h] for h in missing);received=0
        report.emit('transfer',0,transfer_total,20,70,message='仅下载本地缺失的数据块')
        for h in missing:
            data=self.api('/api/rooms/'+room+'/blobs/'+h,raw=True)
            if hashlib.sha256(data).hexdigest()!=h:raise ValueError('云端数据块校验失败')
            self.cache.put_blob(data);received+=len(data)
            report.emit('transfer',received,transfer_total,20,70,message='增量下载')
        def progress(stage,done,total):
            report.emit(stage,done,total,70 if stage=='assemble' else 90,90 if stage=='assemble' else 99,
                        'bytes' if stage=='assemble' else 'files','重建并验证文件' if stage=='assemble' else '安全替换世界文件')
        world=Path(world);world.mkdir(parents=True,exist_ok=True)
        if (world/'level.dat').is_file():
            with closed_world(world):materialize(world,result['manifest'],self.cache,progress=progress)
        elif any(p.name not in ('.aetherloom','session.lock') for p in world.iterdir()):
            raise ValueError('目标目录非空且不是Minecraft世界，拒绝覆盖')
        else:
            with closed_world(world,require_level=False):materialize(world,result['manifest'],self.cache,progress=progress)
        report.finish('权威存档校验与下载完成')
        return result['version']

    def candidate(self,room,world,parent):
        ticket=self.api('/api/rooms/'+room+'/recoveries/start',{})['ticket']
        return self._upload(room,world,parent,recovery=ticket)
