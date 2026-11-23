"""Panel-only settings and narrowly delegated account capabilities."""
import ipaddress
import json
import re
import socket
from fastapi import Depends, HTTPException, Request


from .panel_entry import validate_entry

def agent(operation,**args):
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
            sock.settimeout(12)
            sock.connect("/run/aetherloom-panel/control.sock")
            sock.sendall((json.dumps(dict(operation=operation,**args))+"\n").encode())
            result=json.loads(sock.makefile("rb").readline(8192))
        if "error" in result:
            raise HTTPException(409,result["error"])
        return result
    except (ValueError,OSError,AttributeError):
        raise HTTPException(503,"面板入口管理服务暂不可用") from None


def install(app,store,authenticate,audit):
    def capability(user):
        if user["role"]=="root":return "edit"
        with store.connect() as c:
            row=c.execute("SELECT access_level FROM panel_grants WHERE actor=?",(user["name"],)).fetchone()
        return row["access_level"] if row else None

    @app.get("/api/panel/access")
    def access(user=Depends(authenticate)):
        return {"access":capability(user)}

    @app.get("/api/panel/settings")
    def settings(user=Depends(authenticate)):
        if not capability(user):raise HTTPException(403,"未获面板设置权限")
        result=agent("read")
        if user["role"]=="root":
            with store.connect() as c:
                result["grants"]=[dict(r) for r in c.execute("SELECT actor,access_level FROM panel_grants").fetchall()]
        return result

    @app.post("/api/panel/settings")
    def stage(body:dict,user=Depends(authenticate)):
        if capability(user)!="edit":raise HTTPException(403,"需要面板修改权限")
        value=validate_entry(body)
        result=agent("stage",settings=value)
        with store.connect() as c:audit(c,user["name"],"panel_stage","panel",{"fields":list(value)})
        return result

    @app.post("/api/panel/confirm")
    def confirm(request:Request,user=Depends(authenticate)):
        if capability(user)!="edit":raise HTTPException(403,"需要面板修改权限")
        result=agent("confirm",proof=request.headers.get("x-aetherloom-entry",""))
        with store.connect() as c:audit(c,user["name"],"panel_confirm","panel",{})
        return result

    @app.put("/api/panel/grants/{actor}")
    def grant(actor:str,body:dict,user=Depends(authenticate)):
        if user["role"]!="root":raise HTTPException(403,"仅 root 可授权")
        level=body.get("access")
        if level not in ("view","edit","none"):raise ValueError("未知权限")
        with store.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            target=c.execute("SELECT role FROM accounts WHERE name=?",(actor,)).fetchone()
            if not target or target["role"]=="root":raise HTTPException(409,"请选择已有的非 root 账号")
            c.execute("DELETE FROM panel_grants WHERE actor=?",(actor,))
            if level!="none":c.execute("INSERT INTO panel_grants VALUES (?,?)",(actor,level))
            audit(c,user["name"],"panel_grant",actor,{"access":level})
        return {"ok":True}
