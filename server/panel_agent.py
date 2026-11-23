"""Root-owned local service for one Aetherloom Nginx site."""
import json
import os
from pathlib import Path
import re
import secrets
import socket
import ssl
import subprocess
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from aetherloom.panel_entry import validate_entry

SITE=Path("/etc/nginx/sites-available/aetherloom-https")
STATE=Path("/var/lib/aetherloom-panel/state.json")
SOCKET=Path("/run/aetherloom-panel/control.sock")


def write(path,data):
    temporary=path.with_suffix(".next")
    temporary.write_text(data,encoding="utf8")
    os.chmod(temporary,0o600)
    os.replace(temporary,path)


def save(state):
    write(STATE,json.dumps(state))


def initialize():
    if STATE.exists():return json.loads(STATE.read_text())
    prefix,sep,panel=SITE.read_text().rpartition("\nserver {")
    if not sep:raise ValueError("无法识别已部署的面板配置")
    port=re.search(r"listen (\d+) ssl;",panel)[1]
    domain=re.search(r"server_name ([^ ;]+);",panel)[1]
    path=re.search(r"location = /([a-zA-Z0-9]{16}) ",panel)[1]
    current=validate_entry(dict(address="0.0.0.0",port=int(port),domain=domain,path=path,icp=""))
    if "location ^~ /api/panel/" not in prefix:
        prefix=prefix.replace(" location /api/ {"," location ^~ /api/panel/ { return 404; }\n location /api/ {",1)
    state={"base":prefix,"current":current}
    STATE.parent.mkdir(mode=0o700,exist_ok=True)
    apply(state)
    save(state)
    return state


def block(entry,proof,locations_only=False):
    domain,route,port=entry["domain"],entry["path"],entry["port"]
    cert=f"/etc/letsencrypt/live/{domain}"
    location=f"""
 location = /{route} {{ return 302 /{route}/; }}
 location = /{route}/api/login {{ limit_req zone=aetherloom_login burst=5 nodelay; limit_req_status 429; proxy_pass http://127.0.0.1:8765/api/login; }}
 location ^~ /{route}/ {{ proxy_set_header X-Aetherloom-Entry "{proof}"; proxy_pass http://127.0.0.1:8765/; proxy_read_timeout 120s; }}
"""
    if locations_only:return location
    return f"""
server {{
 listen {entry['address']}:{port} ssl;
 server_name {domain};
 ssl_certificate {cert}/fullchain.pem;
 ssl_certificate_key {cert}/privkey.pem;
 ssl_protocols TLSv1.2 TLSv1.3;
 server_tokens off;
 access_log off;
 error_log /var/log/nginx/aetherloom-panel-error.log crit;
 client_max_body_size 8m;
 add_header Strict-Transport-Security "max-age=31536000" always;
 {location}
 location / {{ return 404; }}
}}
"""


def render(state):
    current=state["current"]
    output=block(current,"")
    if "pending" in state:
        candidate=state["pending"]
        proof=state["proof"]
        if all(current[k]==candidate[k] for k in ("address","domain","port")):
            if current["path"]==candidate["path"]:
                output=block(candidate,proof)
            else:
                output=output.replace(" location / {",block(candidate,proof,True)+" location / {")
        else:
            output+=block(candidate,proof)
    return state["base"]+output


def apply(state):
    old=SITE.read_text()
    write(SITE,render(state))
    try:
        for command in (["nginx","-t"],["systemctl","reload","nginx"]):
            subprocess.run(command,check=True,capture_output=True,timeout=10)
    except Exception:
        write(SITE,old)
        subprocess.run(["systemctl","reload","nginx"],capture_output=True,timeout=10)
        raise ValueError("Nginx 检查或应用失败，已恢复原入口") from None


def handle(state,request):
    op=request["operation"]
    if op=="read":return {k:state[k] for k in ("current","pending","expires") if k in state}
    if op=="stage":
        if "pending" in state:raise ValueError("已有待确认入口")
        candidate=validate_entry(request["settings"])
        cert=Path("/etc/letsencrypt/live")/candidate["domain"]/"fullchain.pem"
        subprocess.run(["openssl","verify","-verify_hostname",candidate["domain"],"-untrusted",str(cert.parent/"chain.pem"),str(cert.parent/"cert.pem")],capture_output=True,timeout=5,check=True)
        next_state=dict(state,pending=candidate,proof=secrets.token_hex(24),expires=time.time()+180)
        save(next_state)
        try:apply(next_state)
        except Exception:
            save(state)
            raise
    elif op=="confirm":
        if not state.get("proof") or time.time()>=state["expires"] or not secrets.compare_digest(request.get("proof",""),state["proof"]):
            raise ValueError("请在新入口登录并确认")
        next_state={"base":state["base"],"current":state["pending"]}
        apply(next_state)
        save(next_state)
    else:raise ValueError("无效操作")
    state.clear()
    state.update(next_state)
    return {"ok":True}


def main():
    os.umask(0o077)
    state=initialize()
    if "pending" in state:
        state={"base":state["base"],"current":state["current"]}
        apply(state)
        save(state)
    SOCKET.parent.mkdir(mode=0o755,exist_ok=True)
    SOCKET.unlink(missing_ok=True)
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as listener:
        listener.bind(str(SOCKET))
        os.chown(SOCKET,10001,-1)
        os.chmod(SOCKET,0o600)
        listener.listen(8)
        listener.settimeout(1)
        while True:
            if state.get("expires",float("inf"))<=time.time():
                stable={"base":state["base"],"current":state["current"]}
                apply(stable)
                save(stable)
                state=stable
            try:client,_=listener.accept()
            except TimeoutError:continue
            with client:
                client.settimeout(2)
                try:reply=handle(state,json.loads(client.makefile("rb").readline(8192)))
                except Exception as error:reply={"error":str(error) if type(error)==ValueError else "面板配置验证失败"}
                try:client.sendall(json.dumps(reply).encode()+b"\n")
                except OSError:pass

if __name__=="__main__":main()
