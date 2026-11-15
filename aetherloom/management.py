"""CraftLink-compatible account policy adapted for persistent world rooms.

Policy source: CraftLink gatekeeper.py, GPL-3.0, commit 8178a3df.
Software identity changes never modify Minecraft identities or world NBT.
"""
import datetime
import hashlib
import json
import secrets
import time
from fastapi import HTTPException


def install(store):
    with store.connect() as c:
        c.executescript('''
CREATE TABLE IF NOT EXISTS account_settings(name TEXT PRIMARY KEY, disabled INTEGER DEFAULT 0,
 month TEXT, changes INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS room_settings(room TEXT PRIMARY KEY, name TEXT, environment TEXT,
 world TEXT, mode TEXT DEFAULT 'AUTO');
CREATE TABLE IF NOT EXISTS members(room TEXT, actor TEXT, PRIMARY KEY(room,actor));
CREATE TABLE IF NOT EXISTS audit(id TEXT PRIMARY KEY, actor TEXT, action TEXT, target TEXT, detail TEXT, created REAL);
CREATE TABLE IF NOT EXISTS recovery_uploads(id TEXT PRIMARY KEY, room TEXT, actor TEXT, expires REAL);
''')


def audit(c, actor, action, target, detail=None):
    c.execute('INSERT INTO audit VALUES (?,?,?,?,?,?)',
        (secrets.token_hex(16), actor, action, target, json.dumps(detail or {}, ensure_ascii=False), time.time()))


def valid_name(name,minimum=2):
    if not minimum <= len(name) <= 32 or any(x.isspace() or ord(x) < 32 for x in name):
        raise ValueError(f'账号名称应为{minimum}至32位，不能包含空白或控制字符')


def password_hash(password):
    if not 6 <= len(password) <= 1024:
        raise ValueError('密码应为6至1024位')
    salt = secrets.token_bytes(16)
    return salt.hex(), hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 200000).hex()


def edit_account(store, actor, target, body, delete=False):
    with store.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT * FROM accounts WHERE name=?', (target,)).fetchone()
        if not row:
            raise HTTPException(404, '账号不存在')
        if row['role'] == 'root':
            raise HTTPException(403, 'root受保护，仅允许服务器本地恢复工具修改')
        privileged = actor['role'] in ('root', 'admin')
        if not privileged and (target != actor['name'] or delete):
            raise HTTPException(403, '无权修改该账号')
        allowed = {'username', 'password', 'role', 'disabled'} if privileged else {'username', 'password'}
        if set(body) - allowed:
            raise HTTPException(403, '无权执行该操作')
        if 'role' in body and (actor['role'] != 'root' or body['role'] not in ('admin', 'player')):
            raise HTTPException(403, '只有root可以变更admin/player权限组')
        current = c.execute('SELECT * FROM account_settings WHERE name=?', (target,)).fetchone()
        month = datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m')
        changes = current['changes'] if current and current['month'] == month else 0
        edits = int('username' in body and body['username'] != target) + int('password' in body)
        if not privileged and changes + edits > 3:
            raise HTTPException(429, '每个自然月改名和改密合计最多3次')
        if delete:
            if row['role']=='admin':
                admins=c.execute("SELECT a.name FROM accounts a LEFT JOIN account_settings s ON s.name=a.name WHERE a.role IN ('root','admin') AND COALESCE(s.disabled,0)=0").fetchall()
                if any(a['name']==target for a in admins) and len(admins)<=1:
                    raise HTTPException(409,'不能删除最后一个可用admin')
            if c.execute('SELECT 1 FROM rooms WHERE owner=?', (target,)).fetchone():
                raise HTTPException(409, '请先转移或删除该账号拥有的共享房间，避免存档失去所有者')
            if c.execute('SELECT 1 FROM rooms WHERE host=? AND expires>?', (target,time.time())).fetchone():
                raise HTTPException(409, '该账号正在托管，请先保存并结束会话')
            for table, column in (('sessions','actor'),('members','actor'),('managers','actor'),('recovery_uploads','actor'),('account_settings','name'),('accounts','name')):
                c.execute(f'DELETE FROM {table} WHERE {column}=?', (target,))
            audit(c,actor['name'],'delete_user',target)
            return {'ok':True}
        if 'password' in body:
            salt,digest=password_hash(body['password'])
            c.execute('UPDATE accounts SET salt=?,digest=? WHERE name=?',(salt,digest,target))
        if 'role' in body:
            c.execute('UPDATE accounts SET role=? WHERE name=?',(body['role'],target))
        if not current:
            c.execute('INSERT INTO account_settings(name,disabled,month,changes) VALUES (?,0,?,0)',(target,month))
        if 'disabled' in body:
            if not isinstance(body['disabled'],bool):raise ValueError('disabled应为布尔值')
            c.execute('UPDATE account_settings SET disabled=? WHERE name=?',(int(body['disabled']),target))
        c.execute('UPDATE account_settings SET month=?,changes=? WHERE name=?',(month,changes+edits,target))
        if 'password' in body or body.get('disabled') or (body.get('role')=='player' and row['role']=='admin'):
            c.execute('DELETE FROM sessions WHERE actor=?',(target,))
        name=body.get('username',target)
        if name != target:
            valid_name(name)
            if c.execute('SELECT 1 FROM accounts WHERE name=?',(name,)).fetchone():
                raise HTTPException(409,'账号名称已存在')
            for table,column in (('accounts','name'),('account_settings','name'),('sessions','actor'),('rooms','owner'),('rooms','host'),('managers','actor'),('members','actor'),('versions','actor'),('recovery_uploads','actor')):
                c.execute(f'UPDATE {table} SET {column}=? WHERE {column}=?',(name,target))
        audit(c,actor['name'],'edit_user',target,{'fields':list(body),'new_name':name})
        return {'ok':True,'username':name}
