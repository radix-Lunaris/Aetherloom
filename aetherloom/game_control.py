"""Explicit selection of experimental game control; stable Bridge is default."""
import json
from pathlib import Path
import uuid

AGENT_ENVIRONMENT={'minecraft':'1.20.1','loader':'forge','loader_version':'47.4.22'}
CAPABILITIES=('world','lan','join','identity','saved','exit')

def agent_config(control):
    data=json.loads(control.config.read_text(encoding='utf-8'))
    data['adapter']='1.20.1-forge';data['identity']=str(uuid.UUID(data['identity']))
    # Properties.load uses ISO-8859-1 with Java unicode escapes.
    def escape(value):
        value=str(value).replace('\\','\\\\').replace('\n','\\n').replace('\r','\\r').replace('\t','\\t').replace('=','\\=').replace(':','\\:').replace(' ','\\ ')
        return ''.join(c if ord(c)<128 else ''.join('\\u%04x'%n for n in ([ord(c)] if ord(c)<=65535 else [0xd800+((ord(c)-65536)>>10),0xdc00+((ord(c)-65536)&1023)])) for c in value)
    path=control.config.with_suffix('.properties')
    path.write_text('\n'.join(key+'='+escape(str(value).lower() if isinstance(value,bool) else value) for key,value in data.items())+'\n',encoding='ascii')
    return path

def select_backend(binding):
    value=binding.get('control_backend','bridge')
    if value not in ('bridge','agent'):raise ValueError('未知游戏控制实现')
    return value
