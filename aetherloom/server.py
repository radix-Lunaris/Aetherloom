"""Authenticated control API. Run one worker; state is persisted in SQLite."""
import argparse
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import time
from fastapi import FastAPI, HTTPException, Header, Request, Depends
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .store import Authority, Conflict

class Login(BaseModel):
    username: str
    password: str

class UserInput(Login):
    role: str = "player"

class Claim(BaseModel):
    confirm_recovery: bool = False

class Lease(BaseModel):
    token: str
    epoch: int

class Commit(Lease):
    parent: str | None = None
    manifest: dict

def create_app(data_dir=None):
    store = Authority(Path(data_dir or os.environ.get("AETHERLOOM_DATA", "./data")))
    with store.connect() as c:
        c.executescript("""
CREATE TABLE IF NOT EXISTS accounts(name TEXT PRIMARY KEY, salt TEXT, digest TEXT, role TEXT);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, actor TEXT, expires REAL);
""")
    app = FastAPI(title="Aetherloom", version="0.1.0")
    app.state.store = store

    def authenticate(authorization: str = Header(default="")):
        token = authorization.removeprefix("Bearer ")
        hashed = hashlib.sha256(token.encode()).hexdigest()
        with store.connect() as c:
            row = c.execute("SELECT a.name,a.role FROM sessions s JOIN accounts a ON a.name=s.actor WHERE s.token=? AND s.expires>?",
                            (hashed,time.time())).fetchone()
        if not row:
            raise HTTPException(401,"请先登录 Aetherloom")
        return dict(row)

    def manager(room, user):
        with store.connect() as c:
            r=c.execute("SELECT * FROM rooms WHERE id=?",(room,)).fetchone()
            m=c.execute("SELECT 1 FROM managers WHERE room=? AND actor=?",(room,user["name"])).fetchone()
        if not r:
            raise HTTPException(404,"实例不存在")
        if user["role"] != "root" and r["owner"] != user["name"] and not m:
            raise HTTPException(403,"需要实例管理权限")

    @app.exception_handler(Conflict)
    async def conflict(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409,content={"detail":str(exc)})

    @app.exception_handler(ValueError)
    async def invalid(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400,content={"detail":str(exc)})

    @app.exception_handler(sqlite3.IntegrityError)
    async def duplicate(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409,content={"detail":"记录已存在"})

    @app.get("/health")
    def health():
        return {"status":"ok","version":"0.1.0"}

    @app.post("/api/login")
    def login(body:Login):
        with store.connect() as c:
            row=c.execute("SELECT * FROM accounts WHERE name=?",(body.username,)).fetchone()
        # Compute a hash even for missing usernames.
        digest=hashlib.pbkdf2_hmac("sha256",body.password.encode(),
            bytes.fromhex(row["salt"]) if row else b"0"*16,200000).hex()
        if not row or not hmac.compare_digest(digest,row["digest"]):
            raise HTTPException(401,"账号或密码错误")
        token=secrets.token_urlsafe(32)
        with store.connect() as c:
            c.execute("INSERT INTO sessions VALUES (?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(),row["name"],time.time()+43200))
        return {"token":token,"username":row["name"],"role":row["role"]}

    @app.post("/api/logout")
    def logout(authorization: str=Header(default=""),user=Depends(authenticate)):
        with store.connect() as c:
            c.execute("DELETE FROM sessions WHERE token=?",
                (hashlib.sha256(authorization.removeprefix("Bearer ").encode()).hexdigest(),))
        return {"ok":True}

    @app.get("/api/status")
    def status(user=Depends(authenticate)):
        if user["role"] not in ("root","admin"):
            raise HTTPException(403,"需要服务器管理权限")
        disk=shutil.disk_usage(store.root)
        with store.connect() as c:
            rooms=c.execute("SELECT COUNT(*) FROM rooms").fetchone()[0]
            accounts=c.execute("SELECT COUNT(*) FROM accounts").fetchone()[0]
        return {"disk_total":disk.total,"disk_free":disk.free,"rooms":rooms,"accounts":accounts}

    @app.post("/api/users")
    def users(body:UserInput,user=Depends(authenticate)):
        if user["role"] not in ("root","admin") or body.role not in ("admin","player") or (body.role=="admin" and user["role"]!="root"):
            raise HTTPException(403,"无权创建该角色")
        add_user(store,body.username,body.password,body.role)
        return {"ok":True}

    @app.get("/api/rooms")
    def rooms(user=Depends(authenticate)):
        with store.connect() as c:
            rows=c.execute("SELECT id,owner,epoch,head,host,expires,state FROM rooms").fetchall()
        return [dict(r) for r in rows]

    @app.post("/api/rooms")
    def create(user=Depends(authenticate)):
        disk=shutil.disk_usage(store.root)
        if disk.free/disk.total < .1:
            raise HTTPException(507,"磁盘剩余空间低于10%")
        return {"id":store.create(user["name"])}

    @app.post("/api/rooms/{room}/claim")
    def claim(room:str,body:Claim,user=Depends(authenticate)):
        try:
            return store.claim(room,user["name"],body.confirm_recovery)
        except KeyError:
            raise HTTPException(404,"实例不存在")

    @app.post("/api/rooms/{room}/renew")
    def renew(room:str,body:Lease,user=Depends(authenticate)):
        store.renew(room,user["name"],body.token,body.epoch)
        return {"ok":True}

    @app.post("/api/rooms/{room}/commit")
    def commit(room:str,body:Commit,user=Depends(authenticate)):
        return {"version":store.commit(room,user["name"],body.token,body.epoch,body.parent,body.manifest)}

    # Uploads are lease-scoped; a regular login cannot fill arbitrary worlds.
    @app.put("/api/rooms/{room}/blobs/{digest}")
    async def put_blob(room:str,digest:str,request:Request,
                       x_lease:str=Header(),x_epoch:int=Header(),user=Depends(authenticate)):
        if not re.fullmatch("[0-9a-f]{64}",digest):
            raise HTTPException(400,"非法哈希")
        with store.connect() as c:
            store._lease(c,room,user["name"],x_lease,x_epoch)
        data=bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data)>4*1024*1024:
                raise HTTPException(413,"数据块超过4MiB")
        if hashlib.sha256(data).hexdigest()!=digest:
            raise HTTPException(400,"SHA256校验失败")
        disk=shutil.disk_usage(store.root)
        if disk.free/disk.total < .1 or disk.free < len(data)*2:
            raise HTTPException(507,"存储空间不足")
        store.put_blob(data)
        return {"ok":True}

    @app.get("/api/rooms/{room}/head")
    def head(room:str,user=Depends(authenticate)):
        with store.connect() as c:
            r=c.execute("SELECT v.id,v.manifest FROM rooms r LEFT JOIN versions v ON v.id=r.head WHERE r.id=?",(room,)).fetchone()
        if not r:
            raise HTTPException(404,"实例不存在")
        return {"version":r["id"],"manifest":json.loads(r["manifest"]) if r["manifest"] else {}}

    return app

def add_user(store,name,password,role):
    if not re.fullmatch("[A-Za-z0-9_-]{1,32}",name) or len(password)<12:
        raise ValueError("账号1至32位字母数字下划线，密码至少12位")
    salt=secrets.token_bytes(16)
    digest=hashlib.pbkdf2_hmac("sha256",password.encode(),salt,200000).hex()
    with store.connect() as c:
        if role=="root" and c.execute("SELECT 1 FROM accounts WHERE role='root'").fetchone():
            raise ValueError("root已存在")
        c.execute("INSERT INTO accounts VALUES (?,?,?,?)",(name,salt.hex(),digest,role))

def main():
    import getpass
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["init-root","create-user"])
    p.add_argument("--data",default=os.environ.get("AETHERLOOM_DATA","./data"))
    p.add_argument("--username",default="root")
    p.add_argument("--role",choices=["admin","player"],default="player")
    a=p.parse_args()
    password=getpass.getpass("Password (12+ characters): ")
    if password!=getpass.getpass("Confirm password: "):
        p.error("Passwords differ")
    app=create_app(a.data)
    add_user(app.state.store,a.username,password,"root" if a.action=="init-root" else a.role)
    print("Account created")

if __name__=="__main__":
    main()

