"""Bounded, read-only discovery in the selected instance's saves directory.

MCsaves-sync scanner/level_info informed the layout and metadata fields.
This reader is original, bounded code; never walks region files or disks.
"""
import gzip,io,struct,zlib
from pathlib import Path

MAX_LEVEL=16*1024*1024

class Reader:
    def __init__(self,data):self.data=data;self.pos=0;self.nodes=0
    def take(self,n):
        if n<0 or self.pos+n>len(self.data):raise ValueError('NBT数据不完整')
        value=self.data[self.pos:self.pos+n];self.pos+=n;return value
    def number(self,fmt):return struct.unpack('>'+fmt,self.take(struct.calcsize('>'+fmt)))[0]
    def text(self):
        data=self.take(self.number('H')).replace(b'\xc0\x80',b'\0')
        return data.decode('utf-8','surrogatepass').encode('utf-16-le','surrogatepass').decode('utf-16-le','replace')
    def payload(self,tag,depth=0):
        self.nodes+=1
        if depth>64 or self.nodes>100000:raise ValueError('NBT结构过大或过深')
        if tag in (1,2,3,4,5,6):return self.number({1:'b',2:'h',3:'i',4:'q',5:'f',6:'d'}[tag])
        if tag==8:return self.text()
        if tag in (7,11,12):
            count=self.number('i');self.take(count*{7:1,11:4,12:8}[tag]);return None
        if tag==9:
            subtype=self.number('B');count=self.number('i')
            if count<0 or count>100000:raise ValueError('NBT列表长度无效')
            for _ in range(count):self.payload(subtype,depth+1)
            return None
        if tag==10:
            result={}
            while True:
                subtype=self.number('B')
                if subtype==0:return result
                key=self.text();result[key]=self.payload(subtype,depth+1)
        raise ValueError('未知NBT标签')

def level_info(path):
    path=Path(path)
    if path.is_symlink() or path.stat().st_size>4*1024*1024:raise ValueError('level.dat过大或是链接')
    raw=path.read_bytes()
    if raw.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=io.BytesIO(raw)) as source:data=source.read(MAX_LEVEL+1)
    elif raw[:2] in (b'x\x01',b'x\x9c',b'x\xda'):
        decoder=zlib.decompressobj();data=decoder.decompress(raw,MAX_LEVEL+1)
        if len(data)<=MAX_LEVEL and not decoder.eof:raise ValueError('level.dat压缩数据不完整')
    else:data=raw
    if len(data)>MAX_LEVEL:raise ValueError('level.dat解压后过大')
    reader=Reader(data)
    if reader.number('B')!=10:raise ValueError('世界元数据不是NBT复合根')
    reader.text();root=reader.payload(10);value=root.get('Data',root)
    if not isinstance(value,dict):raise ValueError('世界Data字段无效')
    version=value.get('Version',{})
    if type(value.get('LastPlayed',0))!=int:raise ValueError('LastPlayed不是整数')
    return {'world_name':str(value.get('LevelName','')),'game_version':str(version.get('Name','')) if isinstance(version,dict) else str(version),
            'gametype':{0:'生存',1:'创造',2:'冒险',3:'旁观'}.get(value.get('GameType'),'未知'),
            'difficulty':{0:'和平',1:'简单',2:'普通',3:'困难'}.get(value.get('Difficulty'),'未知'),
            'hardcore':bool(value.get('hardcore',False)),'last_played':int(value.get('LastPlayed',0))/1000}

def discover(run):
    run=Path(run).resolve();saves=run/'saves';found=[]
    if not saves.is_dir() or saves.is_symlink() or not saves.resolve().is_relative_to(run):return []
    for path in sorted(saves.iterdir())[:1000]:
        if path.is_symlink() or not path.is_dir() or not path.resolve().is_relative_to(saves.resolve()):continue
        if not (path/'level.dat').is_file() and not (path/'level.dat_old').is_file():continue
        record={'path':str(path.resolve()),'folder':path.name,'world_name':path.name,'game_version':'','error':None}
        try:record.update(level_info(path/'level.dat'))
        except (OSError,ValueError,TypeError,struct.error,UnicodeError,zlib.error) as error:record['error']='元数据无法读取：'+str(error)
        found.append(record)
    return sorted(found,key=lambda row:row.get('last_played',0),reverse=True)
