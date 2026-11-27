"""Choose managed game control from the installed instance."""
import json
from pathlib import Path
import uuid
import zipfile
import zlib

CAPABILITIES=('world','lan','join','identity','saved','exit')
AGENT_PREMAIN='online.superyk7hero.aetherloom.agent.Agent'


def check_agent_package(path):
    """Validate the bundled Agent before a game or a cloud lease is started."""
    if not path.is_file():
        raise ValueError('交付包缺少游戏控制 Agent，请重新下载 Aetherloom')
    try:
        with zipfile.ZipFile(path) as archive:
            if sum(entry.file_size for entry in archive.infolist()) > 16 * 1024 * 1024:
                raise ValueError('Unexpected Agent package size')
            with archive.open('META-INF/MANIFEST.MF') as manifest:
                main_section=manifest.read().decode('ascii').replace('\r\n','\n').split('\n\n',1)[0]
            entry=AGENT_PREMAIN.replace('.','/')+'.class'
            if 'Premain-Class: '+AGENT_PREMAIN not in main_section.splitlines():
                raise ValueError('Wrong Agent entry point')
            with archive.open(entry) as bytecode:
                header=bytecode.read(8)
            if len(header)!=8 or header[:4]!=b'\xca\xfe\xba\xbe' or int.from_bytes(header[6:8],'big')!=52:
                raise ValueError('Invalid Agent entry class')
            if archive.testzip() is not None:
                raise ValueError('Agent CRC mismatch')
    except (OSError,ValueError,KeyError,RuntimeError,zipfile.BadZipFile,zlib.error) as error:
        raise ValueError('交付包中的 Agent 已损坏或版本不匹配，请重新下载 Aetherloom') from error

def agent_config(control, *, open_world=False, host_presets=None):
    data=json.loads(control.config.read_text(encoding='utf-8'))
    if open_world:
        data['open_world'] = True
    if host_presets and not (data.get("inspect") or data.get("join")):
        pvp={"允许":"true","禁止":"false"}.get(host_presets.get("pvp"))
        mode={"生存":"survival","创造":"creative","冒险":"adventure","旁观":"spectator"}.get(host_presets.get("mode"))
        if pvp is not None:
            data["host_pvp"]=pvp
        if mode is not None:
            data["host_mode"]=mode
        data["host_cheats"]=bool(host_presets.get("cheats"))
        data["host_official_auth"]=bool(host_presets.get("official_auth"))
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
    from .vanilla_control import CALAMUS_VANILLA_RELEASES, LEGACY_LAN_RELEASES, supports_vanilla_control
    environment = describe(binding['root'], binding['version'])
    if value != 'agent' and (
        environment['minecraft'], environment['loader'], loader_family(environment)
    ) == ('1.20.1', 'forge', '47'):
        return 'bridge'
    if environment['loader'] == 'vanilla':
        if not supports_vanilla_control(environment['minecraft']):
            raise ValueError('该原版尚无对应联机控制，仍可离线启动')
    elif environment['loader'] not in ('forge', 'neoforge', 'fabric', 'quilt'):
        raise ValueError('当前加载器没有联机控制实现')
    elif environment['minecraft'] in CALAMUS_VANILLA_RELEASES:
        raise ValueError('此补丁当前只有原版的精确联机控制，模组加载器仍可离线启动')
    elif environment['minecraft'] in LEGACY_LAN_RELEASES:
        if environment['loader'] != 'fabric':
            raise ValueError('此旧版联机需要原版或 Legacy Fabric 实例')
        from .launcher import manifest
        expected = 'net.legacyfabric:intermediary:'+environment['minecraft']
        libraries = manifest(Path(binding['root']), binding['version']).get('libraries', [])
        if not any(lib.get('name') == expected for lib in libraries):
            raise ValueError('此 Legacy Fabric 实例缺少对应的 Intermediary 元数据')
    return 'agent'
