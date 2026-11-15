import hashlib
import json
import os
import platform
import re
import subprocess
import uuid
import zipfile
from pathlib import Path

class LaunchError(ValueError):
    pass

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

def prepare(root, version, java, name, run_dir=None, memory=2048):
    root, java = Path(root).resolve(), Path(java).resolve()
    run = Path(run_dir or root).resolve()
    if not re.fullmatch("[A-Za-z0-9_]{1,16}", name):
        raise LaunchError("Invalid offline name")
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
    cp.append(str(require(inside(root, f"versions/{client}/{client}.jar"))))
    asset_id = m.get("assetIndex", {}).get("id", m.get("assets", "legacy"))
    index = require(inside(root, f"assets/indexes/{asset_id}.json"))
    if index.is_file():
        for obj in json.loads(index.read_text()).get("objects", {}).values():
            h = obj["hash"]
            if not re.fullmatch("[0-9a-f]{40}", h):
                raise LaunchError("Invalid asset hash")
            require(root / "assets" / "objects" / h[:2] / h)
    if missing:
        raise LaunchError("Missing files:\n" + "\n".join(missing))
    probe = subprocess.run([str(java), "-version"], capture_output=True, text=True, timeout=15)
    match = re.search(r'version "(\d+)(?:\.(\d+))?', probe.stderr + probe.stdout)
    major = int(match[2]) if match and match[1] == "1" else int(match[1]) if match else 0
    required = m.get("javaVersion", {}).get("majorVersion", 17)
    if probe.returncode or major < required:
        raise LaunchError(f"Java {required}+ required")
    native_dir = inside(run, ".aetherloom/natives/" + uuid.uuid4().hex)
    variables = dict(auth_player_name=name, auth_uuid=offline_uuid(name), auth_access_token="0",
        user_type="legacy", user_properties="{}", version_name=version, version_type=m.get("type", "release"),
        game_directory=str(run), assets_root=str(root / "assets"), assets_index_name=asset_id,
        natives_directory=str(native_dir), launcher_name="Aetherloom", launcher_version="0.1.0",
        classpath=os.pathsep.join(cp), classpath_separator=os.pathsep, library_directory=str(root / "libraries"))
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
        jvm += ["-Djava.library.path=" + str(native_dir)]
    for archive, excludes in natives:
        with zipfile.ZipFile(archive) as z:
            for entry in z.infolist():
                if entry.is_dir() or any(entry.filename.startswith(x) for x in excludes):
                    continue
                target = inside(native_dir, entry.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(z.read(entry))
    return [str(java), f"-Xmx{memory}M", *jvm, m["mainClass"], *game], run

def launch(*args, **kwargs):
    command, run = prepare(*args, **kwargs)
    return subprocess.Popen(command, cwd=run)

