"""Verified HTTP range segments, with a streaming fallback when unsupported."""
import re,threading
from .parallel import transfer

def download(url,path,size,open_request,cancel,progress,workers=4):
    def validate(response,start,end):
        expected=f'bytes {start}-{end}/{size}'
        if response.status!=206 or response.headers.get('Content-Range')!=expected:
            raise ValueError('Java分段下载响应范围不匹配')
        length=response.headers.get('Content-Length')
        if length is not None and int(length)!=end-start+1:raise ValueError('Java分段下载长度不匹配')
    with open_request(url,headers={'Range':'bytes=0-0'}) as response:
        if response.status==200:return False
        validate(response,0,0)
        if len(response.read(2))!=1:raise ValueError('Java下载范围探测失败')
    count=max(1,min(workers,8,size));stride=(size+count-1)//count
    segments=[(start,min(size-1,start+stride-1)) for start in range(0,size,stride)]
    with path.open('xb') as output:output.truncate(size)
    stopped=threading.Event();lock=threading.Lock();received=0
    def segment(bounds):
        nonlocal received
        start,end=bounds;remaining=end-start+1
        try:
            if cancel.is_set() or stopped.is_set():raise ValueError('Java下载已取消')
            with open_request(url,headers={'Range':f'bytes={start}-{end}'}) as response,path.open('r+b') as output:
                validate(response,start,end);output.seek(start)
                while remaining:
                    if cancel.is_set() or stopped.is_set():raise ValueError('Java下载已取消')
                    data=response.read(min(256*1024,remaining))
                    if not data:raise ValueError('Java分段下载提前结束')
                    output.write(data);remaining-=len(data)
                    with lock:received+=len(data);progress(received,size)
            return end-start+1
        except BaseException:stopped.set();raise
    for _ in transfer(segments,segment,count):pass
    if received!=size:raise ValueError('Java分段下载不完整')
    return True
