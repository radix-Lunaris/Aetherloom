"""Unified control API. Production metadata is persisted in private MySQL."""
import argparse
import asyncio
import errno
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
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Request, Depends, WebSocket
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .store import Authority, Conflict
from .management import install, edit_account, valid_name, password_hash, audit
from . import __version__
from .presence import Presence

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

class RoomInput(BaseModel):
    name: str = Field(default='共享世界', min_length=1, max_length=80)
    environment: str = Field(default='1.20.1 Forge 47.4.22', max_length=200)
    world: str = Field(default='', max_length=200)
    required_mods: dict[str,tuple[str,str]] | None = Field(default=None,max_length=4096)

class MemberInput(BaseModel):
    username: str
    role: str = 'member'

def create_app(data_dir=None):
    store = Authority(Path(data_dir or os.environ.get("AETHERLOOM_DATA", "./data")))
    with store.connect() as c:
        c.executescript("""
CREATE TABLE IF NOT EXISTS panel_grants(actor TEXT PRIMARY KEY,access_level TEXT);
CREATE TABLE IF NOT EXISTS room_optional_mods(room TEXT PRIMARY KEY,manifest TEXT);
CREATE TABLE IF NOT EXISTS room_modpacks(room TEXT PRIMARY KEY, manifest TEXT);
CREATE TABLE IF NOT EXISTS accounts(name TEXT PRIMARY KEY, salt TEXT, digest TEXT, role TEXT);
CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY, actor TEXT, expires REAL);
""")
    install(store)
    @asynccontextmanager
    async def lifespan(app):
        bind=os.environ.get('AETHERLOOM_P2P_BIND')
        if bind:
            from .rendezvous import Rendezvous
            relay.rendezvous=Rendezvous(bind)
        udp_transport=None
        udp_bind=os.environ.get("AETHERLOOM_DATAGRAM_BIND")
        if udp_bind:
            from .datagram_relay import DatagramRelay
            host,port=udp_bind.rsplit(":",1)
            udp_transport,relay.datagrams=await asyncio.get_running_loop().create_datagram_endpoint(DatagramRelay,local_addr=(host,int(port)))
        try:yield
        finally:
            if udp_transport:udp_transport.close()
            if relay.rendezvous:relay.rendezvous.close()
    app = FastAPI(title="Aetherloom", version=__version__, docs_url=None, redoc_url=None, openapi_url=None,lifespan=lifespan)
    app.state.store = store
    upload_slots=asyncio.Semaphore(max(1,min(16,int(os.environ.get("AETHERLOOM_TRANSFER_CONCURRENCY","4")))))
    attempts = {}
    attempts_lock = threading.Lock()

    @app.middleware('http')
    async def security_headers(request, call_next):
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    if os.environ.get('AETHERLOOM_PANEL') == '1':
        static = Path(__file__).with_name('panel')
        @app.get('/')
        def panel():
            return FileResponse(static/'index.html')
        @app.get('/panel.js')
        def panel_js():
            return FileResponse(static/'panel.js', media_type='application/javascript')
        @app.get('/mark.png')
        def panel_mark():
            return FileResponse(static/'mark.png',media_type='image/png')
        @app.get('/panel.css')
        def panel_css():
            return FileResponse(static/'panel.css', media_type='text/css')

    def authenticate(authorization: str = Header(default="")):
        token = authorization.removeprefix("Bearer ")
        hashed = hashlib.sha256(token.encode()).hexdigest()
        with store.connect() as c:
            row = c.execute("SELECT a.name,a.role FROM sessions s JOIN accounts a ON a.name=s.actor LEFT JOIN account_settings p ON p.name=a.name WHERE s.token=? AND s.expires>? AND COALESCE(p.disabled,0)=0",
                            (hashed,time.time())).fetchone()
        if not row:
            raise HTTPException(401,"请先登录 Aetherloom")
        return dict(row)

    if os.environ.get("AETHERLOOM_PANEL")=="1":
        from . import panel_settings
        panel_settings.install(app,store,authenticate,audit)

    def manager(room, user):
        with store.connect() as c:
            r=c.execute("SELECT * FROM rooms WHERE id=?",(room,)).fetchone()
            m=c.execute("SELECT 1 FROM managers WHERE room=? AND actor=?",(room,user["name"])).fetchone()
        if not r:
            raise HTTPException(404,"实例不存在")
        if user["role"] != "root" and r["owner"] != user["name"] and not m:
            raise HTTPException(403,"需要实例管理权限")

    def participant(room:str,user=Depends(authenticate)):
        with store.connect() as c:
            r=c.execute('SELECT owner FROM rooms WHERE id=?',(room,)).fetchone()
            joined=c.execute('SELECT 1 FROM members WHERE room=? AND actor=?',(room,user['name'])).fetchone()
        if not r:raise HTTPException(404,'房间不存在')
        if user['role']!='root' and r['owner']!=user['name'] and not joined:raise HTTPException(403,'请先加入此共享房间')
        return user

    from .relay import Relay
    relay=Relay(store,authenticate,participant)
    app.state.relay=relay

    @app.get('/api/connections/{sid}/punch')
    async def punch_info(sid:str,user=Depends(authenticate)):
        pair=relay.pairs.get(sid)
        if not pair:raise HTTPException(404,'通道不存在')
        participant(pair.room,user)
        return relay.punch(sid,user['name'])

    @app.websocket('/api/relay')
    async def relay_socket(ws:WebSocket):
        await relay.websocket(ws)

    @app.post('/api/rooms/{room}/connections')
    async def connect_room(room:str,body:dict={},user=Depends(participant)):
        return relay.create(room,user['name'],body.get('identity'))

    @app.get('/api/rooms/{room}/connections')
    async def pending_connections(room:str,user=Depends(participant)):
        return relay.pending(room,user['name'])

    @app.post('/api/rooms/{room}/ready')
    def ready(room:str,body:Lease,user=Depends(participant)):
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            store._lease(c,room,user['name'],body.token,body.epoch)
            c.execute("UPDATE rooms SET state='ready' WHERE id=?",(room,))
        return {'ok':True}

    @app.exception_handler(Conflict)
    async def conflict(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409,content={"detail":str(exc)})

    @app.exception_handler(ValueError)
    async def invalid(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=400,content={"detail":str(exc)})

    @app.exception_handler(OSError)
    async def storage_error(request,exc):
        from fastapi.responses import JSONResponse
        full=exc.errno==errno.ENOSPC
        return JSONResponse(status_code=507 if full else 503,content={'detail':'存储空间不足，权威版本未更改' if full else '存储暂不可用，请保留本地数据后重试'})

    @app.exception_handler(sqlite3.IntegrityError)
    async def duplicate(request,exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=409,content={"detail":"记录已存在"})

    @app.get("/health")
    def health():
        ports=[int(os.environ.get('AETHERLOOM_STUN_PORT','52718')),int(os.environ.get('AETHERLOOM_STUN_PORT2','52719'))] if os.environ.get('AETHERLOOM_STUN_ENABLED')=='1' else []
        return {"status":"ok","version":__version__,"stun_ports":ports}

    @app.post("/api/login")
    def login(body:Login, request:Request):
        key=(request.client.host if request.client else 'unknown',body.username)
        now=time.monotonic()
        with attempts_lock:
            stale=[k for k,v in attempts.items() if now-v[0]>60]
            for k in stale:del attempts[k]
            if key in attempts and attempts[key][1]>=10:
                raise HTTPException(429,'登录尝试过多，请一分钟后重试')
            if len(attempts)>10000:
                raise HTTPException(429,'登录繁忙，请稍后重试')
            first,count=attempts.get(key,(now,0))
            attempts[key]=(first,count+1)
        with store.connect() as c:
            row=c.execute("SELECT * FROM accounts WHERE name=?",(body.username,)).fetchone()
        # Compute a hash even for missing usernames.
        digest=hashlib.pbkdf2_hmac("sha256",body.password.encode(),
            bytes.fromhex(row["salt"]) if row else b"0"*16,200000).hex()
        with store.connect() as c:
            settings=c.execute('SELECT disabled FROM account_settings WHERE name=?',(body.username,)).fetchone()
        if not row or (settings and settings['disabled']) or not hmac.compare_digest(digest,row["digest"]):
            raise HTTPException(401,"账号或密码错误")
        with attempts_lock:attempts.pop(key,None)
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
        result={"disk_total":disk.total,"disk_free":disk.free,"rooms":rooms,"accounts":accounts,
                "cpu_count":os.cpu_count(),"server_time":time.time(),"version":__version__}
        if hasattr(os,'getloadavg'):result['load_average']=os.getloadavg()
        meminfo=Path('/proc/meminfo')
        if meminfo.exists():
            memory={line.split(':')[0]:int(line.split()[1])*1024 for line in meminfo.read_text().splitlines() if len(line.split())>=2 and line.split()[1].isdigit()}
            result['memory_total']=memory.get('MemTotal')
            result['memory_available']=memory.get('MemAvailable')
        return result

    @app.get('/api/users')
    def list_users(user=Depends(authenticate)):
        if user['role'] not in ('root','admin'):
            raise HTTPException(403,'需要服务器管理权限')
        with store.connect() as c:
            return [dict(r) for r in c.execute('SELECT a.name,a.role,COALESCE(s.disabled,0) AS disabled FROM accounts a LEFT JOIN account_settings s ON s.name=a.name ORDER BY a.name').fetchall()]

    @app.patch('/api/users/{name}')
    def edit_user(name:str,body:dict,user=Depends(authenticate)):
        result=edit_account(store,user,name,body)
        if result.get('username')!=name:relay.rename(name,result['username'])
        return result

    @app.delete('/api/users/{name}')
    def delete_user(name:str,user=Depends(authenticate)):
        return edit_account(store,user,name,{},delete=True)

    @app.patch('/api/me')
    def edit_self(body:dict,user=Depends(authenticate)):
        result=edit_account(store,user,user['name'],body)
        if result.get('username')!=user['name']:relay.rename(user['name'],result['username'])
        return result

    @app.get('/api/me')
    def get_self(user=Depends(authenticate)):
        return user

    @app.get('/api/audit')
    def get_audit(user=Depends(authenticate)):
        if user['role'] not in ('root','admin'):raise HTTPException(403,'需要服务器管理权限')
        with store.connect() as c:
            return [dict(r) for r in c.execute('SELECT * FROM audit ORDER BY created DESC LIMIT 200').fetchall()]

    @app.post("/api/users")
    def users(body:UserInput,user=Depends(authenticate)):
        if user["role"] not in ("root","admin") or body.role not in ("admin","player") or (body.role=="admin" and user["role"]!="root"):
            raise HTTPException(403,"无权创建该角色")
        add_user(store,body.username,body.password,body.role)
        with store.connect() as c:audit(c,user['name'],'create_user',body.username,{'role':body.role})
        return {"ok":True}

    @app.get("/api/rooms")
    def rooms(user=Depends(authenticate)):
        with store.connect() as c:
            rows=c.execute("SELECT r.id,r.owner,r.epoch,r.head,r.host,r.expires,r.state,COALESCE(s.name,r.id) AS name,s.environment,s.world,s.mode FROM rooms r LEFT JOIN room_settings s ON s.room=r.id").fetchall()
            optional={row["room"]:set(json.loads(row["manifest"])) for row in c.execute("SELECT room,manifest FROM room_optional_mods").fetchall()}
            packs={row["room"]:json.loads(row["manifest"]) for row in c.execute("SELECT room,manifest FROM room_modpacks").fetchall()}
            managed={r['room'] for r in c.execute('SELECT room FROM managers WHERE actor=?',(user['name'],)).fetchall()}
        result=[dict(r) for r in rows]
        for room in result:
            if room["id"] in packs:
                room["required_mods"]={k:v for k,v in packs[room["id"]].items() if k not in optional.get(room["id"],())}
                room["optional_mods"]=sorted(optional.get(room["id"],()))
        for r in result:r['can_manage']=user['role']=='root' or r['owner']==user['name'] or r['id'] in managed
        return result

    @app.get('/api/rooms/{room}/membership')
    def membership(room:str,user=Depends(participant)):
        return {'ok':True,'username':user['name']}

    @app.get('/api/rooms/{room}/account-options')
    def account_options(room:str,user=Depends(authenticate)):
        # Only ownership/member managers may enumerate eligible target names.
        with store.connect() as c:
            r=c.execute('SELECT owner FROM rooms WHERE id=?',(room,)).fetchone()
            if not r:raise HTTPException(404,'房间不存在')
            if user['role']!='root' and user['name']!=r['owner']:
                raise HTTPException(403,'仅Owner或root可选择账号管理成员与所有权')
            return [dict(row) for row in c.execute('SELECT a.name FROM accounts a LEFT JOIN account_settings s ON s.name=a.name WHERE COALESCE(s.disabled,0)=0 ORDER BY a.name').fetchall()]

    @app.post('/api/connections/{sid}/report')
    async def report_stream(sid:str,body:dict,user=Depends(authenticate)):
        pair=relay.pairs.get(sid)
        if not pair:return {"closed":True}
        participant(pair.room,user)
        if user["name"] not in (pair.host,pair.player):
            raise HTTPException(403,"不是此连接的成员")
        room=relay.room(pair.room)
        if body.get("epoch")!=pair.epoch or room["epoch"]!=pair.epoch or pair.revoked:return {"closed":True}
        state={k:v for k,v in body.items() if k in ("active_path","switch_phase","direct_rtt_ms","relay_rtt_ms") and type(v) in (str,int,float) and len(str(v))<=64}
        pair.reports[user["name"]]={**state,"time":time.time()}
        pair.touched=time.monotonic()
        return {"closed":False}

    @app.delete('/api/rooms/{room}/streams/{epoch}/{sid}')
    async def disconnect_stream(room:str,epoch:int,sid:str,user=Depends(authenticate)):
        manager(room,user)
        pair=relay.pairs.get(sid)
        if not pair or pair.room!=room or pair.channel!="data" or pair.epoch!=epoch or relay.room(room)["epoch"]!=epoch:
            raise HTTPException(409,"流已结束或代次已变化")
        pair.revoked=True
        for ws in list(pair.ends.values()):
            try:await ws.close(code=1000)
            except RuntimeError:pass
        with store.connect() as c:audit(c,user["name"],"disconnect_stream",room,{"sid":sid,"epoch":epoch})
        return {"ok":True}

    @app.put('/api/rooms/{room}/required-mods')
    def update_required_mods(room:str,body:dict,user=Depends(authenticate)):
        manager(room,user)
        required=body.get("required")
        if not isinstance(required,list) or len(required)>4096 or not all(isinstance(key,str) for key in required):
            raise HTTPException(400,"模组选择无效")
        with store.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            active=c.execute("SELECT host,expires,owner FROM rooms WHERE id=?",(room,)).fetchone()
            if not active:raise HTTPException(404,"房间不存在")
            if user["role"]!="root" and active["owner"]!=user["name"] and not c.execute("SELECT 1 FROM managers WHERE room=? AND actor=?",(room,user["name"])).fetchone():
                raise HTTPException(403,"房间管理权限已撤销")
            if active["host"] and active["expires"]>time.time():raise Conflict("请在结束托管后调整模组")
            row=c.execute("SELECT manifest FROM room_modpacks WHERE room=?",(room,)).fetchone()
            if not row:raise HTTPException(409,"此房间尚未登记模组清单")
            catalog=json.loads(row["manifest"])
            if set(required)-catalog.keys():raise HTTPException(400,"包含未登记的模组")
            c.execute("DELETE FROM room_optional_mods WHERE room=?",(room,))
            c.execute("INSERT INTO room_optional_mods(room,manifest) VALUES (?,?)",(room,json.dumps(sorted(catalog.keys()-set(required)))))
            audit(c,user["name"],"edit_required_mods",room,{"count":len(required)})
        return {"ok":True}

    @app.get('/api/connections/{sid}/datagrams')
    async def udp_grant(sid:str,user=Depends(authenticate)):
        pair=relay.pairs.get(sid)
        if not pair or pair.channel!="network" or not getattr(relay,"datagrams",None):
            raise HTTPException(404,"UDP 服务不可用")
        participant(pair.room,user)
        room=relay.room(pair.room)
        if room["epoch"]!=pair.epoch or room["host"]!=pair.host:
            raise HTTPException(409,"Host 已变更")
        if user["name"] not in (pair.host,pair.player):
            raise HTTPException(403,"没有此连接的权限")
        return relay.datagrams.grant(sid,0 if user["name"]==pair.host else 1)

    @app.get('/api/rooms/{room}/diagnostics')
    async def connection_diagnostics(room:str,user=Depends(authenticate)):
        manager(room,user)
        with store.connect() as c:
            r=c.execute('SELECT epoch,host,expires,state FROM rooms WHERE id=?',(room,)).fetchone()
        # Server can observe relay attachments, not whether clients use P2P.
        return {'room':room,'host':r['host'],'epoch':r['epoch'],'state':r['state'],
                'streams':[{'id':p.sid,'player':p.player,'channel':p.channel,'mode':p.mode,
                            'reports':{actor:state for actor,state in p.reports.items() if time.time()-state['time']<15},'closed':p.revoked,'host_attached':'host' in p.ends,'player_attached':'player' in p.ends,
                            'path':'服务器仅观测中继承载；P2P 状态见客户端'}
                           for p in relay.pairs.values() if p.room==room and p.epoch==r['epoch']]}

    @app.post("/api/rooms")
    def create(body:RoomInput=RoomInput(),user=Depends(authenticate)):
        disk=shutil.disk_usage(store.root)
        if disk.free/disk.total < .1:
            raise HTTPException(507,"磁盘剩余空间低于10%")
        room=store.create(user['name'])
        with store.connect() as c:
            c.execute('INSERT INTO room_settings(room,name,environment,world,mode) VALUES (?,?,?,?,?)',(room,body.name,body.environment,body.world,'AUTO'))
            if body.required_mods is not None:
                c.execute('INSERT INTO room_modpacks(room,manifest) VALUES (?,?)',(room,json.dumps(body.required_mods)))
            c.execute('INSERT INTO members VALUES (?,?)',(room,user['name']))
            audit(c,user['name'],'create_room',room,body.model_dump())
        return {"id":room}

    @app.patch('/api/rooms/{room}')
    def edit_room(room:str,body:dict,user=Depends(authenticate)):
        manager(room,user)
        if set(body)-{'name','environment','world','mode','owner'}:raise ValueError('未知房间属性')
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            r=c.execute('SELECT * FROM rooms WHERE id=?',(room,)).fetchone()
            if not r:raise HTTPException(404,'房间不存在')
            if user['role']!='root' and r['owner']!=user['name'] and not c.execute('SELECT 1 FROM managers WHERE room=? AND actor=?',(room,user['name'])).fetchone():raise HTTPException(403,'实例管理权限已变化')
            if r['token'] and r['expires']>time.time():raise Conflict('请先正常保存并结束托管')
            settings=c.execute('SELECT * FROM room_settings WHERE room=?',(room,)).fetchone()
            if not settings:c.execute('INSERT INTO room_settings(room,name) VALUES (?,?)',(room,room))
            for key,value in body.items():
                if not isinstance(value,str) or not value or len(value)>200:raise ValueError('房间属性无效')
                if key=='mode' and value not in ('AUTO','RELAY','DIRECT'):raise ValueError('未知连接策略')
                if key=='owner':
                    if user['role']!='root' and r['owner']!=user['name']:raise HTTPException(403,'仅Owner或root可转移所有权')
                    if not c.execute('SELECT 1 FROM accounts WHERE name=?',(value,)).fetchone():raise ValueError('新所有者账号不存在')
                    c.execute('UPDATE rooms SET owner=? WHERE id=?',(value,room))
                    if not c.execute('SELECT 1 FROM members WHERE room=? AND actor=?',(room,value)).fetchone():
                        c.execute('INSERT INTO members VALUES (?,?)',(room,value))
                else:c.execute(f'UPDATE room_settings SET {key}=? WHERE room=?',(value,room))
            audit(c,user['name'],'edit_room',room,body)
        return {'ok':True}

    @app.delete('/api/rooms/{room}')
    def delete_room(room:str,user=Depends(authenticate)):
        manager(room,user)
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            r=c.execute('SELECT * FROM rooms WHERE id=?',(room,)).fetchone()
            if not r:raise HTTPException(404,'房间不存在')
            if user['role']!='root' and r['owner']!=user['name'] and not c.execute('SELECT 1 FROM managers WHERE room=? AND actor=?',(room,user['name'])).fetchone():raise HTTPException(403,'实例管理权限已变化')
            if r['token'] and r['expires']>time.time():raise Conflict('房间正在托管，需先正常保存退出')
            # Immutable versions/blobs remain available to server backup/recovery.
            for table,column in (('room_optional_mods','room'),('room_modpacks','room'),('members','room'),('managers','room'),('room_settings','room'),('rooms','id')):
                c.execute(f'DELETE FROM {table} WHERE {column}=?',(room,))
            audit(c,user['name'],'delete_room',room,{'head':r['head'],'state':r['state'],'epoch':r['epoch']})
        return {'ok':True}

    @app.post('/api/rooms/{room}/join')
    def join_room(room:str,user=Depends(authenticate)):
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            if not c.execute('SELECT 1 FROM rooms WHERE id=?',(room,)).fetchone():raise HTTPException(404,'房间不存在')
            if not c.execute('SELECT 1 FROM members WHERE room=? AND actor=?',(room,user['name'])).fetchone():
                c.execute('INSERT INTO members VALUES (?,?)',(room,user['name']))
        return {'ok':True}

    @app.get('/api/rooms/{room}/members')
    def room_members(room:str,user=Depends(authenticate)):
        with store.connect() as c:
            return [dict(r) for r in c.execute('SELECT m.actor,CASE WHEN r.owner=m.actor THEN \'owner\' WHEN a.actor IS NOT NULL THEN \'admin\' ELSE \'member\' END AS role FROM members m JOIN rooms r ON r.id=m.room LEFT JOIN managers a ON a.room=m.room AND a.actor=m.actor WHERE m.room=?',(room,)).fetchall()]

    @app.post('/api/rooms/{room}/members')
    def set_member(room:str,body:MemberInput,user=Depends(authenticate)):
        manager(room,user)
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            r=c.execute('SELECT * FROM rooms WHERE id=?',(room,)).fetchone()
            if r['owner']!=user['name'] and user['role']!='root':raise HTTPException(403,'仅Owner或root可管理成员权限')
            if body.username==r['owner']:raise ValueError('不能修改Owner的成员权限')
            if not c.execute('SELECT 1 FROM accounts WHERE name=?',(body.username,)).fetchone():raise ValueError('账号不存在')
            if body.role not in ('member','admin','remove'):raise ValueError('无效的实例权限')
            if r['host']==body.username and r['expires']>time.time():raise Conflict('请先结束该成员的托管')
            c.execute('DELETE FROM managers WHERE room=? AND actor=?',(room,body.username))
            c.execute('DELETE FROM members WHERE room=? AND actor=?',(room,body.username))
            if body.role!='remove':c.execute('INSERT INTO members VALUES (?,?)',(room,body.username))
            if body.role=='admin':c.execute('INSERT INTO managers VALUES (?,?)',(room,body.username))
            audit(c,user['name'],'member_role',room,body.model_dump())
        return {'ok':True}

    presence=Presence()
    @app.post('/api/rooms/{room}/presence')
    def room_presence(room:str,body:dict,user=Depends(participant)):
        device=body.get('device','');active=body.get('active',True)
        if not isinstance(device,str) or not re.fullmatch('[a-f0-9]{32}',device) or type(active)!=bool:raise HTTPException(400,'Invalid presence heartbeat')
        return {'online':presence.heartbeat(user['name'],device,room,active),'ttl':presence.ttl}

    @app.post("/api/rooms/{room}/claim")
    def claim(room:str,body:Claim,user=Depends(participant)):
        try:
            return store.claim(room,user["name"],body.confirm_recovery)
        except KeyError:
            raise HTTPException(404,"实例不存在")

    @app.post("/api/rooms/{room}/renew")
    def renew(room:str,body:Lease,user=Depends(participant)):
        store.renew(room,user["name"],body.token,body.epoch)
        return {"ok":True}

    @app.post('/api/rooms/{room}/cancel')
    def cancel_unloaded(room:str,body:Lease,user=Depends(participant)):
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            r=store._lease(c,room,user['name'],body.token,body.epoch)
            if r['state']!='preparing':raise Conflict('已就绪的世界必须正常保存上传后结束')
            c.execute("UPDATE rooms SET token=NULL,host=NULL,expires=0,state='idle' WHERE id=?",(room,))
            audit(c,user['name'],'cancel_preparing',room)
        return {'ok':True}

    @app.post('/api/rooms/{room}/uploading')
    def begin_upload(room:str,body:Lease,user=Depends(participant)):
        with store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            store._lease(c,room,user['name'],body.token,body.epoch)
            c.execute("UPDATE rooms SET state='uploading' WHERE id=?",(room,))
        return {'ok':True}

    @app.post("/api/rooms/{room}/commit")
    def commit(room:str,body:Commit,user=Depends(participant)):
        return {"version":store.commit(room,user["name"],body.token,body.epoch,body.parent,body.manifest)}

    def recovery_permission(c,room,actor,ticket):
        token=hashlib.sha256(ticket.encode()).hexdigest()
        if not c.execute('SELECT 1 FROM recovery_uploads WHERE id=? AND room=? AND actor=? AND expires>?',(token,room,actor,time.time())).fetchone():
            raise HTTPException(403,'恢复上传凭据已失效')

    @app.post('/api/rooms/{room}/recoveries/start')
    def recovery_start(room:str,user=Depends(participant)):
        ticket=secrets.token_urlsafe(32)
        with store.connect() as c:
            if not c.execute('SELECT 1 FROM rooms WHERE id=?',(room,)).fetchone():raise HTTPException(404,'房间不存在')
            c.execute('DELETE FROM recovery_uploads WHERE expires<? OR (room=? AND actor=?)',(time.time(),room,user['name']))
            c.execute('INSERT INTO recovery_uploads VALUES (?,?,?,?)',(hashlib.sha256(ticket.encode()).hexdigest(),room,user['name'],time.time()+3600))
        return {'ticket':ticket}

    @app.post('/api/rooms/{room}/recoveries')
    def recovery_submit(room:str,body:dict,user=Depends(participant)):
        with store.connect() as c:recovery_permission(c,room,user['name'],body['ticket'])
        candidate=store.candidate(room,user['name'],body.get('parent'),body['manifest'])
        with store.connect() as c:
            c.execute('DELETE FROM recovery_uploads WHERE id=?',(hashlib.sha256(body['ticket'].encode()).hexdigest(),))
            audit(c,user['name'],'recovery_candidate',room,{'candidate':candidate,'parent':body.get('parent')})
        return {'candidate':candidate}

    @app.get('/api/rooms/{room}/recoveries')
    def recoveries(room:str,user=Depends(authenticate)):
        manager(room,user)
        with store.connect() as c:
            return [dict(r) for r in c.execute('SELECT id,parent,actor FROM versions WHERE room=? AND candidate=1',(room,)).fetchall()]

    @app.post('/api/rooms/{room}/recoveries/{candidate}/approve')
    def approve_recovery(room:str,candidate:str,body:dict,user=Depends(authenticate)):
        manager(room,user)
        with store.connect() as c:
            source=c.execute('SELECT candidate FROM versions WHERE id=? AND room=?',(candidate,room)).fetchone()
            if not source or source['candidate']!=1:raise HTTPException(404,'候选不存在')
        version=store.restore(room,user['name'],candidate,body.get('expected_head'),root=user['role']=='root')
        with store.connect() as c:audit(c,user['name'],'approve_recovery',room,{'candidate':candidate,'version':version})
        return {'version':version}

    # Uploads are lease-scoped; a regular login cannot fill arbitrary worlds.
    @app.put("/api/rooms/{room}/blobs/{digest}")
    async def put_blob(room:str,digest:str,request:Request,
                       x_lease:str=Header(default=''),x_epoch:int=Header(default=0),x_recovery:str=Header(default=''),user=Depends(participant)):
        if not re.fullmatch("[0-9a-f]{64}",digest):
            raise HTTPException(400,"非法哈希")
        with store.connect() as c:
            if x_recovery:recovery_permission(c,room,user['name'],x_recovery)
            else:store._lease(c,room,user["name"],x_lease,x_epoch)
        async with upload_slots:
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
    def head(room:str,user=Depends(participant)):
        with store.connect() as c:
            r=c.execute("SELECT v.id,v.manifest FROM rooms r LEFT JOIN versions v ON v.id=r.head WHERE r.id=?",(room,)).fetchone()
        if not r:
            raise HTTPException(404,"实例不存在")
        return {"version":r["id"],"manifest":json.loads(r["manifest"]) if r["manifest"] else {}}

    @app.post('/api/rooms/{room}/missing')
    def missing(room:str,body:dict,user=Depends(participant)):
        with store.connect() as c:
            if body.get('recovery'):recovery_permission(c,room,user['name'],body['recovery'])
            else:
                lease=Lease(**body['lease'])
                store._lease(c,room,user['name'],lease.token,lease.epoch)
        hashes=body.get('hashes',[])
        if len(hashes)>4096 or any(not isinstance(h,str) or not re.fullmatch('[0-9a-f]{64}',h) for h in hashes):raise ValueError('非法数据块清单')
        return {'missing':[h for h in hashes if not (store.root/'blobs'/h[:2]/h).is_file()]}

    @app.get('/api/rooms/{room}/blobs/{digest}')
    def download_blob(room:str,digest:str,user=Depends(participant)):
        if not re.fullmatch('[0-9a-f]{64}',digest):raise HTTPException(400,'非法哈希')
        with store.connect() as c:
            row=c.execute('SELECT v.manifest FROM rooms r JOIN versions v ON v.id=r.head WHERE r.id=?',(room,)).fetchone()
        if not row or not any(piece[2]==digest for entry in json.loads(row['manifest']).values() for piece in entry['pieces']):raise HTTPException(404,'该房间没有此数据块')
        path=store.root/'blobs'/digest[:2]/digest
        if not path.is_file():raise HTTPException(409,'云端缺少数据块，禁止开服')
        return FileResponse(path,media_type='application/octet-stream')

    return app

