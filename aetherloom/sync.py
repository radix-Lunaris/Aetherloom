"""Explicit, stopped-world SHA-256 snapshots. No watcher or scheduled work."""
import hashlib
import os
from pathlib import Path
import uuid
from .launcher import inside

def snapshot(world, store):
    world = Path(world).resolve()
    manifest = {}
    for path in sorted(world.rglob("*")):
        if path.is_symlink():
            raise ValueError("World symlinks are unsupported")
        if not path.is_file() or path.name == "session.lock":
            continue
        rel = path.relative_to(world).as_posix()
        if ".aetherloom" in path.relative_to(world).parts:
            continue
        before = path.stat()
        pieces = []
        full = hashlib.sha256()
        size = 256*1024 if path.suffix == ".mca" else 4*1024*1024
        offset = 0
        with path.open("rb") as f:
            while data := f.read(size):
                h = store.put_blob(data)
                pieces.append([offset,len(data),h])
                offset += len(data)
                full.update(data)
        after = path.stat()
        if (before.st_size,before.st_mtime_ns) != (after.st_size,after.st_mtime_ns):
            raise ValueError("World changed during snapshot")
        manifest[rel] = dict(size=offset,hash=full.hexdigest(),pieces=pieces)
    return manifest

def materialize(world, manifest, store):
    """Stage all files before replacing; journal persists until all replacements finish."""
    store._validate(manifest)
    world = Path(world).resolve()
    world.mkdir(parents=True,exist_ok=True)
    staging = inside(world, ".aetherloom/staging/" + uuid.uuid4().hex)
    staged = []
    for rel, entry in manifest.items():
        target = inside(world,rel)
        temp = inside(staging,rel)
        temp.parent.mkdir(parents=True,exist_ok=True)
        full = hashlib.sha256()
        with temp.open("xb") as f:
            for _,_,h in entry["pieces"]:
                data = inside(store.root/"blobs",h[:2]+"/"+h).read_bytes()
                f.write(data)
                full.update(data)
            f.flush()
            os.fsync(f.fileno())
        if full.hexdigest() != entry["hash"]:
            raise ValueError("File hash mismatch")
        staged.append((temp,target))
    journal = inside(world, ".aetherloom/incomplete")
    journal.parent.mkdir(parents=True,exist_ok=True)
    journal.write_text(str(staging),encoding="utf-8")
    for temp,target in staged:
        if target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest() == hashlib.sha256(temp.read_bytes()).hexdigest():
            temp.unlink()
            continue
        target.parent.mkdir(parents=True,exist_ok=True)
        os.replace(temp,target)
    # Deletion policy deliberately not enabled until backups and world-lock
    # integration exist. Callers must not advertise this as exact cloud checkout.
    journal.unlink()

