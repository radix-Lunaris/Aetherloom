"""SQLite transaction authority. No Minecraft files are scanned by this service."""
import hashlib
import json
from pathlib import Path
import secrets
import sqlite3
import time
import uuid
import os
from contextlib import contextmanager
from .launcher import inside

class Conflict(ValueError):
    pass

class Authority:
    def __init__(self, root, clock=time.time, ttl=60):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.clock, self.ttl = clock, ttl
        self.db = self.root / "authority.db"
        with self.connect() as c:
            c.executescript("""
PRAGMA journal_mode=WAL;
CREATE TABLE IF NOT EXISTS rooms(id TEXT PRIMARY KEY, owner TEXT, epoch INTEGER DEFAULT 0,
 head TEXT, token TEXT, host TEXT, expires REAL DEFAULT 0, state TEXT DEFAULT 'idle');
CREATE TABLE IF NOT EXISTS managers(room TEXT, actor TEXT, PRIMARY KEY(room,actor));
CREATE TABLE IF NOT EXISTS versions(id TEXT PRIMARY KEY, room TEXT, parent TEXT, manifest TEXT,
 candidate INTEGER, actor TEXT);
""")

    @contextmanager
    def connect(self):
        c = sqlite3.connect(self.db, timeout=15)
        c.row_factory = sqlite3.Row
        try:
            with c:
                yield c
        finally:
            c.close()

    def create(self, owner):
        room = uuid.uuid4().hex
        with self.connect() as c:
            c.execute("INSERT INTO rooms(id,owner) VALUES (?,?)", (room, owner))
        return room

    def claim(self, room, actor, confirm_recovery=False):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            r = c.execute("SELECT * FROM rooms WHERE id=?", (room,)).fetchone()
            if not r:
                raise KeyError(room)
            if r["token"] and r["expires"] > self.clock():
                raise Conflict("World is occupied")
            if r["token"] and not confirm_recovery:
                raise Conflict("Previous host lost: explicit recovery confirmation required")
            token = secrets.token_urlsafe(32)
            epoch = r["epoch"] + 1
            c.execute("UPDATE rooms SET token=?,host=?,epoch=?,expires=?,state='preparing' WHERE id=?",
                      (token, actor, epoch, self.clock()+self.ttl, room))
            return dict(token=token, epoch=epoch, head=r["head"])

    def _lease(self, c, room, actor, token, epoch):
        r = c.execute("SELECT * FROM rooms WHERE id=?", (room,)).fetchone()
        if not r or r["host"] != actor or not secrets.compare_digest(r["token"] or "", token) or r["epoch"] != epoch or r["expires"] <= self.clock():
            raise Conflict("Expired or superseded host lease")
        return r

    def renew(self, room, actor, token, epoch):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            self._lease(c,room,actor,token,epoch)
            c.execute("UPDATE rooms SET expires=? WHERE id=?", (self.clock()+self.ttl,room))

    def put_blob(self, data):
        h = hashlib.sha256(data).hexdigest()
        dest = inside(self.root / "blobs", h[:2]+"/"+h)
        dest.parent.mkdir(parents=True,exist_ok=True)
        temp = dest.with_name(dest.name + '.' + uuid.uuid4().hex + '.tmp')
        with temp.open('xb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        try:
            if dest.exists():
                if hashlib.sha256(dest.read_bytes()).hexdigest() != h:
                    raise Conflict("Corrupt existing blob")
            else:
                os.replace(temp, dest)
        finally:
            temp.unlink(missing_ok=True)
        return h

    def _validate(self, manifest):
        for rel, entry in manifest.items():
            if not rel or rel in (".", "..") or "\\" in rel or ":" in rel or rel.startswith("/") or any(p in ('..', '.', '.aetherloom') or not p for p in rel.split('/')):
                raise ValueError("Unsafe world path")
            pos = 0
            for piece in entry["pieces"]:
                off, size, h = piece
                if off != pos or size <= 0 or len(h) != 64 or any(x not in "0123456789abcdef" for x in h):
                    raise ValueError("Invalid piece coverage")
                blob = inside(self.root / "blobs", h[:2]+"/"+h)
                if not blob.is_file() or blob.stat().st_size != size or hashlib.sha256(blob.read_bytes()).hexdigest() != h:
                    raise ValueError("Missing or corrupt blob")
                pos += size
            if pos != entry["size"]:
                raise ValueError("Incomplete file coverage")

    def commit(self, room, actor, token, epoch, parent, manifest):
        self._validate(manifest)
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            r = self._lease(c,room,actor,token,epoch)
            if parent != r["head"]:
                raise Conflict("Parent version changed")
            vid = uuid.uuid4().hex
            c.execute("INSERT INTO versions VALUES (?,?,?,?,0,?)",
                      (vid,room,parent,json.dumps(manifest),actor))
            c.execute("UPDATE rooms SET head=?,token=NULL,host=NULL,expires=0,state='idle' WHERE id=?",
                      (vid,room))
            return vid

    def candidate(self, room, actor, parent, manifest):
        self._validate(manifest)
        with self.connect() as c:
            if not c.execute("SELECT 1 FROM rooms WHERE id=?", (room,)).fetchone():
                raise KeyError(room)
            vid = uuid.uuid4().hex
            c.execute("INSERT INTO versions VALUES (?,?,?,?,1,?)",
                      (vid,room,parent,json.dumps(manifest),actor))
            return vid

    def restore(self, room, actor, candidate, expected_head):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            r = c.execute("SELECT * FROM rooms WHERE id=?", (room,)).fetchone()
            if not r:
                raise KeyError(room)
            manager = c.execute("SELECT 1 FROM managers WHERE room=? AND actor=?", (room,actor)).fetchone()
            if r["owner"] != actor and not manager:
                raise PermissionError("Instance management permission required")
            if r["token"] and r["expires"] > self.clock():
                raise Conflict("Stop current session before restoring")
            if r["head"] != expected_head:
                raise Conflict("Head changed after review")
            source = c.execute("SELECT * FROM versions WHERE id=? AND room=?", (candidate,room)).fetchone()
            if not source:
                raise KeyError(candidate)
            self._validate(json.loads(source["manifest"]))
            vid = uuid.uuid4().hex
            c.execute("INSERT INTO versions VALUES (?,?,?,?,0,?)",
                      (vid,room,r["head"],source["manifest"],actor))
            c.execute("UPDATE rooms SET head=?,epoch=epoch+1,token=NULL,host=NULL,expires=0,state='idle' WHERE id=?", (vid,room))
            return vid