def add_user(store,name,password,role):
    valid_name(name,minimum=1)
    if role not in ('root','admin','player'):raise ValueError('未知权限组')
    salt,digest=password_hash(password)
    with store.connect() as c:
        if role=="root" and c.execute("SELECT 1 FROM accounts WHERE role='root'").fetchone():
            raise ValueError("root已存在")
        c.execute("INSERT INTO accounts(name,salt,digest,role) VALUES (?,?,?,?)",(name,salt,digest,role))

def main():
    import getpass
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=["init-root","create-user","reset-root"])
    p.add_argument("--data",default=os.environ.get("AETHERLOOM_DATA","./data"))
    p.add_argument("--username",default="root")
    p.add_argument("--role",choices=["admin","player"],default="player")
    a=p.parse_args()
    password=getpass.getpass("Password (6+ characters): ")
    if password!=getpass.getpass("Confirm password: "):
        p.error("Passwords differ")
    app=create_app(a.data)
    if a.action=='reset-root':
        salt,digest=password_hash(password)
        with app.state.store.connect() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute("SELECT name FROM accounts WHERE role='root'").fetchone()
            if not row:p.error('root does not exist')
            c.execute('UPDATE accounts SET salt=?,digest=? WHERE name=?',(salt,digest,row['name']))
            c.execute('DELETE FROM sessions WHERE actor=?',(row['name'],))
            audit(c,'local-root-recovery','reset_root',row['name'])
        print('Root password changed; previous sessions revoked')
    else:
        add_user(app.state.store,a.username,password,"root" if a.action=="init-root" else a.role)
        print("Account created")

if __name__=="__main__":
    main()

