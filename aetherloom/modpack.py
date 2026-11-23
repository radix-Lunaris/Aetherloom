"""Identify enabled mods from the chosen instance without executing their code."""
import hashlib
import json
import tomllib
import zipfile
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=4096)
def inspect_mod(path, size, modified):
    with zipfile.ZipFile(path) as jar:
        names=set(jar.namelist())
        def read(name):
            if jar.getinfo(name).file_size>1024*1024:
                raise ValueError(f"模组元数据过大：{path.name}")
            return jar.read(name)
        rows=[]
        if "fabric.mod.json" in names:
            meta=json.loads(read("fabric.mod.json"))
            if meta.get("environment")=="client":
                return ()
            rows.append((meta["id"],meta.get("version","")))
        elif "quilt.mod.json" in names:
            meta=json.loads(read("quilt.mod.json"))["quilt_loader"]
            rows.append((meta["id"],meta.get("version","")))
        else:
            for filename in ("META-INF/neoforge.mods.toml","META-INF/mods.toml"):
                if filename in names:
                    meta=tomllib.loads(read(filename).decode("utf-8-sig"))
                    rows.extend((row["modId"],row.get("version","")) for row in meta["mods"])
                    break
        if not rows:
            rows.append((path.name,""))
    with path.open("rb") as stream:
        digest=hashlib.file_digest(stream,"sha256").hexdigest()
    return tuple((str(key),str(version),digest) for key,version in rows)


def required_mods(run):
    folder=Path(run)/"mods"
    result={}
    if folder.is_symlink():
        raise ValueError("模组目录是链接，无法确认整合包")
    for path in sorted(folder.glob("*.jar")):
        if path.is_symlink():
            raise ValueError("模组文件是链接："+path.name)
        stat=path.stat()
        for key,version,digest in inspect_mod(path,stat.st_size,stat.st_mtime_ns):
            if key in result:
                raise ValueError("模组 ID 重复："+key)
            result[key]=[version,digest]
    return result


def verify_pack(run,local,environment,required):
    if required is None:
        return
    expected=json.loads(environment)
    if expected["loader"]!=local["loader"]:
        raise ValueError("房间需要加载器 "+expected["loader"])
    installed=required_mods(run)
    mismatches=[key for key,value in required.items() if installed.get(key)!=value]
    if mismatches:
        raise ValueError("缺失或内容不同的房间模组："+"、".join(mismatches))
