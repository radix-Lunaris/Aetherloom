import hashlib
import json
import os
import platform
import re
import subprocess
from . import __version__
import uuid
import zipfile
from pathlib import Path

class LaunchError(ValueError):
    pass

def java_path(path):
    """Java17's Windows launcher can lose characters outside the ANSI codepage."""
    path=Path(path)
    if os.name != 'nt':
        return str(path)
    import ctypes
    if not path.exists():
        return str(Path(java_path(path.parent))/path.name)
    get_short=ctypes.windll.kernel32.GetShortPathNameW
    size=get_short(str(path),None,0)
    if size:
        buffer=ctypes.create_unicode_buffer(size)
        if get_short(str(path),buffer,size):
            return buffer.value
    try:
        str(path).encode('mbcs')
    except UnicodeEncodeError as exc:
        raise LaunchError('Java17 cannot represent this path on this Windows locale; select an ASCII path or enable NTFS short filenames') from exc
    return str(path)

def inside(root, rel):
    root = Path(root).resolve()
    target = (root / rel).resolve()
    if not target.is_relative_to(root):
        raise LaunchError("Path escapes selected directory")
    return target

def offline_uuid(name):
    return uuid.UUID(bytes=hashlib.md5(("OfflinePlayer:" + name).encode()).digest(), version=3).hex

def allowed(rules):
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "osx"}[platform.system()]
    result = not rules
    for r in rules:
        spec = r.get("os", {})
        if spec.get("name", system) != system:
            continue
        if "arch" in spec and not re.search(spec["arch"], platform.machine()):
            continue
        if "version" in spec and not re.search(spec["version"], platform.version()):
            continue
        if any(v for v in r.get("features", {}).values()):
            continue
        result = r["action"] == "allow"
    return result

def manifest(root, version, seen=None):
    seen = set() if seen is None else seen
    if version in seen:
        raise LaunchError("Version inheritance cycle")
    seen.add(version)
    child = json.loads(inside(root, f"versions/{version}/{version}.json").read_text(encoding="utf-8-sig"))
    if "inheritsFrom" not in child:
        child["_client"] = child.get("jar", version)
        return child
    parent = manifest(root, child["inheritsFrom"], seen)
    merged = dict(parent, **child)
    merged["_client"] = child.get("jar", parent["_client"])
    merged["libraries"] = parent.get("libraries", []) + child.get("libraries", [])
    merged["arguments"] = {k: parent.get("arguments", {}).get(k, []) + child.get("arguments", {}).get(k, []) for k in ("game", "jvm")}
    return merged

def coordinate(name):
    parts = name.split(":")
    if len(parts) not in (3, 4):
        raise LaunchError("Unsupported Maven coordinate")
    group, artifact, version = parts[:3]
    suffix = "-" + parts[3] if len(parts) == 4 else ""
    return f"{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}{suffix}.jar"

def game_uuid(name, custom_uuid=None):
    if custom_uuid is None:return offline_uuid(name)
    if not isinstance(custom_uuid,str):raise LaunchError('UUID 必须为文本')
    if not custom_uuid.strip():return offline_uuid(name)
    try:
        parsed=uuid.UUID(custom_uuid.strip())
        if parsed.int==0:raise ValueError()
        return parsed.hex
    except (ValueError,AttributeError):
        raise LaunchError('UUID 格式无效：请填写32位十六进制或带连字符的标准UUID；不能全部为零') from None


