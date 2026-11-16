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
    if isinstance(value, dict): return value
    try:
        result = json.loads(value)
        if isinstance(result, dict) and set(result) == {'minecraft','loader','loader_version'}: return result
    except (ValueError, TypeError): pass
    match = re.fullmatch(r'(?:Minecraft\s+)?(\d+\.\d+(?:\.\d+)?)\s+[Ff]orge\s*(\d+\.\d+\.\d+)', value or '')
    if match: return {'minecraft':match[1], 'loader':'forge', 'loader_version':match[2]}
    return None


def validate(local, remote):
    expected = decode(remote)
    if expected is None:
        raise ValueError('房间缺少明确版本声明，请管理员在面板设置版本和加载器后再绑定')
    if local != expected:
        raise ValueError('游戏环境不匹配：本机 '+encode(local)+'；房间 '+encode(expected))
    if local != {'minecraft':'1.20.1','loader':'forge','loader_version':'47.4.22'}:
        raise ValueError('完整在线 Hop 当前仅支持 Minecraft 1.20.1 / Forge 47.4.22；其他版本可离线启动')
