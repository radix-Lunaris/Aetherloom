"""Version identity, independent of a launcher's friendly profile name."""
import json
from pathlib import Path
import re
from .launcher import manifest


def describe(root, version):
    data = manifest(Path(root), version)
    args = data.get('arguments', {}).get('game', [])
    strings = [a for a in args if isinstance(a, str)]
    def flag(name):
        return strings[strings.index(name)+1] if name in strings and strings.index(name)+1 < len(strings) else None
    minecraft = flag('--fml.mcVersion') or data.get('clientVersion') or data.get('_client')
    loader, loader_version = 'vanilla', ''
    for lib in data.get('libraries', []):
        parts = lib.get('name', '').split(':')
        if len(parts) < 3: continue
        if parts[:2] == ['net.minecraftforge','forge']:
            loader = 'forge'
            minecraft, _, loader_version = parts[2].partition('-')
        elif parts[:2] == ['net.fabricmc','fabric-loader']:
            loader, loader_version = 'fabric', parts[2]
        elif parts[:2] == ['net.neoforged','neoforge']:
            loader, loader_version = 'neoforge', parts[2]
    if flag('--fml.forgeVersion'):
        loader, loader_version = 'forge', flag('--fml.forgeVersion')
    if not re.fullmatch(r'\d+\.\d+(?:\.\d+)?', str(minecraft)):
        # Merged profiles can have a renamed client jar; use explicit version metadata.
        minecraft = data.get('patches', [{}])[0].get('version', minecraft) if data.get('patches') else minecraft
    return {'minecraft': str(minecraft), 'loader': loader, 'loader_version': loader_version}


def encode(environment):
    return json.dumps(environment, separators=(',', ':'), sort_keys=True)


def decode(value):
    try:
        result = value if isinstance(value,dict) else json.loads(value)
        if isinstance(result,dict) and set(result) in ({'minecraft','loader','loader_version'},{'minecraft','loader','loader_version','authentication'}):
            if result.get('authentication','offline') not in ('offline','littleskin'):return None
            return {k:result[k] for k in ('minecraft','loader','loader_version')}
    except (ValueError, TypeError): pass
    match = re.fullmatch(r'(?:Minecraft\s+)?(\d+\.\d+(?:\.\d+)?)\s+[Ff]orge\s*(\d+\.\d+\.\d+)', value or '')
    if match: return {'minecraft':match[1], 'loader':'forge', 'loader_version':match[2]}
    return None


def authentication(value):
    if isinstance(value,str):
        try:value=json.loads(value)
        except (TypeError,ValueError):return 'offline'
    result=value.get('authentication','offline') if isinstance(value,dict) else 'offline'
    if result not in ('offline','littleskin'):raise ValueError('未知房间游戏认证模式')
    return result


def validate_account(binding,remote):
    local='littleskin' if binding.get('game_account') else 'offline'
    if local!=authentication(remote):raise ValueError('游戏账号类型与房间不一致；LittleSkin房间需选择LittleSkin角色，离线房间请使用离线身份')


def loader_family(environment):
    version=environment['loader_version']
    if environment['loader']=='forge':return str(version).split('.')[0]
    return version


def validate(local, remote,backend='bridge'):
    expected = decode(remote)
    if expected is None:
        raise ValueError('房间缺少明确版本声明，请管理员在面板设置版本和加载器后再绑定')
    if any(local[k]!=expected[k] for k in ('minecraft','loader')) or loader_family(local)!=loader_family(expected):
        raise ValueError('游戏环境不匹配：本机 '+encode(local)+'；房间 '+encode(expected))
    family=(local['minecraft'],local['loader'],loader_family(local))
    if family==('1.20.1','forge','47'):return
    if backend=='agent' and family==('1.21.1','forge','52'):return
    raise ValueError('此环境尚无可用的自动Hop适配。Agent候选支持1.20.1/Forge47与1.21.1/Forge52；其他版本可个人启动，不能伪装成已适配')
