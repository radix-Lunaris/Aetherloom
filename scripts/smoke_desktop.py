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
    (version/'test-forge.json').write_text('{"javaVersion":{"majorVersion":17}}')
    ctk.set_appearance_mode('dark')
    (root/'settings').mkdir()
    (root/'settings/settings.json').write_text(json.dumps({'room_bindings':{'legacy':{'java':'old-bundled-path'}}}))
    window=Window(root/'settings');window.withdraw()
    try:
        assert window.bindings['legacy']['java_mode']=='auto'
        assert window.values['control_backend'].get()=='bridge'
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
        with patch.object(window,'resolve_java',return_value=str(root/'java.exe')),patch('aetherloom.gui.launch',return_value=game) as launch:
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
        (alternate/'test-two.json').write_text('{"javaVersion":{"majorVersion":17}}')
        window.values['version'].set('test-two');window.select_version(save=False)
        # Windows runners may expose Temp through a junction or short path;
        # compare the directory identity rather than its display spelling.
        assert Path(window.values['run'].get()).resolve()==alternate.resolve()
        assert window.values['uuid'].get()==''
        window.values['version'].set('test-forge');window.select_version(save=False)
        assert window.values['run'].get()==str(root/'custom-run')
        assert window.values['uuid'].get()=='81f14300-fbc1-4a46-88f0-0d90db478198'
        window.values['control_backend'].set('agent');window.remember_profile()
        assert window.current_binding()['control_backend']=='agent'
        window.values['control_backend'].set('bridge');window.remember_profile()
        wait(window,lambda:window.pending==0)
        # Java detection and installation must remain on workers, preserve
        # manual choices, and switch to the matching stable major in auto mode.
        from aetherloom.runtime import JavaRuntime
        old_java=JavaRuntime(str(root/'old/bin/java.exe'),'17.0.15',17,64,'amd64',source='test')
        wrong_java=JavaRuntime(str(root/'new/bin/java.exe'),'25.0.3',25,64,'amd64',source='test')
        installed=JavaRuntime(str(root/'downloaded/bin/java.exe'),'17.0.21',17,64,'amd64',source='Aetherloom')
        with patch('aetherloom.gui.find_runtimes',return_value=[old_java,wrong_java]) as discovery:
            window.values['java_mode'].set('auto');window.detect_java()
            wait(window,lambda:window.pending==0)
            assert window.values['java'].get()==old_java.path
            label=next(label for label,path in window.java_choices.items() if path==wrong_java.path)
            window.choose_java_candidate(label);wait(window,lambda:window.pending==0)
            assert window.values['java_mode'].get()=='manual'
            assert window.values['java'].get()==wrong_java.path
            def install(major,directory,progress,cancel,on_progress=None):
                assert major==17 and directory==window.settings.path.parent/'java'
                progress('test download progress');return installed.path
            discovery.return_value=[old_java,wrong_java,installed]
            with patch('aetherloom.java_download.install_runtime',side_effect=install):
                window.download_java();wait(window,lambda:window.pending==0)
                assert window.values['java_mode'].get()=='auto'
                assert window.values['java'].get()==installed.path
            def cancelling(major,directory,progress,cancel,on_progress=None):
                assert cancel.wait(5);raise ValueError('Java download cancelled')
            with patch('aetherloom.java_download.install_runtime',side_effect=cancelling):
                window.download_java();window.download_java();wait(window,lambda:window.pending==0)
                assert not window.java_busy and window.values['java'].get()==installed.path
        window.begin_transfer('online','准备在线会话')
        window.session_status({'room':'test-room','role':'Host','phase':'ready','mode':'AUTO','epoch':3,'lan_port':25565,'players':0,'message':'等待其他玩家连接'})
        window.show('network');window.update()
        assert 'Host就绪' in window.network_summary.cget('text')
        assert '25565' in window.network_summary.cget('text') and '已就绪对端：0' in window.network_summary.cget('text')
        assert window.network_empty.winfo_exists() and window.network_empty.winfo_manager()=='pack'
        assert not window.network_rows and not window.transfer_active
        window.transfer_status({'operation':'upload','stage':'transfer','percent':63,'done':2,'total':4,'unit':'bytes'})
        assert window.transfer_number.cget('text')=='63.0%'
        window.finish_transfer(False,'模拟上传失败')
        assert window.transfer_percent==63 and '未完成' in window.transfer_number.cget('text')
        window.transfer_status({'operation':'upload','stage':'complete','percent':100,'message':'提交成功'})
        assert not window.transfer_active and window.transfer_bar.get()==1
        for page in ('home','instance','cloud','network','logs'):window.show(page);window.update()
        before=set(window.winfo_children());window.show_licenses();window.update()
        dialog=next(widget for widget in window.winfo_children() if widget not in before and isinstance(widget,ctk.CTkToplevel))
        text=next(widget for widget in dialog.winfo_children() if isinstance(widget,ctk.CTkTextbox))
        assert 'GPLv3' in text.get('1.0','end');dialog.destroy()
        print('Desktop smoke passed: navigation, installed versions, UI-thread dispatch, launch/exit, login, private settings.')
    finally:window.destroy()
