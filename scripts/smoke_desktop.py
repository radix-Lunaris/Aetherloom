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
        assert window.start.cget('text').startswith('离线启动')
        assert window.online.cget('text').startswith('在线启动')
        assert launch.call_args.kwargs.get('bridge_file') is None
        # Polling must retain existing room widgets and scroll position.
        rooms=[dict(id=str(i),owner='test',name='room '+str(i),environment='1.20.1 Forge 47.4.22',host=None,state='idle',head='v1',expires=0,epoch=0) for i in range(15)]
        with patch('aetherloom.cloud.API.__call__',return_value=rooms):
            window.rooms();wait(window,lambda:window.pending==0)
            window.show('cloud');window.update()
            row=window.room_rows['0'][0]
            window.room_list._parent_canvas.yview_moveto(.5);window.update()
            position=window.room_list._parent_canvas.yview()[0]
            window.rooms();wait(window,lambda:window.pending==0)
            assert window.room_rows['0'][0] is row
            assert abs(window.room_list._parent_canvas.yview()[0]-position)<.01
            window.select_room(rooms[0]);assert 'room 0' in window.selected_hint.cget('text')
        window.values['uuid'].set('81f14300-fbc1-4a46-88f0-0d90db478198')
        window.values['run'].set(str(root/'custom-run'));window.save()
        alternate=root/'game/versions/test-two';(alternate/'mods').mkdir(parents=True)
        (alternate/'test-two.json').write_text('{}')
        window.values['version'].set('test-two');window.select_version(save=False)
        # Windows runners may expose Temp through a junction or short path;
        # compare the directory identity rather than its display spelling.
        assert Path(window.values['run'].get()).resolve()==alternate.resolve()
        assert window.values['uuid'].get()==''
        window.values['version'].set('test-forge');window.select_version(save=False)
        assert window.values['run'].get()==str(root/'custom-run')
        assert window.values['uuid'].get()=='81f14300-fbc1-4a46-88f0-0d90db478198'
        wait(window,lambda:window.pending==0)
        for page in ('home','instance','cloud','network','logs'):window.show(page);window.update()
        print('Desktop smoke passed: navigation, installed versions, UI-thread dispatch, launch/exit, login, private settings.')
    finally:window.destroy()
