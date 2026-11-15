"""Desktop flow smoke test using temporary paths; never starts a real game."""
from pathlib import Path
import json,sys,tempfile,threading,time
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import customtkinter as ctk
from aetherloom.gui import Window

def wait(window,predicate):
    deadline=time.monotonic()+8
    while not predicate():
        if time.monotonic()>deadline:raise AssertionError('Desktop worker timed out')
        window.update()
        time.sleep(.02)

class Game:
    pid=12345
    exit_code=None
    @property
    def returncode(self):return self.exit_code
    def poll(self):return self.exit_code

with tempfile.TemporaryDirectory() as d:
    root=Path(d);version=root/'game/versions/test-forge';version.mkdir(parents=True)
    (version/'test-forge.json').write_text('{}')
    ctk.set_appearance_mode('dark')
    window=Window(root/'settings');window.withdraw()
    try:
        window.values['root'].set(str(root/'game'))
        window.values['java'].set(str(root/'java.exe'))
        window.values['name'].set('OfflinePlayer')
        window.load_versions(silent=True)
        assert window.values['version'].get()=='test-forge'
        main_thread=threading.get_ident();dispatched=[]
        window.task(lambda:'done',lambda value:dispatched.append((value,threading.get_ident())))
        wait(window,lambda:bool(dispatched))
        assert dispatched==[('done',main_thread)]
        game=Game()
        with patch('aetherloom.gui.launch',return_value=game) as launch:
            window.start_game()
            wait(window,lambda:window.process is game)
            assert launch.call_args.args[3]=='OfflinePlayer'
        game.exit_code=0
        window.poll_game()
        assert window.process is None and window.start.cget('state')=='normal'
        window.values['username'].set('test')
        window.password.set('never-save-this')
        with patch.object(Window,'request',side_effect=lambda url,token,path,body=None:
            {'token':'temporary-token','username':'test','role':'player'} if path=='/api/login' else []),patch('aetherloom.cloud.API.__call__',return_value=[]):
            window.login()
            wait(window,lambda:window.token=='temporary-token' and window.pending==0)
        data=json.loads(window.settings.path.read_text(encoding='utf-8'))
        assert 'password' not in data and 'token' not in data
        assert 'never-save-this' not in window.settings.path.read_text(encoding='utf-8')
        for page in ('home','instance','cloud','logs'):window.show(page);window.update()
        print('Desktop smoke passed: navigation, installed versions, UI-thread dispatch, launch/exit, login, private settings.')
    finally:window.destroy()
