"""Per-launch loopback control, isolated by a random capability."""
import json
from pathlib import Path
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class BridgeControl:
    def __init__(self,world,identity,inspect=False):
        self.world=Path(world).resolve();self.identity=identity
        self.token=secrets.token_urlsafe(32)
        self.ready=threading.Event();self.saved=threading.Event();self.stop=False;self.port=None
        self.error=None
        self.poll_count=0
        control=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def reply(self,status,data):
                body=json.dumps(data).encode();self.send_response(status)
                self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)))
                self.end_headers();self.wfile.write(body)
            def authorized(self):
                return secrets.compare_digest(self.headers.get('Authorization',''),'Bearer '+control.token)
            def do_GET(self):
                if not self.authorized():self.reply(403,{});return
                control.poll_count+=1
                self.reply(200,{'stop':control.stop})
            def do_POST(self):
                if not self.authorized():self.reply(403,{});return
                try:
                    length=int(self.headers.get('Content-Length','0'))
                    if not 0<length<=16384:raise ValueError('Invalid size')
                    data=json.loads(self.rfile.read(length))
                    if Path(data['world']).resolve()!=control.world or data['uuid'].replace('-','')!=control.identity.replace('-',''):
                        raise ValueError('Wrong world or identity')
                    if data['event']=='ready':
                        port=int(data['port'])
                        if not ((inspect and port==0) or (not inspect and 1<=port<=65535)):raise ValueError('Invalid port')
                        control.port=port;control.ready.set()
                    elif data['event']=='saved' and control.ready.is_set():control.saved.set()
                    elif data['event']=='error':control.error='游戏Bridge未能准备世界或LAN，请查看游戏日志'
                    else:raise ValueError('Invalid lifecycle event')
                    self.reply(200,{'ok':True})
                except (ValueError,KeyError,TypeError):self.reply(400,{'ok':False})
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.config=self.world/'.aetherloom'/('bridge-'+secrets.token_hex(8)+'.json')
        self.config.parent.mkdir(parents=True,exist_ok=True)
        self.config.write_text(json.dumps({'endpoint':'http://127.0.0.1:'+str(self.server.server_port),
            'token':self.token,'world':str(self.world),'inspect':inspect}),encoding='utf-8')

    def close(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)
        self.config.unlink(missing_ok=True)
