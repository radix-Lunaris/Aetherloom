"""Choose managed game control from the installed instance."""
import json
from pathlib import Path
import uuid

CAPABILITIES=('world','lan','join','identity','saved','exit')

def agent_config(control, *, open_world=False):
    data=json.loads(control.config.read_text(encoding='utf-8'))
    if open_world:
        data['open_world'] = True
    data.setdefault('adapter','1.20.1-forge');data['identity']=str(uuid.UUID(data['identity']))
    # Properties.load uses ISO-8859-1 with Java unicode escapes.
    def escape(value):
        value=str(value).replace('\\','\\\\').replace('\n','\\n').replace('\r','\\r').replace('\t','\\t').replace('=','\\=').replace(':','\\:').replace(' ','\\ ')
        return ''.join(c if ord(c)<128 else ''.join('\\u%04x'%n for n in ([ord(c)] if ord(c)<=65535 else [0xd800+((ord(c)-65536)>>10),0xdc00+((ord(c)-65536)&1023)])) for c in value)
    path=control.config.with_suffix('.properties')
    path.write_text('\n'.join(key+'='+escape(str(value).lower() if isinstance(value,bool) else value) for key,value in data.items())+'\n',encoding='ascii')
    return path

def select_backend(binding):
    value = binding.get('control_backend', 'auto')
    if value not in ('auto', 'bridge', 'agent'):
        raise ValueError('未知游戏控制实现')
    if 'root' not in binding or 'version' not in binding:
        return 'bridge' if value == 'auto' else value
    from .environment import describe, loader_family
    environment = describe(binding['root'], binding['version'])
    if value != 'agent' and (
        environment['minecraft'], environment['loader'], loader_family(environment)
    ) == ('1.20.1', 'forge', '47'):
        return 'bridge'
    if environment['loader'] not in ('forge', 'neoforge', 'fabric', 'quilt'):
        raise ValueError('该实例可以离线启动，共享联机需要 Forge、NeoForge、Fabric 或 Quilt')
    return 'agent'
