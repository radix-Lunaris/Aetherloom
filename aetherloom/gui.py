"""CustomTkinter desktop; worker results are dispatched exclusively on the UI thread."""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox
import urllib.error
import urllib.request
import customtkinter as ctk
import asyncio
from .launcher import launch, inside, game_uuid
from . import __version__
from .runtime import find_runtimes, required_java, choose_java, compatibility, inspect_java,launch_compatibility
from .environment import describe, encode, validate
from .environment import authentication,validate_account,decode
from .game_accounts import GameAccounts
from .network_status import probe_nat,human_bytes
from .diagnostics import setup, logger, safe, event

BG="#101116"
SIDE="#17181F"
CARD="#1B1D27"
BORDER="#2B2D3B"
TEXT="#F0F0F6"
MUTED="#9698AD"
ACCENT="#A69BFF"
PRIMARY="#7564E8"

class Settings:
    def __init__(self,directory=None):
        self.path=Path(directory or os.environ.get("AETHERLOOM_CONFIG_DIR") or
            Path(os.environ.get("LOCALAPPDATA",Path.home()/".config"))/"Aetherloom")/"settings.json"
        self.data={}
        if self.path.exists():
            try:self.data=json.loads(self.path.read_text(encoding="utf-8"))
            except (OSError,ValueError):pass
        elif sys.platform=="win32" and directory is None and not os.environ.get("AETHERLOOM_CONFIG_DIR"):
            # Read-only migration from the previous Qt registry settings.
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r"Software\Aetherloom\Desktop") as k:
                    for name in ("root","run","java","name","version","memory","url","username"):
                        try:self.data[name]=winreg.QueryValueEx(k,name)[0]
                        except OSError:pass
            except OSError:pass

    def save(self,data):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temp=self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
        os.replace(temp,self.path)
        self.data=data