def prepare(root, version, java, name, run_dir=None, memory=2048, custom_uuid=None):
    root, java = Path(root).resolve(), Path(java).resolve()
    run = Path(run_dir or root).resolve()
    if not root.is_dir() or not run.is_dir():
        raise LaunchError("Game root and run directory must already exist")
    if not re.fullmatch("[A-Za-z0-9_]{1,16}", name):
        raise LaunchError("Invalid offline name")
    identity=game_uuid(name,custom_uuid)
    if not 512 <= memory <= 65536:
        raise LaunchError("Invalid memory limit")
    m = manifest(root, version)
    missing, cp, natives = [], [], []
    def require(p):
        if not p.is_file():
            missing.append(str(p))
        return p
    require(java)
    system = {"Windows": "windows", "Linux": "linux", "Darwin": "osx"}[platform.system()]
    libs = {}
    for lib in m.get("libraries", []):
        # Preserve classifier dependencies, replace inherited module versions.
        key = lib["name"].split(":")
        libs[(key[0], key[1], tuple(key[3:]))] = lib
    for lib in libs.values():
        if not allowed(lib.get("rules", [])):
            continue
        dl = lib.get("downloads", {})
        item = dl.get("artifact")
        if item or not lib.get("natives"):
            cp.append(str(require(inside(root / "libraries", item["path"] if item else coordinate(lib["name"])))))
        classifier = lib.get("natives", {}).get(system)
        if classifier:
            classifier = classifier.replace("${arch}", "64" if platform.machine().endswith("64") else "32")
            item = dl.get("classifiers", {}).get(classifier)
            if not item:
                raise LaunchError("Missing native descriptor")
            natives.append((require(inside(root / "libraries", item["path"])), lib.get("extract", {}).get("exclude", [])))
    client = m["_client"]
    primary_jar = require(inside(root, f"versions/{client}/{client}.jar"))
    cp.append(str(primary_jar))
    asset_id = m.get("assetIndex", {}).get("id", m.get("assets", "legacy"))
    index = require(inside(root, f"assets/indexes/{asset_id}.json"))
    if index.is_file():
        for obj in json.loads(index.read_text(encoding="utf-8")).get("objects", {}).values():
            h = obj["hash"]
            if not re.fullmatch("[0-9a-f]{40}", h):
                raise LaunchError("Invalid asset hash")
            require(root / "assets" / "objects" / h[:2] / h)
    if missing:
        raise LaunchError("Missing files:\n" + "\n".join(missing))
    from .runtime import inspect_java,required_java,compatibility
    required=required_java(m)
    java_info=inspect_java(java,refresh=True)
    reason=compatibility(java_info,required)
    if reason:raise LaunchError(reason+'；请使用稳定的推荐版本或自动选择')
    native_dir = inside(run, ".aetherloom/natives/" + uuid.uuid4().hex)
    native_dir.mkdir(parents=True,exist_ok=True)
    cp = [java_path(p) for p in cp]
    primary_java = java_path(primary_jar)
    libraries_java = java_path(root / 'libraries')
    variables = dict(auth_player_name=name, auth_uuid=identity, auth_access_token="0",
        clientid="", auth_xuid="", auth_session="0", xuid="",
        resolution_width="1280", resolution_height="720",
        user_type="legacy", user_properties="{}", version_name=version, version_type=m.get("type", "release"),
        game_directory=java_path(run), assets_root=java_path(root / "assets"), assets_index_name=asset_id,
        natives_directory=java_path(native_dir), launcher_name="Aetherloom", launcher_version=__version__,
        classpath=os.pathsep.join(cp), classpath_separator=os.pathsep,
        library_directory=libraries_java, libraries_directory=libraries_java,
        primary_jar=primary_java, primary_jar_name=Path(primary_java).name, file_separator=os.sep)
    def expand(s):
        def replacement(x):
            if x[1] not in variables:
                raise LaunchError("Unsupported variable: " + x[1])
            return variables[x[1]]
        return re.sub(r"\$\{([^}]+)\}", replacement, s)
    def args(items):
        out = []
        for x in items:
            if isinstance(x, str):
                out.append(expand(x))
            elif allowed(x.get("rules", [])):
                values = x["value"]
                out.extend(expand(v) for v in ([values] if isinstance(values, str) else values))
        return out
    jvm = args(m.get("arguments", {}).get("jvm", []))
    game = args(m.get("arguments", {}).get("game", []))
    if not game and "minecraftArguments" in m:
        import shlex
        game = args(shlex.split(m["minecraftArguments"]))
    if not any(x in ("-cp", "-classpath") for x in jvm):
        jvm += ["-cp", os.pathsep.join(cp)]
    if not any(x.startswith("-Djava.library.path=") for x in jvm):
        jvm += ["-Djava.library.path=" + java_path(native_dir)]
    for archive, excludes in natives:
        with zipfile.ZipFile(archive) as z:
            for entry in z.infolist():
                if entry.is_dir() or any(entry.filename.startswith(x) for x in excludes):
                    continue
                target = inside(native_dir, entry.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(entry))
    return [str(java), f"-Xmx{memory}M", *jvm, m["mainClass"], *game], run

def launch(*args, quick_play=None, bridge_file=None, agent_jar=None, agent_config=None, before_start=None, managed=False, **kwargs):
    command, run = prepare(*args, **kwargs)
    environment=None
    if agent_jar or agent_config:
        if not agent_jar or not agent_config or not Path(agent_jar).is_file() or not Path(agent_config).is_file():raise LaunchError('Incomplete agent resources')
        if bridge_file:raise LaunchError('Agent and Bridge cannot control the same game')
        command.insert(1,'-javaagent:'+java_path(Path(agent_jar).resolve())+'=managed')
        environment=dict(os.environ,AETHERLOOM_AGENT_CONFIG=str(Path(agent_config).resolve()))
        environment.pop('AETHERLOOM_BRIDGE_FILE',None)
    if quick_play:
        mode,value=quick_play
        if mode not in ('Singleplayer','Multiplayer'):raise LaunchError('Unsupported quick play mode')
        command.extend(['--quickPlayPath',java_path(run/'.aetherloom/quickplay.json'),'--quickPlay'+mode,value])
    if bridge_file:
        environment=dict(os.environ,AETHERLOOM_BRIDGE_FILE=str(bridge_file))
    if bridge_file or managed:
        command.insert(1,'-Dsharedplayerdata.disable=true')
    logs = inside(run, '.aetherloom/logs')
    logs.mkdir(parents=True, exist_ok=True)
    if before_start:before_start()
    with (logs / ('game-' + uuid.uuid4().hex + '.log')).open('wb') as output:
        from .runtime import hidden_process
        from .diagnostics import event
        event('game.spawn', mode='online' if managed else 'offline', run=run, argc=len(command))
        return subprocess.Popen(command, cwd=run, stdout=output, stderr=subprocess.STDOUT,env=environment,**hidden_process())