class Window(ctk.CTk):
    def __init__(self,config_dir=None):
        super().__init__()
        self.title("Aetherloom")
        self.geometry("1160x790")
        self.minsize(1040,730)
        self.configure(fg_color=BG)
        self.settings=Settings(config_dir)
        setup(self.settings.path.parent/"logs")
        self.events=queue.Queue()
        self.room_rows={}
        self.room_items={}
        self.rooms_busy=False
        self.refresh_failures=0
        self.network_rows={}
        self.session_info={}
        self.transfer_active=False
        self.transfer_operation=''
        self.transfer_percent=0.
        self.selected_room=self.settings.data.get("selected_room", "")
        self.presence_device=__import__('secrets').token_hex(16);self.presence_busy=False;self.presence_retry=0;self.presence_last=0;self.room_presence={}
        self.profiles=self.settings.data.get("local_profiles", {})
        self.profile_key=None
        self.java_busy=False
        self.java_scan=0
        self.java_download_cancel=None
        self.java_choices={}
        self.java_choice=tk.StringVar()
        self.java_directory=self.settings.path.parent/'java'
        self.pending=0
        self.process=None
        self.token=""
        self.server_url=""
        self.page="home"
        self.logs=[]
        self.launching=False
        self.login_busy=False
        self.shared=None
        self.cloud_user=''
        self.cloud_role=''
        data=self.settings.data
        self.bindings=data.get('room_bindings',{})
        for binding in self.bindings.values():
            if isinstance(binding,dict):binding.setdefault('java_mode','auto')
        self.auto_run=data.get('auto_run_path','')
        saved_java=data.get("java","")
        self.values={key:tk.StringVar(value=str(data.get(key,default))) for key,default in
            [("root",""),("run",""),("name","Player"),("version","尚未选择"),("memory",4096),
             ("url","https://artherlink.superyk7hero.online:47192"),("username",""),("uuid",""),("java_mode","auto"),("control_backend","bridge"),("game_account","")]}
        self.game_accounts=GameAccounts(self.settings.path.parent)
        self.offline_identity=('Player','')
        if self.values['url'].get().rstrip('/').lower() in ('https://artherlink.superyk7hero.online','https://artherlink.superyk7hero.online:443'):
            self.values['url'].set('https://artherlink.superyk7hero.online:47192')
        self.values["java"]=tk.StringVar(value=saved_java if saved_java and Path(saved_java).is_file() else "")
        self.password=tk.StringVar()
        self.grid_rowconfigure(0,weight=1)
        self.grid_columnconfigure(1,weight=1)
        self.sidebar=ctk.CTkFrame(self,width=216,corner_radius=0,fg_color=SIDE)
        self.sidebar.grid(row=0,column=0,sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(8,weight=1)
        self.label(self.sidebar,"A",size=30,color=ACCENT,bold=True).grid(row=0,column=0,sticky="w",padx=28,pady=(30,4))
        self.label(self.sidebar,"Aetherloom",size=21,bold=True).grid(row=1,column=0,sticky="w",padx=28)
        self.label(self.sidebar,"让世界，继续。",size=12,color=MUTED).grid(row=2,column=0,sticky="w",padx=28,pady=(4,34))
        self.nav={}
        for row,(key,title) in enumerate([("home","开始游戏"),("instance","本地游戏"),("cloud","共享世界"),("network","联机状态"),("logs","运行记录")],3):
            b=ctk.CTkButton(self.sidebar,text=title,anchor="w",width=176,height=44,
                corner_radius=8,fg_color="transparent",hover_color="#252633",
                text_color=MUTED,font=self.font(14),command=lambda k=key:self.show(k))
            b.grid(row=row,column=0,padx=20,pady=4)
            self.nav[key]=b
        foot=ctk.CTkFrame(self.sidebar,fg_color="#20212D",corner_radius=10)
        foot.grid(row=9,column=0,padx=20,pady=(20,14),sticky="ew")
        self.label(foot,"游戏身份",size=12,color=ACCENT).pack(anchor="w",padx=14,pady=(12,2))
        self.identity=self.label(foot,self.values["name"].get(),size=14,bold=True)
        self.identity.pack(anchor="w",padx=14,pady=(0,12))
        self.label(self.sidebar,'v'+__version__,size=11,color="#696C81").grid(row=10,column=0,sticky="w",padx=28,pady=(0,24))
        self.body=ctk.CTkFrame(self,fg_color=BG,corner_radius=0)
        self.body.grid(row=0,column=1,sticky="nsew",padx=34,pady=28)
        self.body.grid_columnconfigure(0,weight=1)
        self.body.grid_rowconfigure(2,weight=1)
        self.top=ctk.CTkFrame(self.body,fg_color="transparent")
        self.top.grid(row=0,column=0,sticky="ew",pady=(0,18))
        self.breadcrumb=self.label(self.top,"工作台  /  开始游戏",size=12,color=MUTED)
        self.breadcrumb.pack(side="left")
        self.connection=self.label(self.top,"●  本地模式",size=12,color=ACCENT)
        self.connection.pack(side="right")
        self.build_transfer_progress()
        self.pages={}
        for name in self.nav:
            frame=ctk.CTkFrame(self.body,fg_color="transparent")
            frame.grid(row=2,column=0,sticky="nsew")
            self.pages[name]=frame
        self.notice=self.label(self.body,"就绪",size=12,color=MUTED)
        self.notice.grid(row=3,column=0,sticky="w",pady=(12,0))
        self.build_home()
        self.build_instance()
        self.build_cloud()
        self.build_network()
        self.build_logs()
        self.load_versions(silent=True)
        self.show("home")
        self.after(5000,self.auto_refresh)
        self.protocol("WM_DELETE_WINDOW",self.close)
        self.after(100,self.drain)
        self.after(1000,self.poll_game)

    def font(self,size=14,bold=False):
        return ctk.CTkFont(family="Microsoft YaHei" if os.name=="nt" else "sans-serif",size=size,weight="bold" if bold else "normal")

    def label(self,parent,text,size=14,color=TEXT,bold=False,**kw):
        return ctk.CTkLabel(parent,text=text,font=self.font(size,bold),text_color=color,anchor="w",**kw)

    def button(self,parent,text,command,primary=False,**kw):
        return ctk.CTkButton(parent,text=text,command=command,height=40,corner_radius=8,
            fg_color=PRIMARY if primary else "#2A2C3B",hover_color="#8878F0" if primary else "#36394B",
            text_color="#FFFFFF" if primary else TEXT,font=self.font(13,primary),**kw)

    def card(self,parent,**kw):
        return ctk.CTkFrame(parent,fg_color=CARD,border_color=BORDER,border_width=1,corner_radius=12,**kw)

    def entry(self,parent,key,placeholder=""):
        return ctk.CTkEntry(parent,textvariable=self.values[key],height=40,
            fg_color="#13151D",border_color=BORDER,border_width=1,corner_radius=7,
            text_color=TEXT,placeholder_text=placeholder,font=self.font(13))

    def heading(self,parent,title,subtitle):
        self.label(parent,title,26,bold=True).pack(anchor="w")
        self.label(parent,subtitle,13,MUTED).pack(anchor="w",pady=(4,20))

    def build_home(self):
        p=self.pages["home"]
        self.heading(p,"开始你的下一段旅程","离线进入游戏主菜单，在线接续选中的共享世界。")
        hero=self.card(p,height=206)
        hero.pack(fill="x",pady=(0,18))
        hero.pack_propagate(False)
        self.label(hero,"YOUR NEXT CHAPTER",11,ACCENT,True).pack(anchor="w",padx=26,pady=(24,4))
        self.label(hero,"世界，在此延续。",32,bold=True).pack(anchor="w",padx=26)
        self.label(hero,"用熟悉的离线身份，开启今天的冒险。",14,MUTED).pack(anchor="w",padx=26,pady=(8,14))
        self.button(hero,"配置游戏实例  →",lambda:self.show("instance"),width=152).pack(anchor="w",padx=26)
        row=ctk.CTkFrame(p,fg_color="transparent")
        row.pack(fill="x",pady=(0,18));row.grid_columnconfigure((0,1),weight=1)
        left=self.card(row);left.grid(row=0,column=0,sticky="nsew",padx=(0,8))
        self.label(left,"当前实例",12,MUTED).pack(anchor="w",padx=20,pady=(18,6))
        self.instance_title=self.label(left,"尚未绑定",19,bold=True)
        self.instance_title.pack(anchor="w",padx=20)
        self.instance_hint=self.label(left,"到本地游戏中选择 .minecraft 目录",12,MUTED)
        self.instance_hint.pack(anchor="w",padx=20,pady=(5,18))
        right=self.card(row);right.grid(row=0,column=1,sticky="nsew",padx=(8,0))
        self.label(right,"软件连接",12,MUTED).pack(anchor="w",padx=20,pady=(18,6))
        self.home_connection=self.label(right,"本地模式",19,bold=True)
        self.home_connection.pack(anchor="w",padx=20)
        self.button(right,"连接共享世界  →",lambda:self.show("cloud"),width=160).pack(anchor="w",padx=20,pady=(10,16))
        bottom=self.card(p);bottom.pack(fill="x")
        info=ctk.CTkFrame(bottom,fg_color="transparent");info.pack(side="left",padx=22,pady=20)
        self.game_state=self.label(info,"准备就绪",17,bold=True);self.game_state.pack(anchor="w")
        self.game_detail=self.label(info,"先选择一个完整的本地游戏实例",12,MUTED);self.game_detail.pack(anchor="w",pady=(4,0))
        self.start=self.button(bottom,"离线启动   →",self.start_game,primary=True,width=130)
        self.start.pack(side="right",padx=12,pady=20)
        self.online=self.button(bottom,"在线启动   →",self.start_online,primary=True,width=130)
        self.online.pack(side="right",padx=8,pady=20)
        self.selected_hint=self.label(p,"在线实例：尚未选择，请到共享世界选择",12,MUTED)
        self.selected_hint.pack(anchor="w",pady=(8,0))

    def build_instance(self):
        p=self.pages["instance"]
        self.heading(p,"本地游戏环境","只访问你选定的目录；已有游戏文件原地使用。")
        scroll=ctk.CTkScrollableFrame(p,fg_color="transparent")
        scroll.pack(fill="both",expand=True)
        scroll.grid_columnconfigure(0,weight=1)
        c=self.card(scroll);c.grid(row=0,column=0,sticky="ew",pady=(0,16));c.grid_columnconfigure(0,weight=1)
        self.label(c,"游戏实例",17,bold=True).grid(row=0,column=0,sticky="w",padx=22,pady=(18,10))
        self.path_row(c,1,"游戏根目录","root",False)
        self.label(c,"本地实例 / 版本管理 · Beta",12,MUTED).grid(row=3,column=0,sticky="w",padx=22,pady=(14,6))
        vr=ctk.CTkFrame(c,fg_color="transparent");vr.grid(row=4,column=0,sticky="ew",padx=22,pady=(0,22));vr.grid_columnconfigure(0,weight=1)
        self.version_menu=ctk.CTkOptionMenu(vr,variable=self.values["version"],values=["尚未选择"],height=40,
            fg_color="#282A3A",button_color="#373A50",button_hover_color="#474B66",font=self.font(13),
            command=lambda _:self.select_version())
        self.version_menu.grid(row=0,column=0,sticky="ew")
        self.button(vr,"刷新版本",self.load_versions,width=100).grid(row=0,column=1,padx=(12,0))
        c=self.card(scroll);c.grid(row=1,column=0,sticky="ew",pady=(0,16));c.grid_columnconfigure(0,weight=1)
        self.label(c,"启动参数",17,bold=True).grid(row=0,column=0,sticky="w",padx=22,pady=(18,10))
        row=ctk.CTkFrame(c,fg_color="transparent");row.grid(row=1,column=0,sticky="ew",padx=22,pady=(0,12));row.grid_columnconfigure((0,1),weight=1)
        for col,key,title in [(0,"name","玩家名称"),(1,"memory","最大内存 / MiB")]:
            f=ctk.CTkFrame(row,fg_color="transparent");f.grid(row=0,column=col,sticky="ew",padx=(0,10) if col==0 else (10,0))
            self.label(f,title,12,MUTED).pack(anchor="w",pady=(0,6))
            widget=self.entry(f,key);widget.pack(fill='x')
            if key=='name':self.game_name_entry=widget
        self.label(c,'自定义 UUID · 可选，留空按名称生成；修改后须重新绑定共享房间',12,MUTED).grid(row=2,column=0,sticky='w',padx=22,pady=(10,6))
        self.game_uuid_entry=self.entry(c,'uuid');self.game_uuid_entry.grid(row=3,column=0,sticky='ew',padx=22)
        modes=ctk.CTkFrame(c,fg_color='transparent');modes.grid(row=4,column=0,sticky='ew',padx=22,pady=(18,8))
        for text,value in [('自动选择合适的 Java','auto'),('手动指定 Java','manual')]:
            ctk.CTkRadioButton(modes,text=text,value=value,variable=self.values['java_mode'],font=self.font(13),fg_color=PRIMARY,command=self.java_mode_changed).pack(side='left',padx=(0,28))
        self.java_hint=self.label(c,'正在准备 Java 检测',12,MUTED,wraplength=650)
        self.java_hint.grid(row=5,column=0,sticky='w',padx=22,pady=6)
        self.path_row(c,6,'当前 Java 可执行文件','java',True)
        self.java_menu=ctk.CTkOptionMenu(c,values=['尚未检测'],variable=self.java_choice,fg_color=CARD,button_color=PRIMARY,command=self.choose_java_candidate,dynamic_resizing=False)
        self.java_menu.grid(row=8,column=0,sticky='ew',padx=22,pady=8)
        actions=ctk.CTkFrame(c,fg_color='transparent');actions.grid(row=9,column=0,sticky='ew',padx=22,pady=8)
        self.button(actions,'重新检测 Java',self.detect_java,width=135).pack(side='left',padx=(0,10))
        self.java_download_button=self.button(actions,'下载推荐 Java',self.download_java,width=170)
        self.java_download_button.pack(side='left')
        self.label(c,'从系统、注册表、用户 .jdks、游戏及启动器运行时目录发现；不读取其他启动器账号。',11,MUTED,wraplength=650).grid(row=10,column=0,sticky='w',padx=22,pady=6)
        self.path_row(c,11,'运行目录 · 自动识别版本隔离，可手动修改','run',False)
        ctk.CTkCheckBox(c,text='优先使用 Agent · 默认自动按实例选择联机控制',variable=self.values['control_backend'],onvalue='agent',offvalue='bridge',command=self.save).grid(row=13,column=0,sticky='w',padx=22,pady=12)
        self.button(c,'保存配置',self.save,primary=True,width=120).grid(row=14,column=0,sticky='e',padx=22,pady=20)
        self.build_game_accounts(scroll)
        self.build_worlds(scroll)

    def build_worlds(self,scroll):
        card=self.card(scroll);card.grid(row=3,column=0,sticky='ew',pady=(0,16));card.grid_columnconfigure(0,weight=1)
        self.label(card,'本地存档 · 自动识别',17,bold=True).grid(row=0,column=0,sticky='w',padx=22,pady=(18,8))
        self.world_menu=ctk.CTkOptionMenu(card,values=['尚未选择运行目录'],fg_color=CARD,button_color=PRIMARY,command=self.select_world)
        self.world_menu.grid(row=1,column=0,sticky='ew',padx=22,pady=8)
        self.world_hint=self.label(card,'仅检测当前运行目录的saves；游戏运行时暂停，不扫描区块文件。',12,MUTED,wraplength=650)
        self.world_hint.grid(row=2,column=0,sticky='w',padx=22,pady=8)
        self.button(card,'发布选中存档',lambda:self.create_room(world_path=self.world_choices.get(self.world_menu.get(),{}).get('path')),True,width=160).grid(row=3,column=0,sticky='e',padx=22,pady=(8,20))
        self.world_choices={};self.world_generation=0;self.world_scan_key=None
        self.after(15000,self.auto_worlds)

    def auto_worlds(self):
        self.maybe_refresh_worlds();self.after(15000,self.auto_worlds)

    def maybe_refresh_worlds(self):
        run=self.values['run'].get().strip() or self.values['root'].get().strip()
        try:signature=(run,(Path(run)/'saves').stat().st_mtime_ns)
        except OSError:signature=(run,None)
        if signature!=self.world_scan_key:self.refresh_worlds()

    def refresh_worlds(self):
        if self.shared or self.process and self.process.poll() is None:return
        run=self.values['run'].get().strip() or self.values['root'].get().strip()
        if not run or not hasattr(self,'world_menu'):return
        try:self.world_scan_key=(run,(Path(run)/'saves').stat().st_mtime_ns)
        except OSError:self.world_scan_key=(run,None)
        self.world_generation+=1;generation=self.world_generation
        from .worlds import discover
        def done(worlds):
            if generation!=self.world_generation:return
            old=self.world_menu.get();self.world_choices={}
            for world in worlds:
                title=(world.get('world_name') or world['folder'])+' · '+(world.get('game_version') or '版本未知')+' · '+world['folder']
                if world['error']:title+=' · 损坏/不可读'
                self.world_choices[title]=world
            self.world_menu.configure(values=list(self.world_choices) or ['当前运行目录没有存档'])
            self.world_menu.set(old if old in self.world_choices else next(iter(self.world_choices),'当前运行目录没有存档'))
            self.select_world(self.world_menu.get())
        self.task(lambda:discover(run),done)

    def select_world(self,label):
        world=self.world_choices.get(label)
        if not world:self.world_hint.configure(text='当前运行目录没有检测到存档；可在共享世界发布时手动定位。');return
        detail=world['error'] or ' · '.join((world.get('gametype',''),world.get('difficulty',''),'极限' if world.get('hardcore') else '普通世界'))
        if world.get('last_played'):
            try:detail+=' · 最近游玩 '+time.strftime('%Y-%m-%d %H:%M',time.localtime(world['last_played']))
            except (ValueError,OSError,OverflowError):pass
        self.world_hint.configure(text=world['path']+'\n'+detail)

    def build_game_accounts(self,scroll):
        card=self.card(scroll);card.grid(row=2,column=0,sticky='ew',pady=(0,16));card.grid_columnconfigure(0,weight=1)
        self.label(card,'Minecraft 游戏账号',17,bold=True).grid(row=0,column=0,sticky='w',padx=22,pady=(18,8))
        self.label(card,'与Aetherloom软件账号独立。LittleSkin使用角色真实UUID，不与旧离线背包按昵称合并。',12,MUTED,wraplength=650).grid(row=1,column=0,sticky='w',padx=22,pady=8)
        self.game_account_menu=ctk.CTkOptionMenu(card,values=['离线游戏账号'],command=self.select_game_account,fg_color=CARD,button_color=PRIMARY)
        self.game_account_menu.grid(row=2,column=0,sticky='ew',padx=22,pady=8)
        row=ctk.CTkFrame(card,fg_color='transparent');row.grid(row=3,column=0,sticky='w',padx=22,pady=(8,20))
        self.button(row,'添加 LittleSkin',self.add_littleskin,width=150).pack(side='left',padx=(0,12))
        self.button(row,'退出所选账号',self.remove_game_account,width=150).pack(side='left')
        self.refresh_game_accounts()

    def refresh_game_accounts(self):
        self.game_choices={'离线游戏账号':''}
        for key in list(self.game_accounts.rows):
            p=self.game_accounts.public(key);self.game_choices['LittleSkin · '+p['name']+' · '+p['id'][:8]]=key
        self.game_account_menu.configure(values=list(self.game_choices))
        key=self.values['game_account'].get()
        self.game_account_menu.set(next((label for label,value in self.game_choices.items() if value==key),'角色未登录，请重新添加'))
        self.game_name_entry.configure(state='disabled' if key else 'normal')
        self.game_uuid_entry.configure(state='disabled' if key else 'normal')

    def select_game_account(self,label):
        if self.shared or self.launching or self.process and self.process.poll() is None:self.note('请先结束游戏再切换账号',True);self.refresh_game_accounts();return
        key=self.game_choices[label];old=self.values['game_account'].get()
        if key:
            p=self.game_accounts.public(key)
            if self.values['uuid'].get() and game_uuid(self.values['name'].get(),self.values['uuid'].get())!=p['id']:
                if not messagebox.askyesno('切换游戏身份','LittleSkin使用角色真实UUID。原离线背包不会自动迁移或合并；共享房间需要重新绑定。继续？',parent=self):self.refresh_game_accounts();return
            if not old:self.offline_identity=(self.values['name'].get(),self.values['uuid'].get())
            self.values['name'].set(p['name']);self.values['uuid'].set(p['id'])
        elif old:
            self.values['name'].set(self.offline_identity[0]);self.values['uuid'].set(self.offline_identity[1])
        self.values['game_account'].set(key);self.save();self.refresh_summary();self.refresh_game_accounts()

    def add_littleskin(self):
        if self.shared or self.launching or self.process and self.process.poll() is None:self.note('请先结束游戏，再更换游戏账号',True);return
        dialog=ctk.CTkToplevel(self);dialog.title('LittleSkin 外置登录');dialog.geometry('520x440');dialog.configure(fg_color=BG);dialog.transient(self)
        self.label(dialog,'LittleSkin 游戏账号',20,bold=True).pack(anchor='w',padx=24,pady=(22,8))
        self.label(dialog,'凭据仅发送给 littleskin.cn，密码不保存；登录令牌使用Windows用户加密。',12,MUTED,wraplength=460).pack(anchor='w',padx=24,pady=8)
        username=ctk.CTkEntry(dialog,placeholder_text='邮箱或角色名',height=38);username.pack(fill='x',padx=24,pady=8)
        password=ctk.CTkEntry(dialog,placeholder_text='LittleSkin密码',show='•',height=38);password.pack(fill='x',padx=24,pady=8)
        role=ctk.CTkOptionMenu(dialog,values=['登录后选择角色'],fg_color=CARD,button_color=PRIMARY);role.pack(fill='x',padx=24,pady=8)
        status=self.label(dialog,'请先在LittleSkin网站创建角色并设置皮肤。',12,MUTED,wraplength=460);status.pack(anchor='w',padx=24,pady=8)
        pending={}
        def failed(error):
            if dialog.winfo_exists():status.configure(text=error);login.configure(state='normal')
        def logged(result):
            if not dialog.winfo_exists():return
            pending['result'],profiles=result;pending['roles']={p['name']+' · '+p['id'][:8]:p for p in profiles}
            role.configure(values=list(pending['roles']));role.set(next(iter(pending['roles'])))
            status.configure(text='登录成功，请选择角色并保存。');login.configure(state='normal');save.configure(state='normal')
        def authenticate():
            user,secret=username.get().strip(),password.get();password.delete(0,'end')
            if not user or not secret:status.configure(text='请输入LittleSkin账号和密码');return
            login.configure(state='disabled');save.configure(state='disabled');pending.clear()
            self.task(lambda:self.game_accounts.login(user,secret),logged,failed)
        def saved(key):
            self.refresh_game_accounts()
            self.select_game_account(next(label for label,value in self.game_choices.items() if value==key));dialog.destroy()
            self.note('LittleSkin角色已添加；共享房间需使用对应认证模式并重新绑定')
        def commit():
            if 'result' not in pending:return
            result=pending['result'];selected=pending['roles'][role.get()]
            save.configure(state='disabled')
            self.task(lambda:self.game_accounts.add(result,selected),saved,failed)
        login=self.button(dialog,'登录',authenticate,True,width=140);login.pack(side='left',padx=24,pady=18)
        save=self.button(dialog,'保存所选角色',commit,width=180);save.pack(side='right',padx=24,pady=18);save.configure(state='disabled')

    def remove_game_account(self):
        key=self.values['game_account'].get()
        if not key:return
        if self.shared or self.launching or self.process and self.process.poll() is None:self.note('请先结束游戏',True);return
        def done(_):self.select_game_account('离线游戏账号');self.refresh_game_accounts();self.note('LittleSkin本地授权已清除，旧房间绑定需重新配置')
        self.task(lambda:self.game_accounts.remove(key),done)

    def check_game_identity(self,binding):
        if binding.get('game_account'):
            p=self.game_accounts.public(binding['game_account'])
            if binding['name']!=p['name'] or game_uuid(binding['name'],binding.get('uuid'))!=p['id']:raise ValueError('LittleSkin角色名称和UUID不能自定义，请重新选择角色')

    def path_row(self,parent,row,title,key,file):
        self.label(parent,title,12,MUTED).grid(row=row,column=0,sticky="w",padx=22,pady=(10,6))
        f=ctk.CTkFrame(parent,fg_color="transparent")
        f.grid(row=row+1,column=0,sticky="ew",padx=22);f.grid_columnconfigure(0,weight=1)
        self.entry(f,key).grid(row=0,column=0,sticky="ew")
        self.button(f,"浏览",lambda:self.pick(key,file),width=72).grid(row=0,column=1,padx=(10,0))

    def build_cloud(self):
        p=self.pages["cloud"]
        self.heading(p,"共享世界","连接你的服务器，查看实例与在线会话。")
        card=self.card(p);card.pack(fill="x",pady=(0,16));card.grid_columnconfigure((0,1),weight=1)
        self.label(card,"服务器连接",17,bold=True).grid(row=0,column=0,sticky="w",padx=22,pady=(18,6))
        self.label(card,"软件账号与游戏中的离线身份相互独立。",12,MUTED).grid(row=1,column=0,columnspan=2,sticky="w",padx=22,pady=(0,8))
        self.label(card,"服务器地址",12,MUTED).grid(row=2,column=0,sticky="w",padx=22)
        self.entry(card,"url").grid(row=3,column=0,columnspan=2,sticky="ew",padx=22,pady=(6,12))
        for col,title in [(0,"软件账号"),(1,"软件密码")]:
            self.label(card,title,12,MUTED).grid(row=4,column=col,sticky="w",padx=22)
        self.entry(card,"username").grid(row=5,column=0,sticky="ew",padx=(22,8),pady=6)
        self.password_entry=ctk.CTkEntry(card,textvariable=self.password,show="•",height=40,
            fg_color="#13151D",border_color=BORDER,font=self.font(13))
        self.password_entry.grid(row=5,column=1,sticky="ew",padx=(8,22),pady=6)
        self.password_entry.bind("<Return>",lambda _:self.login())
        self.cloud_state=self.label(card,"尚未连接",12,MUTED)
        self.cloud_state.grid(row=6,column=0,sticky="w",padx=22,pady=(14,20))
        self.login_button=self.button(card,"登录服务器",self.login,True,width=150)
        self.login_button.grid(row=6,column=1,sticky="e",padx=22,pady=(14,20))
        toolbar=ctk.CTkFrame(p,fg_color="transparent");toolbar.pack(fill="x",pady=(0,10))
        self.label(toolbar,"共享房间",17,bold=True).pack(side="left")
        self.cloud_buttons=[]
        for title,callback in [("发布世界",self.create_room),("账号",self.account_settings)]:
            b=self.button(toolbar,title,callback,width=95);b.pack(side="right",padx=(8,0));b.configure(state="disabled");self.cloud_buttons.append(b)
        self.room_list=ctk.CTkScrollableFrame(p,fg_color=CARD,corner_radius=12,border_width=1,border_color=BORDER)
        self.room_list.pack(fill="both",expand=True)
        self.label(self.room_list,"登录后，这里会显示服务器中的实例。",13,MUTED).pack(padx=20,pady=28)
        self.label(p,"共享房间 = 游戏环境 + 共同存档；本地实例 = 已准备的游戏目录。",11,MUTED).pack(anchor="w",pady=(12,0))

    def build_logs(self):
        p=self.pages["logs"];self.heading(p,"运行记录","查看启动与服务器连接的处理结果。")
        self.logbox=ctk.CTkTextbox(p,fg_color=CARD,border_color=BORDER,border_width=1,
            corner_radius=12,text_color="#C4C7D8",font=self.font(13))
        self.logbox.pack(fill="both",expand=True);self.logbox.configure(state="disabled")
        self.button(p,"清空记录",self.clear_logs,width=100).pack(anchor="e",pady=(12,0))
        self.button(p,'许可与来源',self.show_licenses,width=110).pack(anchor='w',pady=(6,0))

    def show_licenses(self):
        base=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent.parent))
        folder=base/'licenses' if getattr(sys,'frozen',False) else base
        files=sorted(folder.iterdir()) if folder.is_dir() else []
        if not getattr(sys,'frozen',False):files=[p for p in files if p.name in ('LICENSE','THIRD_PARTY.md')]
        dialog=ctk.CTkToplevel(self);dialog.title('许可与来源');dialog.geometry('800x620');dialog.configure(fg_color=BG)
        text=ctk.CTkTextbox(dialog,fg_color=CARD,text_color=TEXT,wrap='word');text.pack(fill='both',expand=True,padx=20,pady=20)
        text.insert('end','Aetherloom · GPLv3\n源代码：https://github.com/radix-Lunaris/Aetherloom\n\n')
        for path in files:
            if path.is_file():text.insert('end','\n=== '+path.name+' ===\n'+path.read_text(encoding='utf-8',errors='replace')+'\n')
        text.configure(state='disabled')

    def show(self,name):
        self.page=name;self.pages[name].tkraise()
        for key,b in self.nav.items():b.configure(fg_color="#302B49" if key==name else "transparent",text_color=ACCENT if key==name else MUTED)
        self.breadcrumb.configure(text="工作台  /  "+{"home":"开始游戏","instance":"本地游戏","cloud":"共享世界","network":"联机状态","logs":"运行记录"}[name])
        self.refresh_summary()

        if name=='network':self.start_nat_probe()

    def refresh_summary(self):
        version=self.values["version"].get()
        self.instance_title.configure(text=(version[:32] if version!="尚未选择" else "尚未绑定"))
        self.instance_hint.configure(text="已选择本地游戏目录" if self.values["root"].get() else "到本地游戏中选择 .minecraft 目录")
        self.identity.configure(text=self.values["name"].get() or "Player")
        if hasattr(self,"selected_hint"):
            selected=self.room_items.get(self.selected_room)
            self.selected_hint.configure(text="在线实例："+(selected.get("name",self.selected_room) if selected else "尚未选择，请到共享世界选择"))
        self.game_detail.configure(text=f"{self.values['name'].get()}  ·  {self.values['memory'].get()} MiB" if version!="尚未选择" else "先选择一个完整的本地游戏实例")

    def note(self,message,error=False):
        message=safe(message)
        self.notice.configure(text=message[:115],text_color="#F0AF9C" if error else MUTED)
        logger.log(40 if error else 20,message)
        line=time.strftime("%H:%M:%S")+("  ERROR  " if error else "  INFO  ")+message
        self.logs.append(line)
        if len(self.logs)>3000:
            del self.logs[:1000]
            self.logbox.configure(state="normal");self.logbox.delete("1.0","1001.0")
        self.logbox.configure(state="normal");self.logbox.insert("end",line+"\n");self.logbox.see("end");self.logbox.configure(state="disabled")

    def clear_logs(self):
        self.logs.clear();self.logbox.configure(state="normal");self.logbox.delete("1.0","end");self.logbox.configure(state="disabled")

    def save(self):
        self.remember_profile()
        try:self.settings.save(dict({k:v.get().strip() for k,v in self.values.items()},room_bindings=self.bindings,auto_run_path=self.auto_run,selected_room=self.selected_room,local_profiles=self.profiles))
        except OSError as e:self.note("配置保存失败："+str(e),True);return False
        self.refresh_summary();self.maybe_refresh_worlds();self.note("配置已保存");return True

    def pick(self,key,file=False):
        value=filedialog.askopenfilename(parent=self,title="选择 Java",filetypes=[("Java","*.exe"),("所有文件","*")]) if file else filedialog.askdirectory(parent=self,title="选择目录",initialdir=self.values[key].get() or None)
        if value:
            self.values[key].set(value)
            if key=="java":self.values["java_mode"].set("manual");self.java_hint.configure(text="已手动指定 Java，启动前会验证版本与架构")
            if key=="root":self.load_versions()
            self.save()
            if key=='java':self.detect_java()

    def load_versions(self,silent=False):
        root=self.values["root"].get().strip()
        if not root:return
        try:
            folder=inside(Path(root),"versions")
            versions=[p.name for p in sorted(folder.iterdir()) if p.is_dir() and (p/(p.name+".json")).is_file()]
            self.version_menu.configure(values=versions or ["尚未选择"])
            if self.values["version"].get() not in versions:self.values["version"].set(versions[0] if versions else "尚未选择")
            self.select_version(save=False)
            self.refresh_summary()
            if not silent:self.note(f"找到 {len(versions)} 个已安装版本")
        except (OSError,ValueError) as e:
            if not silent:self.note("无法读取版本："+str(e),True)

    def suggest_run(self):
        current=self.values['run'].get().strip()
        if current and current!=self.auto_run:return
        root=Path(self.values['root'].get())
        version=self.values['version'].get()
        if not root.is_dir() or version=='尚未选择':return
        selected=inside(root,'versions/'+version)
        isolated=any((selected/name).is_dir() for name in ('mods','saves','config'))
        self.auto_run=str(selected if isolated else root)
        self.values['run'].set(self.auto_run)

    def task(self,fn,done,failed=None):
        self.pending+=1
        def run():
            try:self.events.put((done,fn(),False))
            except Exception as e:self.events.put((failed or self.fail,str(e),True))
        threading.Thread(target=run,daemon=True).start()

    def drain(self):
        while True:
            try:callback,result,_=self.events.get_nowait()
            except queue.Empty:break
            if _!='notification':self.pending-=1
            try:callback(result)
            except Exception as e:self.fail(str(e))
        self.after(100,self.drain)

    def fail(self,message):
        self.note(message,True)

    def start_game(self):
        if self.transfer_active:self.note('请先完成当前传输任务',True);return
        if self.java_busy:self.note('Java 正在安装，请等待完成或取消下载',True);return
        if self.shared or self.launching or (self.process and self.process.poll() is None):return
        if not self.save():return
        try:
            root,version,java,name,run,memory=[self.values[k].get().strip() for k in ("root","version","java","name","run","memory")]
            if not root or (not java and self.values["java_mode"].get()=="manual") or version=="尚未选择":raise ValueError("请先在本地游戏中选择游戏目录、版本和 Java")
            memory=int(memory)
            if not 512<=memory<=65536:raise ValueError("内存范围为 512—65536 MiB")
        except ValueError as e:self.note(str(e),True);self.show("instance");return
        self.launching=True;self.start.configure(state="disabled",text="正在准备…")
        self.game_state.configure(text="正在检查游戏文件")
        def failed(message):
            self.launching=False;self.start.configure(state="normal",text="离线启动   →");self.game_state.configure(text="启动未完成");self.note(message,True)
        custom_uuid=self.values['uuid'].get().strip()
        mode=self.values['java_mode'].get()
        account=self.values['game_account'].get()
        def start():
            from .shared_session import assets
            self.check_game_identity({'game_account':account,'name':name,'uuid':custom_uuid})
            auth=self.game_accounts.refresh(account,name,custom_uuid) if account else None
            selected=self.resolve_java(root,version,java,mode)
            return launch(root,version,selected,name,run or None,memory,custom_uuid=custom_uuid,game_auth=auth,authlib_jar=assets()/'authlib-injector.jar' if auth else None),selected
        def done(result):
            process,selected=result
            if root==self.values['root'].get() and version==self.values['version'].get():
                self.values['java'].set(selected);self.save()
            self.started(process)
        self.task(start,done,failed)

    def started(self,process):
        self.launching=False;self.process=process;self.start.configure(text="游戏运行中")
        self.game_state.configure(text="游戏已启动");self.note(f"游戏进程 {process.pid} 已启动")

    def poll_game(self):
        if self.process and self.process.poll() is not None:
            code=self.process.returncode;self.process=None
            self.start.configure(state="disabled" if self.shared else "normal",text="离线启动   →")
            self.game_state.configure(text="游戏已结束")
            self.note(f"游戏进程结束，返回码 {code}；详细日志在运行目录 .aetherloom/logs")
            self.refresh_worlds()
        self.after(1000,self.poll_game)

    @staticmethod
    def request(url,token,path,body=None):
        if not url.startswith(("http://","https://")):raise ValueError("服务器地址需要以 https:// 开头")
        headers={"Content-Type":"application/json"}
        if token:headers["Authorization"]="Bearer "+token
        request=urllib.request.Request(url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with urllib.request.urlopen(request,timeout=20) as response:return json.load(response)
        except urllib.error.HTTPError as e:
            try:detail=json.load(e).get("detail",str(e))
            except Exception:detail=str(e)
            raise ValueError(str(detail)) from None

    def login(self):
        if self.shared:self.note('共享会话运行期间不能切换软件账号',True);return
        if self.login_busy:return
        url=self.values["url"].get().strip().rstrip("/")
        username=self.values["username"].get().strip()
        password=self.password.get()
        if not username or not password:self.note("请输入软件账号和密码",True);return
        self.save();self.token="";self.login_busy=True
        for b in self.cloud_buttons:b.configure(state="disabled")
        self.login_button.configure(state="disabled",text="正在连接…")
        def done(result):
            self.login_busy=False;self.login_button.configure(state="normal",text="重新登录")
            self.token=result["token"];self.server_url=url;self.password.set("")
            self.cloud_user=result['username'];self.cloud_role=result['role']
            self.cloud_state.configure(text=username+" · "+result["role"],text_color=ACCENT)
            self.connection.configure(text="●  已连接服务器")
            self.home_connection.configure(text="已连接")
            for b in self.cloud_buttons:b.configure(state="normal")
            self.note("服务器登录成功");self.rooms()
        def failed(message):
            self.login_busy=False;self.login_button.configure(state="normal",text="登录服务器")
            self.cloud_state.configure(text="连接未完成",text_color="#F0AF9C")
            self.connection.configure(text="●  本地模式");self.home_connection.configure(text="本地模式");self.note(message,True)
        self.task(lambda:self.request(url,"","/api/login",{"username":username,"password":password}),done,failed)

    def cloud_task(self,path,done,body=None,method=None):
        if not self.token:self.note("请先登录服务器",True);return
        url,token=self.server_url,self.token
        from .cloud import API
        self.task(lambda:API(url,token)(path,body,method=method),done)

    def rooms(self):
        if self.rooms_busy or not self.token:return
        self.rooms_busy=True
        url,token=self.server_url,self.token
        def done(items):
            self.rooms_busy=False
            if token!=self.token or url!=self.server_url:return
            self.refresh_failures=0
            self.room_items={item['id']:item for item in items}
            scroll=self.room_list._parent_canvas.yview()[0]
            for child in self.room_list.winfo_children():
                if not any(child is row[0] for row in self.room_rows.values()):child.destroy()
            for key in set(self.room_rows)-set(self.room_items):
                self.room_rows.pop(key)[0].destroy()
            self.refresh_summary()
            if not items:self.label(self.room_list,"暂无共享房间 · 先配置游戏，再发布一个本地世界。",13,MUTED).pack(pady=30);return
            for item in items:
                signature=json.dumps([item,self.bindings.get(item['id']),bool(self.bindings.get(item['id']) and (Path(self.bindings[item['id']]['world'])/'.aetherloom/pending-session.json').is_file())],sort_keys=True)
                old=self.room_rows.get(item['id'])
                if old and old[1]==signature:continue
                if old:old[0].destroy()
                row=ctk.CTkFrame(self.room_list,fg_color="#232532",corner_radius=8);row.pack(fill="x",padx=8,pady=5)
                self.room_rows[item['id']]=(row,signature)
                top=ctk.CTkFrame(row,fg_color='transparent');top.pack(fill='x',padx=14,pady=(10,4))
                self.label(top,item.get('name') or item['id'][:12],14,bold=True).pack(side='left')
                self.label(top,("Host "+item["host"]) if item.get("host") else "当前无 Host",12,ACCENT).pack(side='right')
                self.label(row,(item.get('environment') or '未设置环境')+' · 所有者 '+item['owner']+' · '+({'idle':'可接管','preparing':'准备中','ready':'可加入','uploading':'上传中'}.get(item['state'],item['state'])),11,MUTED).pack(anchor='w',padx=14)
                bound=self.bindings.get(item['id'])
                if bound:
                    hint=self.label(row,'本机 '+bound['version']+' · '+bound['name']+'\n存档 '+bound['world'],11,MUTED)
                    hint.configure(wraplength=590,justify='left');hint.pack(anchor='w',padx=14,pady=(4,0))
                buttons=ctk.CTkFrame(row,fg_color='transparent');buttons.pack(fill='x',padx=14,pady=10)
                for title,callback in [('在线启动',lambda r=item:self.play_room(r)),('选中',lambda r=item:self.select_room(r)),('绑定目录',lambda r=item:self.bind_room(r)),('成员',lambda r=item:self.room_members(r))]:
                    self.button(buttons,title,callback,width=80).pack(side='left',padx=(0,8))
                bound=self.bindings.get(item['id'])
                if bound and (Path(bound['world'])/'.aetherloom/pending-session.json').is_file():
                    self.button(buttons,'恢复检查',lambda r=item:self.inspect_room(r),width=85).pack(side='left',padx=(0,8))
                if item.get('can_manage') or item['owner']==self.cloud_user or self.cloud_role=='root':
                    if not item.get('head'):
                        self.button(buttons,'上传世界',lambda r=item:self.create_room(r),width=85).pack(side='left',padx=(0,8))
                    self.button(buttons,'管理',lambda r=item:self.manage_room(r),width=70).pack(side='right',padx=(8,0))
                    self.button(buttons,'删除',lambda r=item:self.delete_room(r),width=70).pack(side='right')
            for item in items:
                self.room_rows[item['id']][0].pack_forget()
                self.room_rows[item['id']][0].pack(fill="x",padx=8,pady=5)
            self.room_list.update_idletasks()
            self.room_list._parent_canvas.yview_moveto(scroll)
        def failed(error):
            self.rooms_busy=False;self.refresh_failures=min(self.refresh_failures+1,4)
            event('rooms.refresh.failed',error=error)
        from .cloud import API
        self.task(lambda:API(url,token)('/api/rooms'),done,failed)

    def create_room(self,existing=None,world_path=None):
        if self.transfer_active or self.shared or self.launching or (self.process and self.process.poll() is None):self.note('请先完成当前同步或保存退出游戏',True);return
        binding=self.current_binding()
        if not binding:return
        selected=world_path or self.world_choices.get(self.world_menu.get(),{}).get('path') or filedialog.askdirectory(parent=self,title='选择要发布的世界（包含level.dat）',initialdir=str(Path(binding['run'])/'saves'))
        if not selected:return
        world=Path(selected).resolve()
        if (world/'.aetherloom/pending-session.json').exists():self.note('此世界有未处理的Host会话，请先恢复，禁止重新发布覆盖',True);return
        if not (world/'level.dat').is_file() or world.parent!=Path(binding['run']).resolve()/'saves':
            self.note('请选择当前运行目录 saves 下包含 level.dat 的世界目录',True);return
        binding['world']=str(world)
        from .worlds import level_info,publication_needs_version_confirmation
        from .vanilla_control import name_data_identity
        try:
            metadata=level_info(world/'level.dat');expected=describe(binding['root'],binding['version'])['minecraft']
            confirm_version=publication_needs_version_confirmation(metadata,expected)
            name_data=name_data_identity(binding,expected)
        except (OSError,ValueError,KeyError) as error:self.note('存档检查失败：'+str(error),True);return
        confirmations=[]
        if confirm_version:
            confirmations.append(f'这份旧存档没有发行版本记录。请确认它最后用 {expected} 保存。')
        if name_data:
            confirmations.append(f'如果世界含单人角色数据，请确认归属于离线玩家 {name_data}。')
        if confirmations and not messagebox.askyesno('确认旧版存档','\n'.join(confirmations),parent=self):return
        name=existing.get('name') if existing else ctk.CTkInputDialog(text='共享房间名称',title='发布共同世界').get_input()
        if not name:return
        from .cloud import API,CloudWorld,LeaseGuard
        api=API(self.server_url,self.token)
        self.begin_transfer('publish','准备发布新世界：'+name)
        def progress(state):
            self.events.put((lambda value:self.transfer_status(value),dict(state,operation='publish'),'notification'))
        def publish():
            if binding.get('game_account'):self.game_accounts.refresh(binding['game_account'],binding['name'],binding['uuid'])
            binding['java']=self.resolve_java(binding['root'],binding['version'],binding['java'],binding.get('java_mode','manual'))
            environment=describe(binding['root'],binding['version'])
            if binding.get('game_account'):environment['authentication']='littleskin'
            if existing:
                if existing.get('head'):raise ValueError('已有权威存档，请使用恢复候选审批，不能直接覆盖')
                room=existing['id']
                api('/api/rooms/'+room,dict(name=name,environment=encode(environment),world=world.name),method='PATCH')
            else:room=api('/api/rooms',dict(name=name,environment=encode(environment),world=world.name))['id']
            self.events.put((lambda _:self.note('正在发布 '+name+'，请勿打开此世界'),None,'notification'))
            lease=api('/api/rooms/'+room+'/claim',{})
            guard=LeaseGuard(api,room,lease)
            try:
                from .shared_session import repair
                repair(world,binding['java'],game_uuid(binding['name'],binding.get('uuid')),name_data=name_data,publishing=True)
                version=CloudWorld(api,self.settings.path.parent/'cache',on_progress=progress).upload(room,world,guard.lease,None)
                return room,version
            except Exception:
                # Creation failed before any managed game launch; safe to release.
                try:api('/api/rooms/'+room+'/cancel',guard.lease)
                except Exception:pass
                raise
            finally:guard.close()
        def done(result):
            self.bindings[result[0]]=binding;self.save();self.note('共同存档发布成功');self.rooms()
        def failed(error):self.finish_transfer(False,error);self.note(error,True)
        self.task(publish,done,failed)

    def current_binding(self):
        b={k:self.values[k].get().strip() for k in ('root','run','version','java','name','memory','uuid','java_mode','control_backend','game_account')}
        try:game_uuid(b['name'],b['uuid'])
        except ValueError as e:self.note(str(e),True);return None
        if not b['root'] or (not b['java'] and b['java_mode']=='manual') or b['version']=='尚未选择':
            self.note('先在本地游戏中定位游戏目录、版本和Java',True);self.show('instance');return None
        b['run']=b['run'] or b['root']
        try:self.check_game_identity(b)
        except ValueError as error:self.note(str(error),True);return None
        return b

    def bind_room(self,room):
        b=self.current_binding()
        if not b:return
        try:
            from .game_control import select_backend
            from .vanilla_control import name_data_identity
            environment=describe(b['root'],b['version'])
            validate(environment,room.get('environment'),backend=select_backend(b))
            name_data_identity(b,environment['minecraft'])
            validate_account(b,room.get('environment'))
        except (ValueError,OSError,KeyError) as e:self.note(str(e),True);return
        if not messagebox.askyesno('绑定共享房间',f"将当前本地版本 {b['version']} 绑定到房间 {room.get('name') or room['id']}？\n请确保版本、加载器和Mods与房间环境一致。\n作为Host时会将云端存档校验下载到专用世界目录。",parent=self):return
        target=Path(b['run'])/'saves'/('Aetherloom-'+room['id'])
        if (target/'.aetherloom/pending-session.json').exists():
            import uuid
            target=target.with_name(target.name+'-'+uuid.uuid4().hex[:8])
        b['world']=str(target)
        self.bindings[room['id']]=b;self.selected_room=room['id'];self.save()
        self.cloud_task('/api/rooms/'+room['id']+'/join',lambda _:self.note('本地环境已绑定，可以点击此房间的开始'),{})

    def delete_room(self,room):
        if messagebox.askyesno('删除共享房间','删除 '+(room.get('name') or room['id'])+'？\n本地游戏目录不删除。活动Host必须先正常退出。',parent=self):
            def done(_):self.bindings.pop(room['id'],None);self.save();self.rooms()
            self.cloud_task('/api/rooms/'+room['id'],done,method='DELETE')

    def manage_room(self,room):
        dialog=ctk.CTkToplevel(self);dialog.title('管理共享房间');dialog.geometry('520x540');dialog.configure(fg_color=BG);dialog.transient(self)
        self.label(dialog,room.get('name') or room['id'],19,bold=True).pack(anchor='w',padx=24,pady=(24,12))
        name=ctk.CTkEntry(dialog,height=40,fg_color=CARD,border_color=BORDER);name.insert(0,room.get('name') or room['id']);name.pack(fill='x',padx=24,pady=8)
        mode=ctk.CTkOptionMenu(dialog,values=['AUTO','RELAY','DIRECT'],fg_color=CARD,button_color=PRIMARY,height=38);mode.set(room.get('mode') or 'AUTO');mode.pack(fill='x',padx=24,pady=8)
        login_mode=ctk.CTkOptionMenu(dialog,values=['离线游戏身份','LittleSkin外置登录'],fg_color=CARD,button_color=PRIMARY,height=38)
        login_mode.set('LittleSkin外置登录' if authentication(room.get('environment'))=='littleskin' else '离线游戏身份');login_mode.pack(fill='x',padx=24,pady=8)
        def saved(_):dialog.destroy();self.rooms();self.note('房间配置已更新')
        def save_room():
            body={'name':name.get(),'mode':mode.get()}
            selected='littleskin' if login_mode.get()=='LittleSkin外置登录' else 'offline'
            if selected!=authentication(room.get('environment')):
                if not messagebox.askyesno('变更游戏身份模式','必须先正常结束Host。所有成员需要使用对应账号类型并重新绑定；旧离线UUID与LittleSkin角色UUID可能不同，背包不会自动合并。确认转换？',parent=dialog):return
                environment=decode(room.get('environment'))
                if environment is None:self.note('请先补全房间游戏环境声明',True);return
                environment['authentication']=selected;body['environment']=encode(environment)
            self.cloud_task('/api/rooms/'+room['id'],saved,body,method='PATCH')
        self.button(dialog,'保存名称、连接和账号模式',save_room,True,width=240).pack(anchor='w',padx=24,pady=8)
        self.button(dialog,'审阅并批准恢复候选',lambda:self.review_recovery(room),width=220).pack(anchor='w',padx=24,pady=8)
        if room['owner']==self.cloud_user or self.cloud_role=='root':
            owner=ctk.CTkOptionMenu(dialog,values=[room['owner']],height=38,fg_color=CARD,button_color=PRIMARY);owner.pack(fill='x',padx=24,pady=8)
            self.cloud_task('/api/rooms/'+room['id']+'/account-options',lambda options:owner.winfo_exists() and owner.configure(values=[o['name'] for o in options]))
            self.button(dialog,'转移所有权',lambda:self.cloud_task('/api/rooms/'+room['id'],saved,{'owner':owner.get()},method='PATCH'),width=150).pack(anchor='w',padx=24,pady=8)

    def room_members(self,room):
        if not self.token:return
        from .cloud import API
        api=API(self.server_url,self.token)
        dialog=ctk.CTkToplevel(self);dialog.title('共享房间成员');dialog.geometry('600x480');dialog.configure(fg_color=BG);dialog.transient(self)
        self.label(dialog,'成员与实例权限 · 自动更新',19,bold=True).pack(anchor='w',padx=24,pady=20)
        listing=ctk.CTkScrollableFrame(dialog,fg_color=CARD);listing.pack(fill='both',expand=True,padx=24,pady=(0,12))
        editable=room['owner']==self.cloud_user or self.cloud_role=='root'
        rows={};busy=False
        def change(actor,role):
            self.cloud_task('/api/rooms/'+room['id']+'/members',lambda _:refresh(),{'username':actor,'role':role})
        if editable:
            controls=ctk.CTkFrame(dialog,fg_color='transparent');controls.pack(fill='x',padx=24,pady=(0,20))
            target=ctk.CTkOptionMenu(controls,values=['正在读取账号'],fg_color=CARD,button_color=PRIMARY);target.pack(side='left',padx=4)
            role=ctk.CTkOptionMenu(controls,values=['member','admin'],width=100,fg_color=CARD,button_color=PRIMARY);role.pack(side='left',padx=4)
            self.button(controls,'添加成员',lambda:change(target.get(),role.get()),width=95).pack(side='left',padx=4)
        def load():
            return api('/api/rooms/'+room['id']+'/members'),api('/api/rooms/'+room['id']+'/account-options') if editable else []
        def done(result):
            nonlocal busy
            busy=False
            if not dialog.winfo_exists():return
            members,options=result
            scroll=listing._parent_canvas.yview()[0]
            present={m['actor'] for m in members}
            for key in set(rows)-present:rows.pop(key)[0].destroy()
            for member in members:
                old=rows.get(member['actor'])
                if old and old[1]==member['role']:continue
                if old:old[0].destroy()
                row=ctk.CTkFrame(listing,fg_color='transparent');row.pack(fill='x',pady=8)
                rows[member['actor']]=(row,member['role'])
                self.label(row,member['actor']+' · '+member['role'],13).pack(side='left',padx=8)
                if editable and member['role']!='owner':
                    self.button(row,'移除',lambda a=member['actor']:change(a,'remove'),width=60).pack(side='right',padx=4)
                    self.button(row,'设成员' if member['role']=='admin' else '设管理员',lambda a=member['actor'],r=member['role']:change(a,'member' if r=='admin' else 'admin'),width=85).pack(side='right',padx=4)
            listing.update_idletasks();listing._parent_canvas.yview_moveto(scroll)
            if editable:
                names=[item['name'] for item in options] or ['无可用账号']
                current=target.get();target.configure(values=names)
                target.set(current if current in names else names[0])
        def failed(error):
            nonlocal busy
            busy=False
            if dialog.winfo_exists():self.note(error,True)
        def refresh():
            nonlocal busy
            if not dialog.winfo_exists():return
            if not busy:
                busy=True;self.task(load,done,failed)
        def tick():
            if dialog.winfo_exists():refresh();self.after(5000,tick)
        tick()

    def review_recovery(self,room):
        from .cloud import API
        api=API(self.server_url,self.token);base='/api/rooms/'+room['id']
        def load():return api(base+'/recoveries'),api(base+'/head')
        def done(result):
            candidates,head=result
            if not candidates:self.note('暂无恢复候选');return
            dialog=ctk.CTkToplevel(self);dialog.title('恢复候选审批');dialog.geometry('560x340');dialog.configure(fg_color=BG);dialog.transient(self)
            self.label(dialog,'恢复将创建新版本，并保留当前权威版本。',16,bold=True).pack(anchor='w',padx=24,pady=(24,12))
            self.label(dialog,'活动Host或审批基准变化时服务端会拒绝覆盖。',12,MUTED).pack(anchor='w',padx=24,pady=8)
            labels={c['id'][:12]+' · '+c['actor']+' · 基准 '+str(c['parent'] or '无')[:10]:c['id'] for c in candidates}
            choice=ctk.CTkOptionMenu(dialog,values=list(labels),fg_color=CARD,button_color=PRIMARY);choice.pack(fill='x',padx=24,pady=16)
            def approve():
                if not messagebox.askyesno('批准恢复','确认已经核对候选内容，并用它创建新的权威版本？',parent=dialog):return
                self.cloud_task(base+'/recoveries/'+labels[choice.get()]+'/approve',lambda _:(dialog.destroy(),self.rooms(),self.note('恢复已批准并创建新权威版本')),{'expected_head':head['version']})
            self.button(dialog,'批准恢复',approve,True,width=160).pack(anchor='e',padx=24,pady=16)
        self.task(load,done)

    def account_settings(self):
        if self.shared:self.note('请先结束共享会话，再修改软件账号',True);return
        choice=ctk.CTkInputDialog(text='输入操作：改名 / 改密',title='软件账号设置').get_input()
        if choice not in ('改名','改密'):return
        dialog=ctk.CTkInputDialog(text='输入新名称' if choice=='改名' else '输入新密码（至少6位）',title=choice)
        if choice=='改密':dialog.after(30,lambda:getattr(dialog,'_entry',None) and dialog._entry.configure(show='•'))
        value=dialog.get_input()
        if not value:return
        def done(result):
            if choice=='改名':
                self.cloud_user=result['username'];self.values['username'].set(result['username']);self.save()
                self.cloud_state.configure(text=self.cloud_user+' · '+self.cloud_role)
            else:
                self.token='';self.cloud_state.configure(text='密码已更新，请重新登录')
                self.connection.configure(text='●  本地模式');self.home_connection.configure(text='本地模式')
                for button in self.cloud_buttons:button.configure(state='disabled')
                self.note('密码已修改，原登录已失效，请使用新密码重新登录')
        self.cloud_task('/api/me',done,{'username' if choice=='改名' else 'password':value},method='PATCH')

    def play_room(self,room):
        if self.transfer_active:self.note('请先完成当前传输任务',True);return
        if self.shared or self.launching or (self.process and self.process.poll() is None):self.note('已有游戏或共享任务运行，请先退出',True);return
        if room['id'] not in self.bindings:self.bind_room(room);return
        recovery=False
        if room.get('host') and room['expires']<=time.time():
            recovery=messagebox.askyesno('上一位Host异常离线','上一会话没有完成最终上传。\n是否明确使用最近已确认的云端版本接管？\n旧Host未上传的进度需要随后通过恢复审批处理。',parent=self)
            if not recovery:return
        from .shared_session import SharedSession
        self.start_session(SharedSession,room,recovery)

    def inspect_room(self,room):
        if self.transfer_active:self.note('请先完成当前传输任务',True);return
        if self.shared or self.launching or (self.process and self.process.poll() is None):self.note('请先退出游戏及当前任务',True);return
        if not messagebox.askyesno('离线恢复检查','保留旧Host原始存档，复制一份进行离线检查。\n不开LAN、不占公共Host。正常退出后上传不可变候选，等待Owner或实例管理员审批。\n检查副本需要额外磁盘空间，继续？',parent=self):return
        from .shared_session import OfflineInspection
        self.start_session(OfflineInspection,room)

    def start_session(self,session_type,room,recovery=False):
        if self.java_busy:self.note('Java 正在安装，请等待完成或取消下载',True);return
        def notify(kind,value):
            def apply(_):
                if kind=='process':self.started(value)
                elif kind=='network':self.network_status(value)
                elif kind=='session':self.session_status(value)
                elif kind=='progress':self.transfer_status(value)
                else:self.note(value)
            self.events.put((apply,None,'notification'))
        self.selected_room=room['id'];self.save()
        try:
            self.shared=session_type(self.server_url,self.token,self.settings.path.parent/'cache',room['id'],dict(self.bindings[room['id']]),notify,recovery,game_accounts=self.game_accounts)
        except (ValueError, OSError, KeyError) as error:
            self.note(str(error),True)
            return
        session=self.shared
        self.network_rows.clear()
        self.network_states.clear()
        for key in ('path','ping','peer_ping','speed','traffic','local_links'):self.runtime_values[key].configure(text='—')
        self.start_nat_probe()
        for widget in self.network_list.winfo_children():widget.destroy()
        self.network_empty=self.label(self.network_list,'正在准备会话；连接流在玩家实际接入后出现。',12,MUTED)
        self.network_empty.pack(anchor='w',padx=16,pady=16)
        self.session_status({'room':room['id'],'phase':'preflight','role':'待确认','mode':room.get('mode','AUTO'),'message':'在线启动已提交，正在核验环境和权威版本'})
        self.begin_transfer('online','准备在线会话')
        self.launching=True;self.online.configure(state='disabled',text='在线准备中…');self.start.configure(state='disabled')
        def finished(_):
            self.shared=None;self.launching=False
            if self.transfer_active:self.finish_transfer(self.session_info.get('phase')=='complete','会话已完成' if self.session_info.get('phase')=='complete' else '会话结束，未完成的同步未记为成功')
            self.online.configure(state='normal',text='在线启动   →')
            self.start.configure(state='normal' if not self.process or self.process.poll() is not None else 'disabled',text='离线启动   →')
            self.rooms()
        def failed(error):
            self.session_status(dict(self.session_info,phase='failed',message=error))
            self.finish_transfer(False,error);finished(None);self.note(error,True)
        self.task(lambda:asyncio.run(session.run()),finished,failed)

    def remember_profile(self):
        if self.profile_key:
            self.profiles[self.profile_key]={k:self.values[k].get() for k in ('run','java','memory','name','uuid','java_mode','control_backend','game_account')}

    def select_version(self,save=True):
        self.remember_profile()
        previous=self.profile_key
        self.profile_key=self.values['root'].get()+'|'+self.values['version'].get()
        profile=self.profiles.get(self.profile_key)
        if profile:
            self.values['uuid'].set(profile.get('uuid',''))
            self.values['java_mode'].set(profile.get('java_mode','auto'));self.values['control_backend'].set(profile.get('control_backend','bridge'));self.values['game_account'].set(profile.get('game_account',''))
            for key,value in profile.items():
                if key in self.values:self.values[key].set(value)
        else:
            if previous and previous!=self.profile_key:
                self.values['uuid'].set('');self.values['java_mode'].set('auto');self.values['control_backend'].set('bridge');self.values['game_account'].set('')
            if previous and previous!=self.profile_key or self.values['run'].get()==self.auto_run:self.values['run'].set('')
            self.suggest_run()
        self.refresh_game_accounts()
        self.maybe_refresh_worlds()
        self.detect_java(save=save)
        self.refresh_summary()

    def java_mode_changed(self):
        self.save();self.detect_java(save=False)

    def choose_java_candidate(self,label):
        path=self.java_choices.get(label)
        if not path:return
        self.values['java_mode'].set('manual');self.values['java'].set(path)
        self.save();self.detect_java(save=False)

    def resolve_java(self,root,version,current,mode):
        from .launcher import manifest
        if mode=='manual':
            info=inspect_java(current)
            reason=launch_compatibility(info)
            if reason:raise ValueError(reason)
            return info.path
        required=required_java(manifest(Path(root),version))
        runtimes=find_runtimes(root,self.java_directory,known=[current])
        best=choose_java(runtimes,required)
        if not best:raise ValueError(f'未找到稳定的64位 Java {required}，请在本地游戏点击“下载推荐 Java {required}”')
        return best.path

    def detect_java(self,save=False):
        root,version=self.values['root'].get(),self.values['version'].get()
        if not root or version=='尚未选择':return
        self.java_scan+=1;generation=self.java_scan
        current=self.values['java'].get()
        self.java_hint.configure(text='正在检测已安装 Java 的版本与架构…')
        def discover():
            from .launcher import manifest
            required=required_java(manifest(Path(root),version))
            return required,find_runtimes(root,self.java_directory,known=[current])
        def found(result):
            if generation!=self.java_scan or root!=self.values['root'].get() or version!=self.values['version'].get():return
            required,runtimes=result;best=choose_java(runtimes,required)
            self.java_choices={}
            for info in runtimes:
                reason=compatibility(info,required)
                label=f'{info.version} ({info.bits}位) · {info.source} · '+Path(info.path).parent.parent.name
                if reason:label+=' · 不推荐'
                if label in self.java_choices:label+=' · '+info.path
                self.java_choices[label]=info.path
                event('java.discovered',version=info.version,architecture=info.architecture,source=info.source,path=info.path,reason=reason)
            self.java_menu.configure(values=list(self.java_choices) or ['未找到 Java，可下载推荐版本或手动指定'])
            if self.values['java_mode'].get()=='auto':
                self.values['java'].set(best.path if best else '')
                hint=f'自动选择：Java {best.version} · 64位 · {best.source}' if best else f'需要稳定的64位 Java {required}：未找到，可点击下方一键下载'
            else:
                try:current_path=str(Path(self.values['java'].get()).resolve())
                except (OSError,ValueError):current_path=''
                selected=next((r for r in runtimes if Path(r.path).resolve()==Path(current_path)),None)
                if selected:
                    blocked=launch_compatibility(selected)
                    advice=compatibility(selected,required)
                    hint='手动指定：'+(blocked+'，无法启动' if blocked else (advice+'；仍使用所选 Java 尝试启动' if advice else '版本与架构匹配'))
                else:hint=f'手动指定路径未通过检测；推荐 Java {required} x64，可自行选择其他可用版本'
            self.java_hint.configure(text=hint)
            chosen=next((label for label,path in self.java_choices.items() if path==self.values['java'].get()),'未找到匹配项')
            self.java_choice.set(chosen)
            if not self.java_busy:self.java_download_button.configure(text=f'下载推荐 Java {required}')
            if save:self.save()
        def failed(error):
            if generation!=self.java_scan:return
            self.java_hint.configure(text='Java 检测失败：'+error);self.note(error,True)
        self.task(discover,found,failed)

    def download_java(self):
        if self.java_busy:
            self.java_download_cancel.set();self.java_download_button.configure(text='正在取消…',state='disabled');return
        if self.transfer_active or self.shared or self.launching or self.process and self.process.poll() is None:
            self.note('请先结束游戏及共享会话，再安装运行时',True);return
        root,version=self.values['root'].get(),self.values['version'].get()
        try:
            from .launcher import manifest
            required=required_java(manifest(Path(root),version))
        except (ValueError,OSError,KeyError) as e:self.note(str(e),True);return
        cancel=threading.Event();self.java_download_cancel=cancel;self.java_busy=True
        self.begin_transfer('java',f'准备下载推荐 Java {required}')
        self.java_download_button.configure(text='取消 Java 下载')
        def progress(text):
            self.events.put((lambda message:self.note(message),text,'notification'))
        def install():
            from .java_download import install_runtime
            return install_runtime(required,self.java_directory,progress=progress,cancel=cancel,on_progress=lambda state:self.events.put((lambda value:self.transfer_status(value),state,'notification')))
        def complete():
            self.java_busy=False;self.java_download_cancel=None
            self.java_download_button.configure(state='normal',text=f'下载推荐 Java {required}')
        def done(path):
            complete()
            if root==self.values['root'].get() and version==self.values['version'].get():
                self.values['java_mode'].set('auto');self.values['java'].set(path);self.save();self.detect_java()
            self.finish_transfer(True,'Java 校验与安装完成')
            self.note('Java 安装完成；未修改系统环境变量，可直接启动游戏')
        def failed(error):complete();self.finish_transfer(False,error);self.note(error,True)
        self.task(install,done,failed)

    def select_room(self,room):
        self.selected_room=room['id'];self.save()
        self.note('在线实例已选中：'+room.get('name',room['id']))

    def start_online(self):
        if not self.token:self.show('cloud');self.note('在线启动需要登录软件账号',True);return
        room=self.room_items.get(self.selected_room)
        if not room:self.show('cloud');self.note('请在共享世界选择一个在线实例',True);return
        self.play_room(room)

    def auto_refresh(self):
        self.refresh_presence()
        if self.page=='network':self.start_nat_probe()
        if self.token and not self.login_busy:self.rooms()
        self.after((5000 if self.page in ('cloud','home') else 15000)*2**self.refresh_failures,self.auto_refresh)

    def refresh_presence(self):
        room=self.session_info.get('room') if self.shared else self.selected_room
        if not self.token or not room or room not in self.bindings or self.presence_busy or time.monotonic()<self.presence_retry or time.monotonic()-self.presence_last<8:return
        self.presence_busy=True;token=self.token;url=self.server_url
        def done(result):
            self.presence_busy=False;self.presence_last=time.monotonic()
            if token!=self.token:return
            if isinstance(result,dict) and type(result.get('online'))==int:
                self.room_presence[room]=result['online']
                if self.session_info.get('room')==room:self.runtime_values['room_members'].configure(text=str(result['online'])+'（45秒成员心跳）')
            else:self.presence_retry=time.monotonic()+60
        def work():
            try:result=self.request(url,token,'/api/rooms/'+room+'/presence',dict(device=self.presence_device))
            except Exception:result=None
            self.events.put((done,result,'notification'))
        threading.Thread(target=work,name='Aetherloom room presence',daemon=True).start()

    def build_transfer_progress(self):
        panel=self.card(self.body);panel.grid(row=1,column=0,sticky='ew',pady=(0,12));panel.grid_columnconfigure(0,weight=1)
        self.transfer_label=self.label(panel,'暂无同步任务',12,MUTED)
        self.transfer_label.grid(row=0,column=0,sticky='w',padx=12,pady=(8,3))
        self.transfer_number=self.label(panel,'—',12,ACCENT)
        self.transfer_number.grid(row=0,column=1,sticky='e',padx=12,pady=(8,3))
        self.transfer_bar=ctk.CTkProgressBar(panel,height=8,progress_color=PRIMARY,fg_color=BORDER)
        self.transfer_bar.grid(row=1,column=0,columnspan=2,sticky='ew',padx=12,pady=(0,10));self.transfer_bar.set(0)

    def begin_transfer(self,operation,message):
        self.transfer_operation=operation;self.transfer_active=True;self.transfer_percent=0.
        self.transfer_label.configure(text=message,text_color=MUTED)
        self.transfer_number.configure(text='准备中')
        self.transfer_bar.configure(mode='indeterminate',progress_color=PRIMARY);self.transfer_bar.start()

    def transfer_status(self,state):
        self.transfer_operation=state.get('operation','sync')
        percent=state.get('percent')
        if percent is None:return
        self.transfer_bar.stop();self.transfer_bar.configure(mode='determinate',progress_color=PRIMARY)
        self.transfer_percent=max(0.,min(100.,float(percent)));self.transfer_bar.set(self.transfer_percent/100)
        self.transfer_active=state.get('stage')!='complete'
        title={'publish':'发布世界','upload':'上传世界','download':'下载世界','recovery':'恢复候选','java':'Java下载','online':'在线准备'}.get(self.transfer_operation,'同步')
        detail=state.get('message') or state.get('stage','')
        total=state.get('total',0);done=state.get('done',0)
        if total and state.get('unit')=='bytes':detail+=f' · {done/1024**2:.1f} / {total/1024**2:.1f} MiB'
        elif total:detail+=f' · {done} / {total}'
        self.transfer_label.configure(text=(title+' · '+safe(detail))[:105],text_color=MUTED)
        self.transfer_number.configure(text=f'{self.transfer_percent:.1f}%')

    def finish_transfer(self,success,message):
        self.transfer_bar.stop();self.transfer_bar.configure(mode='determinate',progress_color=PRIMARY if success else '#D48B79')
        if success:self.transfer_percent=100.
        self.transfer_bar.set(self.transfer_percent/100);self.transfer_active=False
        self.transfer_label.configure(text=safe(message)[:105],text_color=MUTED if success else '#F0AF9C')
        self.transfer_number.configure(text='100.0%' if success else f'未完成 · {self.transfer_percent:.1f}%')

    def session_status(self,state):
        self.session_info=dict(state)
        names={'created':'待启动','preflight':'校验环境／权威版本','claiming':'申请Host租约','syncing':'同步存档','connecting':'建立代理','loading':'游戏加载中','ready':'Host就绪／等待玩家','active':'运行中','saving':'保存与断开','uploading':'最终上传','inspection':'离线检查','complete':'正常完成','ended':'已结束','failed':'失败'}
        room=state.get('room','');item=self.room_items.get(room,{})
        details=f"实例：{item.get('name',room)}\n角色：{state.get('role','待确认')} · 策略：{state.get('mode','AUTO')} · 状态：{names.get(state.get('phase'),state.get('phase',''))}"
        details+=f"\n代次：{state.get('epoch') if state.get('epoch') is not None else '待确认'} · LAN端口：{state.get('lan_port') or '尚未就绪'} · 已就绪对端：{state.get('players',0)}"
        if state.get('message'):details+='\n'+safe(state['message'])
        self.network_summary.configure(text=details,text_color='#F0AF9C' if state.get('phase')=='failed' else TEXT)
        self.runtime_values['state'].configure(text=names.get(state.get('phase'),state.get('phase','未启动')))
        self.runtime_values['role'].configure(text=state.get('role','待确认'))
        self.runtime_values['room'].configure(text=item.get('name',room) or '未选择')
        self.runtime_values['players'].configure(text=str(state['world_players']) if state.get('world_players') is not None else '等待游戏上报')
        self.runtime_values['room_members'].configure(text=str(self.room_presence[room])+'（45秒成员心跳）' if room in self.room_presence else '等待成员心跳；已就绪对端 '+str(state.get('players',0)))
        if state.get('phase') in ('failed','ended','complete'):
            self.runtime_values['speed'].configure(text='↑ 0 B/s · ↓ 0 B/s');self.runtime_values['local_links'].configure(text='0')
        event('session.state',**{key:state[key] for key in ('room','role','phase','mode','epoch','players','message') if key in state})
        if self.transfer_operation=='online' and state.get('phase') in ('ready','active'):
            self.finish_transfer(True,'在线会话已就绪')

    def build_network(self):
        p=self.pages['network']
        self.nat_busy=False;self.nat_updated=0
        self.network_states={}
        self.heading(p,'联机状态','显示实际流状态、P2P 打洞与中继回退；控制通道不等于游戏直连。')
        self.network_summary=self.label(p,'尚未启动在线会话。点击在线启动后，将持续显示角色、阶段和LAN状态。',13,MUTED,wraplength=690,justify='left')
        self.network_summary.pack(fill='x',pady=(0,14))
        content=ctk.CTkScrollableFrame(p,fg_color='transparent');content.pack(fill='both',expand=True)
        card=self.card(content);card.pack(fill='x',pady=(0,12));card.grid_columnconfigure(1,weight=1)
        self.runtime_values={}
        titles=[('state','状态'),('role','身份'),('path','通路'),('nat','网络类型'),('inbound','入站可达'),('punch','打洞进度'),('room','房间'),('room_members','房间内在线'),('players','已加入世界'),('local_links','本地连接'),('ping','中转延迟'),('peer_ping','对端延迟'),('speed','实时速度'),('traffic','累计流量'),('public','公网映射'),('scope','测量范围')]
        for index,(key,title) in enumerate(titles):
            self.label(card,title,13,MUTED,bold=True).grid(row=index,column=0,sticky='nw',padx=(16,22),pady=5)
            label=self.label(card,{'state':'未启动','nat':'未检测','inbound':'入站未测','punch':'尚未尝试','scope':'NAT诊断独立于游戏套接字，不替代实际直连验证'}.get(key,'—'),16 if key in ('state','path','punch') else 13,TEXT,bold=True,wraplength=520,justify='left')
            label.grid(row=index,column=1,sticky='w',padx=(0,16),pady=5);self.runtime_values[key]=label
        self.network_list=ctk.CTkFrame(content,fg_color=CARD);self.network_list.pack(fill='x',expand=True)
        self.network_empty=self.label(self.network_list,'尚无连接流。Host等待玩家时无需建立到自身的隧道。',13,MUTED)
        self.network_empty.pack(anchor='w',padx=16,pady=16)

    def network_status(self,state):
        if state.get('channel')=='metrics':
            self.runtime_values['speed'].configure(text='↑ '+human_bytes(state.get('speed_up',0))+'/s · ↓ '+human_bytes(state.get('speed_down',0))+'/s')
            self.runtime_values['traffic'].configure(text='↑ '+human_bytes(state.get('bytes_up',0))+' · ↓ '+human_bytes(state.get('bytes_down',0))+'（载荷，含重传）')
            self.runtime_values['local_links'].configure(text=str(state.get('local_links',0)));return
        if state.get('session_id'):
            self.network_states[state['session_id']]=state
        active=[s for s in self.network_states.values() if s.get('channel')=='data' and s.get('switch_phase')!='ended']
        paths={s.get('active_path') for s in active}
        self.runtime_values['path'].configure(text=' / '.join({'relay':'中继','direct':'P2P直连','reconnecting':'重连中','none':'已关闭'}.get(path,str(path)) for path in sorted(p for p in paths if p)) or '等待连接')
        if state.get('stage'):self.runtime_values['punch'].configure(text=state['stage'])
        for source,key in (('relay_rtt_ms','ping'),('direct_rtt_ms','peer_ping')):
            value=state.get(source)
            if value is not None:self.runtime_values[key].configure(text=f'{value:.1f} ms')
        if self.network_empty.winfo_exists():self.network_empty.pack_forget()
        key=state.get('session_id','network')
        display={k:state[k] for k in ('peer','channel','mode','active_path','relay_ready','direct_ready','switch_phase','last_reason','relay_rtt_ms','direct_rtt_ms','direct_endpoint','attempt','stage') if k in state}
        event('network.state',stream=key,**display)
        if state.get('switch_phase') in ('ended','closed','reset'):
            self.network_states.pop(key,None);row=self.network_rows.pop(key,None)
            if row:row.destroy()
            if not self.network_rows:self.network_empty.pack(anchor='w',padx=16,pady=16)
            return
        if key not in self.network_rows:
            row=self.label(self.network_list,'',12,MUTED,justify='left',wraplength=650)
            row.pack(fill='x',padx=16,pady=10);self.network_rows[key]=row
        titles={'peer':'对端','channel':'通道','mode':'策略','active_path':'当前路径','relay_ready':'中继就绪','direct_ready':'直连验证','switch_phase':'迁移阶段','last_reason':'原因','relay_rtt_ms':'中继 RTT / ms','direct_rtt_ms':'直连 RTT / ms','direct_endpoint':'直连端点','attempt':'打洞轮次','stage':'打洞进度'}
        phases={'relay':'中继','direct':'P2P直连','probing':'探测直连','verifying':'验证直连','reconnecting':'重连中','ended':'已结束','closing':'正在关闭','relay_first':'中继优先','fallback':'回退中继'}
        def shown(k,value):
            if type(value)==bool:return '就绪' if value else '未就绪'
            return phases.get(value,value) if isinstance(value,str) and k in ('active_path','switch_phase','last_reason') else value
        self.network_rows[key].configure(text='流 '+str(key)[:12]+'\n'+'  ·  '.join(titles[k]+'：'+str(shown(k,v)) for k,v in display.items()))

    def start_nat_probe(self):
        if self.nat_busy or self.nat_updated and time.monotonic()-self.nat_updated<300:return
        self.nat_busy=True
        self.runtime_values['nat'].configure(text='测量 NAT 类型中…');self.runtime_values['inbound'].configure(text='测量入站策略中…')
        def apply(result):
            self.nat_busy=False;self.nat_updated=time.monotonic()
            for key in ('nat','inbound','public'):self.runtime_values[key].configure(text=result.get(key,'未测出'))
            sub=result.get('subtype');filtering=result.get('filtering')
            color='#76C8FC' if sub=='cone' and filtering in ('eif','adf','adf_or_eif') else '#F0B667' if sub=='cone' and filtering=='apdf' else '#B7A4FF' if sub in ('sym_easy_inc','sym_easy_dec') else '#EE9696' if sub=='sym_hard' else MUTED
            self.runtime_values['nat'].configure(text_color=color)
            self.runtime_values['scope'].configure(text=result.get('detail','独立诊断套接字'))
        def run():
            try:
                from .vendor.craftlink.stun import default_servers
                from urllib.parse import urlsplit
                servers=None;has_responder=False
                try:
                    health=self.request(self.server_url,'','/health')
                    ports=health.get('stun_ports',[]);host=urlsplit(self.server_url).hostname
                    if host and len(ports)==2 and all(type(p)==int and 1<=p<=65535 for p in ports):
                        servers=[(host,p) for p in ports]+default_servers();has_responder=True
                except Exception:pass
                result=probe_nat(servers=servers)
                if not has_responder:result['detail']=result.get('detail','')+' · 服务器未公布双端口STUN，公共端点可能不支持过滤测试'
            except Exception as error:result={'nat':'未知（检测失败）','inbound':'入站未测','public':'未测出','detail':'诊断失败：'+type(error).__name__+'；不影响中继'}
            self.events.put((apply,result,'notification'))
        threading.Thread(target=run,name='Aetherloom NAT diagnostics',daemon=True).start()

    def server_status(self):
        def done(r):
            self.note(f"服务器：磁盘剩余 {r['disk_free']/1024**3:.2f} GiB / {r['disk_total']/1024**3:.2f} GiB · 账号 {r['accounts']} · 实例 {r['rooms']}")
        self.cloud_task("/api/status",done)

    def close(self):
        if self.shared:
            self.shared.stop=True;self.note('正在结束共享会话并处理保存，请完成后再关闭');return
        if self.pending:self.note("正在处理请求，请稍后再关闭");return
        self.save();self.destroy()

    def destroy(self):
        from .diagnostics import close
        close()
        super().destroy()

def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    window=Window()
    if "--smoke-test" in sys.argv:window.after(1000,window.destroy)
    window.mainloop()

if __name__=="__main__":main()

