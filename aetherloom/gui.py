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
from .game_accounts import GameAccounts
from .network_status import probe_nat,human_bytes
from .diagnostics import setup, logger, safe, event

# Palette and sizing follow the MCSync desktop design tokens.
BG=("#f4f5f7","#1b1b1f")
CARD=("#ffffff","#24242a")
SIDE=CARD
SURFACE=("#f0f1f4","#2c2c34")
HOVER=("#e6e8ec","#35353f")
BORDER=("#dcdfe5","#3a3a44")
OUTLINE=("#c6cad2","#4a4a56")
TEXT=("#22232a","#ececf1")
SECONDARY=("#565a66","#b0b0bd")
MUTED=("#71757f","#90909a")
ACCENT=("#234fc1","#7aa2ff")
PRIMARY=("#2f6bff","#5b8cff")
PRIMARY_HOVER=("#1f57e0","#7aa2ff")
SELECTED=("#e4ecff","#2b3550")
DANGER=("#c8342b","#ff8580")


def apply_widget_theme():
    theme=ctk.ThemeManager.theme
    theme["CTkFrame"].update(fg_color=CARD,top_fg_color=SURFACE,border_color=BORDER,corner_radius=10)
    theme["CTkLabel"].update(text_color=TEXT)
    theme["CTkEntry"].update(fg_color=SURFACE,border_color=OUTLINE,text_color=TEXT,placeholder_text_color=MUTED,corner_radius=6)
    theme["CTkButton"].update(fg_color=PRIMARY,hover_color=PRIMARY_HOVER,corner_radius=6)
    theme["CTkTextbox"].update(fg_color=SURFACE,border_color=BORDER,text_color=TEXT,corner_radius=6)
    theme["CTkSegmentedButton"].update(fg_color=SURFACE,selected_color=SELECTED,
        selected_hover_color=SELECTED,unselected_color=SURFACE,unselected_hover_color=HOVER,text_color=TEXT)
    for key in ("CTkCheckBox","CTkRadioButton","CTkSwitch","CTkSlider","CTkProgressBar"):
        if key=="CTkProgressBar":
            theme[key].update(fg_color=SURFACE,progress_color=PRIMARY)
        elif key=="CTkSlider":
            theme[key].update(fg_color=SURFACE,progress_color=PRIMARY,button_color=PRIMARY,button_hover_color=PRIMARY_HOVER)
        elif key=="CTkSwitch":
            theme[key].update(fg_color=OUTLINE,progress_color=PRIMARY,button_color=CARD,button_hover_color=HOVER,text_color=TEXT)
        else:
            theme[key].update(fg_color=PRIMARY,hover_color=PRIMARY_HOVER,border_color=OUTLINE,text_color=TEXT)


class ChoiceMenu(ctk.CTkComboBox):
    """MCSync-style inline select backed by CustomTkinter's native menu."""
    def __init__(self, parent, *, values, variable=None, width=160, height=34, command=None, **kwargs):
        super().__init__(parent,values=values,variable=variable,width=width,height=height,command=command,
                         state="readonly",fg_color=SURFACE,border_color=OUTLINE,border_width=1,
                         button_color=OUTLINE,button_hover_color=HOVER,text_color=TEXT,
                         dropdown_fg_color=CARD,dropdown_hover_color=SELECTED,dropdown_text_color=TEXT,
                         corner_radius=6,font=kwargs.get("font",("Microsoft YaHei UI",12)),
                         dropdown_font=("Microsoft YaHei UI",12))

def physical_memory_mib():
    """Return installed and available physical memory from Windows."""
    if os.name != "nt":
        return None
    import ctypes
    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_uint32), ("load", ctypes.c_uint32)] + [
            (key, ctypes.c_uint64) for key in
            ("total", "available", "page_total", "page_available",
             "virtual_total", "virtual_available", "extended_available")]
    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return status.total // (1024**2), status.available // (1024**2)
    return None


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
        apply_widget_theme()
        super().__init__()
        self.title("Aetherloom")
        mark=Path(__file__).with_name("panel")/"mark.ico"
        if os.name=="nt" and mark.is_file():
            self.iconbitmap(default=str(mark))
        self.geometry("1160x790")
        self.minsize(1040,730)
        self.configure(fg_color=BG)
        self.settings=Settings(config_dir)
        self.theme=self.settings.data.get("theme","system")
        ctk.set_appearance_mode(self.theme)
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
            if isinstance(binding,dict):
                binding.setdefault('java_mode','auto')
                binding['control_backend']='agent'
        self.auto_run=data.get('auto_run_path','')
        saved_java=data.get("java","")
        self.values={key:tk.StringVar(value=str(data.get(key,default))) for key,default in
            [("root",""),("run",""),("name","Player"),("version","尚未选择"),("memory",4096),("initial_heap",""),("window_width",""),("window_height",""),("extra_jvm",""),("fullscreen","0"),
             ("url","https://artherlink.superyk7hero.online:47192"),("username",""),("uuid",""),("java_mode","auto"),("control_backend","agent"),("game_account","")]}
        self.values["control_backend"].set("agent")
        self.game_accounts=GameAccounts(self.settings.path.parent)
        self.offline_identity=('Player','')
        self.offline_profiles=dict(data.get("offline_profiles",{}))
        if "offline_profiles" not in data:
            for item in [data,*self.profiles.values(),*self.bindings.values()]:
                if isinstance(item,dict) and item.get("name") and not item.get("game_account"):
                    try:
                        identity=game_uuid(item["name"],item.get("uuid"))
                        self.offline_profiles.setdefault(identity,item["name"])
                    except ValueError:
                        continue
        if self.values['url'].get().rstrip('/').lower() in ('https://artherlink.superyk7hero.online','https://artherlink.superyk7hero.online:443'):
            self.values['url'].set('https://artherlink.superyk7hero.online:47192')
        self.values["java"]=tk.StringVar(value=saved_java if saved_java and Path(saved_java).is_file() else "")
        self.password=tk.StringVar()
        self.grid_rowconfigure(1,weight=1)
        self.grid_columnconfigure(1,weight=1)
        self.top=ctk.CTkFrame(self,fg_color=CARD,corner_radius=0)
        self.top.grid(row=0,column=0,columnspan=2,sticky="ew")
        self.label(self.top,"Aetherloom",18,TEXT,True).pack(side="left",padx=(20,16),pady=12)
        self.breadcrumb=self.label(self.top,"开始游戏",12,MUTED)
        self.breadcrumb.pack(side="left")
        self.sidebar=ctk.CTkFrame(self,width=212,corner_radius=0,fg_color=SIDE)
        self.sidebar.grid(row=1,column=0,sticky="nsew",padx=(0,1))
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0,weight=1)
        self.sidebar.grid_rowconfigure(6,weight=1)
        self.label(self.sidebar,"工作台",12,MUTED,True).grid(row=0,column=0,sticky="w",padx=16,pady=(16,8))
        self.nav={}
        for row,(key,title) in enumerate([("home","开始游戏"),("instance","本地游戏"),("cloud","共享世界"),("network","联机状态"),("logs","运行记录")],1):
            button=ctk.CTkButton(self.sidebar,text=title,anchor="w",height=36,corner_radius=6,
                fg_color="transparent",hover_color=HOVER,text_color=SECONDARY,font=self.font(13),
                command=lambda name=key:self.show(name))
            button.grid(row=row,column=0,sticky="ew",padx=12,pady=3)
            self.nav[key]=button
        foot=ctk.CTkFrame(self.sidebar,fg_color=SURFACE,corner_radius=10)
        foot.grid(row=7,column=0,padx=12,pady=(12,8),sticky="ew")
        self.label(foot,"游戏身份",11,MUTED).pack(anchor="w",padx=12,pady=(8,2))
        self.identity=self.label(foot,self.values["name"].get(),13,bold=True)
        self.identity.pack(anchor="w",padx=12,pady=(0,8))
        self.label(self.sidebar,'v'+__version__,11,MUTED).grid(row=8,column=0,sticky="w",padx=16,pady=(0,16))
        self.body=ctk.CTkFrame(self,fg_color=BG,corner_radius=0)
        self.body.grid(row=1,column=1,sticky="nsew",padx=20,pady=16)
        self.body.grid_columnconfigure(0,weight=1)
        self.body.grid_rowconfigure(2,weight=1)
        themes={"跟随系统":"system","亮色":"light","暗色":"dark"}
        def change_theme(label):
            self.theme=themes[label]
            ctk.set_appearance_mode(self.theme)
            self.save()
        appearance=ChoiceMenu(self.top,values=list(themes),width=100,command=change_theme)
        appearance.set(next((k for k,v in themes.items() if v==self.theme),"跟随系统"))
        appearance.pack(side="right",padx=8)
        self.remember_login=tk.BooleanVar(value=False)
        self.login_file=self.settings.path.parent/"server-login.bin"
        self.avatar=self.button(self.top,"👤",self.open_server_account,True,width=40)
        self.avatar.configure(corner_radius=20)
        self.avatar.pack(side="right",padx=(8,0))
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
        self.after(200,self.restore_server_login)
        self.protocol("WM_DELETE_WINDOW",self.close)
        self.after(100,self.drain)
        self.after(1000,self.poll_game)

    def font(self,size=13,bold=False):
        return ctk.CTkFont(family="Microsoft YaHei UI" if os.name=="nt" else "sans-serif",size=size,weight="bold" if bold else "normal")

    def label(self,parent,text,size=14,color=TEXT,bold=False,**kw):
        return ctk.CTkLabel(parent,text=text,font=self.font(size,bold),text_color=color,anchor="w",**kw)

    def button(self,parent,text,command,primary=False,**kw):
        return ctk.CTkButton(parent,text=text,command=command,height=34,corner_radius=6,
            fg_color=PRIMARY if primary else SURFACE,hover_color=PRIMARY_HOVER if primary else HOVER,
            text_color="#FFFFFF" if primary else TEXT,font=self.font(13,primary),**kw)

    def card(self,parent,**kw):
        return ctk.CTkFrame(parent,fg_color=CARD,border_color=BORDER,border_width=1,corner_radius=10,**kw)

    def entry(self,parent,key,placeholder=""):
        return ctk.CTkEntry(parent,textvariable=self.values[key],height=40,
            fg_color=SURFACE,border_color=BORDER,border_width=1,corner_radius=7,
            text_color=TEXT,placeholder_text=placeholder,font=self.font(13))

    def heading(self,parent,title,subtitle):
        self.label(parent,title,20,bold=True).pack(anchor="w")
        self.label(parent,subtitle,13,MUTED).pack(anchor="w",pady=(4,20))

    def build_home(self):
        p=self.pages["home"]
        self.heading(p,"开始游戏","启动本地实例，或接续已经绑定的共享世界。")
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
        self.version_menu=ChoiceMenu(vr,variable=self.values["version"],values=["尚未选择"],height=40,
            fg_color=("#45668E","#282A3A"),button_color="#373A50",button_hover_color="#474B66",font=self.font(13),
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
        resources=physical_memory_mib()
        if resources:
            total,available=resources
            maximum=max(768,min(65536,((total-max(1024,total//8))//256)*256))
            slider=ctk.CTkSlider(f,from_=512,to=maximum,number_of_steps=(maximum-512)//256,
                command=lambda value:self.values['memory'].set(str(round(value))))
            slider.pack(fill="x",pady=6)
            def reflect_memory(*_):
                value=self.values['memory'].get()
                if value.isdecimal():
                    slider.set(min(maximum,int(value)))
            self.values['memory'].trace_add("write",reflect_memory)
            reflect_memory()
            self.label(f,f"物理内存 {total/1024:.1f} GiB · 当前可用 {available/1024:.1f} GiB",11,MUTED).pack(anchor="w")
        self.label(c,'自定义 UUID · 可选，留空按名称生成；修改后须重新绑定共享房间',12,MUTED).grid(row=2,column=0,sticky='w',padx=22,pady=(10,6))
        self.game_uuid_entry=self.entry(c,'uuid');self.game_uuid_entry.grid(row=3,column=0,sticky='ew',padx=22)
        modes=ctk.CTkFrame(c,fg_color='transparent');modes.grid(row=4,column=0,sticky='ew',padx=22,pady=(18,8))
        java_modes={"自动选择":"auto","手动指定":"manual"}
        java_selector=ctk.CTkSegmentedButton(modes,values=list(java_modes),
            command=lambda label:(self.values["java_mode"].set(java_modes[label]),self.java_mode_changed()))
        java_selector.pack(side="left")
        def sync_java_mode(*_):
            java_selector.set("手动指定" if self.values["java_mode"].get()=="manual" else "自动选择")
        self.values["java_mode"].trace_add("write",sync_java_mode)
        sync_java_mode()
        self.java_hint=self.label(c,'正在准备 Java 检测',12,MUTED,wraplength=650)
        self.java_hint.grid(row=5,column=0,sticky='w',padx=22,pady=6)
        self.path_row(c,6,'当前 Java 可执行文件','java',True)
        self.java_menu=ChoiceMenu(c,values=['尚未检测'],variable=self.java_choice,fg_color=CARD,button_color=PRIMARY,command=self.choose_java_candidate,dynamic_resizing=False)
        self.java_menu.grid(row=8,column=0,sticky='ew',padx=22,pady=8)
        actions=ctk.CTkFrame(c,fg_color='transparent');actions.grid(row=9,column=0,sticky='ew',padx=22,pady=8)
        self.button(actions,'重新检测 Java',self.detect_java,width=135).pack(side='left',padx=(0,10))
        self.java_download_button=self.button(actions,'下载推荐 Java',self.download_java,width=170)
        self.java_download_button.pack(side='left')
        self.label(c,'从系统、注册表、用户 .jdks、游戏及启动器运行时目录发现；不读取其他启动器账号。',11,MUTED,wraplength=650).grid(row=10,column=0,sticky='w',padx=22,pady=6)
        self.path_row(c,11,'运行目录 · 自动识别版本隔离，可手动修改','run',False)
        advanced=self.card(c)
        advanced.grid(row=13,column=0,sticky="ew",padx=22,pady=8)
        advanced.grid_columnconfigure(1,weight=1)
        for index,(key,title) in enumerate([("initial_heap","初始内存 / MiB"),("window_width","窗口宽度"),("window_height","窗口高度"),("extra_jvm","额外 JVM 参数")]):
            self.label(advanced,title,12,MUTED).grid(row=index,column=0,sticky="w",padx=12,pady=4)
            self.entry(advanced,key).grid(row=index,column=1,sticky="ew",padx=12,pady=4)
        ctk.CTkCheckBox(advanced,text="全屏启动",variable=self.values["fullscreen"],onvalue="1",offvalue="0").grid(row=4,column=1,sticky="w",padx=12,pady=6)
        self.button(c,'保存配置',self.save,primary=True,width=120).grid(row=14,column=0,sticky='e',padx=22,pady=20)
        self.build_game_accounts(scroll)

    def build_worlds(self,scroll):
        card=self.card(scroll);card.grid(row=3,column=0,sticky='ew',pady=(0,16));card.grid_columnconfigure(0,weight=1)
        self.label(card,'本地存档 · 自动识别',17,bold=True).grid(row=0,column=0,sticky='w',padx=22,pady=(18,8))
        self.world_menu=ChoiceMenu(card,values=['尚未选择运行目录'],fg_color=CARD,button_color=PRIMARY,command=self.select_world)
        self.world_menu.grid(row=1,column=0,sticky='ew',padx=22,pady=8)
        self.world_cover=self.label(card,"◇",26,MUTED)
        self.world_cover.grid(row=0,column=1,rowspan=3,padx=16,pady=12)
        self.world_hint=self.label(card,'仅检测当前运行目录的saves；游戏运行时暂停，不扫描区块文件。',12,MUTED,wraplength=650)
        self.world_hint.grid(row=2,column=0,sticky='w',padx=22,pady=8)
        self.button(card,'发布选中存档',lambda:self.create_room(world_path=self.world_choices.get(self.world_menu.get(),{}).get('path')),True,width=160).grid(row=3,column=0,sticky='e',padx=22,pady=(8,20))
        self.button(card,'预览区块清理',self.preview_world_prune,width=145).grid(row=3,column=0,sticky='w',padx=22,pady=(8,20))
        self.world_choices={};self.world_generation=0;self.world_scan_key=None
        self.after(15000,self.auto_worlds)

    def preview_world_prune(self):
        if self.transfer_active or self.shared or self.launching or (self.process and self.process.poll() is None):
            self.note('请先保存退出游戏并等当前同步完成',True);return
        entry=self.world_choices.get(self.world_menu.get(),{})
        if not entry.get('path'):return
        world=Path(entry['path'])
        from .world_prune import clean_copy
        from .vendor.mcsync import chunk_prune
        dialog=ctk.CTkToplevel(self)
        dialog.title("区块清理")
        dialog.geometry("720x615")
        dialog.transient(self)
        self.label(dialog,entry.get("world_name") or world.name,19,bold=True).pack(anchor="w",padx=18,pady=(14,4))
        self.label(dialog,str(world),11,MUTED,wraplength=670).pack(anchor="w",padx=18)
        settings=ctk.CTkScrollableFrame(dialog,height=106)
        settings.pack(fill="x",padx=16,pady=8)
        self.label(settings,"停留时间低于（秒）",13).pack(anchor="w",padx=8)
        seconds=tk.StringVar(value=str(chunk_prune.DEFAULT_MAX_SECONDS))
        ctk.CTkEntry(settings,textvariable=seconds,width=130).pack(anchor="w",padx=8)
        dimensions={}
        textbox=ctk.CTkTextbox(dialog,wrap="word")
        textbox.pack(fill="both",expand=True,padx=16,pady=6)
        buttons=ctk.CTkFrame(dialog,fg_color="transparent")
        buttons.pack(fill="x",padx=16,pady=12)
        pending={}
        def render(text):
            if dialog.winfo_exists():
                textbox.configure(state="normal")
                textbox.delete("1.0","end")
                textbox.insert("1.0",text)
                textbox.configure(state="disabled")
        def invalidate(*_):
            pending.clear()
            for button in (copy_button,apply_button):
                button.configure(state="disabled")
        def busy():
            return self.transfer_active or self.shared or self.launching or self.process and self.process.poll() is None
        def scan():
            if busy():return
            invalidate()
            try:
                raw=seconds.get()
                limit=float(raw)
                if not 0<=limit<=3600:raise ValueError()
            except ValueError:
                render("请输入 0 至 3600 秒。")
                return
            selected={d for d,v in dimensions.items() if v.get()}
            if not selected:
                render("请至少选择一个维度。")
                return
            self.begin_transfer("prune","扫描存档区块")
            render("正在检查 region、entities 和 POI 文件…")
            def done(value):
                plan,report=value
                self.finish_transfer(True,"区块扫描完成")
                if not dialog.winfo_exists():return
                if raw!=seconds.get() or selected!={d for d,v in dimensions.items() if v.get()}:
                    render("清理范围已变化，请重新扫描。")
                    return
                pending.update(plan=plan,limit=limit,selected=selected)
                rows=[f"扫描 {report.total_chunks} 个地形区块 · 跳过 {report.skipped_chunks} 个记录",
                      f"预计处理 {len(plan)} 个文件，释放约 {human_bytes(report.freed_bytes)}（上游扫描估算）"]
                for item in report.regions:
                    file=Path(item.path).resolve().relative_to(world)
                    if file in plan:
                        rows.append(f"{item.dimension} / {item.kind} / {file.name} · {len(plan[file][0])} 条记录")
                render("\n".join(rows) if plan else "没有可安全清理的区块。")
                for button in (copy_button,apply_button):
                    button.configure(state="normal" if plan else "disabled")
            self.task(lambda:clean_copy(world,limit,dimensions=selected,report_only=True),done,fail)
        def fail(error):
            self.finish_transfer(False,error)
            render(error)
        def execute(in_place):
            if not pending or busy():return
            limit,plan,selected=(pending[k] for k in ("limit","plan","selected"))
            if in_place and not messagebox.askyesno("备份并清理原存档",
                    "将先创建完整备份，再清理原存档。请确认游戏已经关闭。",parent=dialog):
                return
            invalidate()
            self.begin_transfer("prune","正在清理区块")
            def done(result):
                if in_place:
                    detail=(f"备份：{result['backup']}\n处理文件 {result['touched_files']} · 删除文件 {result['deleted_files']}"
                            f" · 释放 {human_bytes(result['freed_bytes'])}\n"+"\n".join(result["errors"]))
                    self.finish_transfer(result["ok"],"区块清理完成" if result["ok"] else "部分文件清理失败，详见报告")
                else:
                    detail="清理副本："+str(result)
                    self.finish_transfer(True,"清理副本已生成")
                render(detail)
                self.refresh_worlds()
            self.task(lambda:clean_copy(world,limit,plan,dimensions=selected,in_place=in_place),done,fail)
        scan_button=self.button(buttons,"扫描预览",scan,True)
        scan_button.pack(side="left")
        scan_button.configure(state="disabled")
        copy_button=self.button(buttons,"生成清理副本",lambda:execute(False))
        copy_button.pack(side="right",padx=6)
        apply_button=self.button(buttons,"备份并清理原档",lambda:execute(True))
        apply_button.pack(side="right",padx=6)
        invalidate()
        seconds.trace_add("write",invalidate)
        def supported(result):
            if not dialog.winfo_exists():return
            ok,reason,dims=result
            render(reason)
            if ok:
                for dimension in dims:
                    variable=tk.BooleanVar(value=True)
                    dimensions[dimension["label"]]=variable
                    ctk.CTkCheckBox(settings,text=dimension["label"],variable=variable,command=invalidate).pack(anchor="w",padx=8,pady=2)
                scan_button.configure(state="normal")
        def diagnose():
            ok,reason=chunk_prune.capability(str(world))
            if not ok:
                return ok,reason,[]
            return ok,reason,chunk_prune.discover_dimensions(str(world))
        self.task(diagnose,supported,render)

    def auto_worlds(self):
        self.maybe_refresh_worlds();self.after(15000,self.auto_worlds)

    def world_signature(self,run):
        saves=Path(run)/"saves"
        selected=self.world_choices.get(self.world_menu.get(),{})
        icon=Path(selected["path"])/"icon.png" if "path" in selected else None
        try:
            cover=(icon.stat().st_mtime_ns,icon.stat().st_size) if icon else None
        except OSError:
            cover=None
        return (run,saves.stat().st_mtime_ns,cover)

    def maybe_refresh_worlds(self):
        run=self.values['run'].get().strip() or self.values['root'].get().strip()
        try:signature=self.world_signature(run)
        except OSError:signature=(run,None)
        if signature!=self.world_scan_key:self.refresh_worlds()

    def refresh_worlds(self):
        if self.shared or self.process and self.process.poll() is None:return
        run=self.values['run'].get().strip() or self.values['root'].get().strip()
        if not run or not hasattr(self,'world_menu'):return
        try:self.world_scan_key=self.world_signature(run)
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
            try:self.world_scan_key=self.world_signature(run)
            except OSError:pass
        self.task(lambda:discover(run),done)

    def select_world(self,label):
        world=self.world_choices.get(label)
        from PIL import Image
        empty=ctk.CTkImage(light_image=Image.new("RGBA",(1,1)),size=(1,1))
        self.world_cover.configure(image=empty,text="未提供封面")
        if world:
            preview=Path(world['path'])/'icon.png'
            try:
                if not preview.is_symlink() and preview.stat().st_size<=8*1024*1024:
                    with Image.open(preview,formats=['PNG']) as picture:
                        if max(picture.size)<=4096:
                            self.world_cover.configure(image=ctk.CTkImage(light_image=picture.convert('RGBA'),size=(84,84)),text='')
            except (OSError,ValueError,Image.DecompressionBombError):
                pass
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
        self.game_account_menu=ChoiceMenu(card,values=['离线游戏账号'],command=self.select_game_account,fg_color=CARD,button_color=PRIMARY)
        self.game_account_menu.grid(row=2,column=0,sticky='ew',padx=22,pady=8)
        row=ctk.CTkFrame(card,fg_color='transparent');row.grid(row=3,column=0,sticky='w',padx=22,pady=(8,20))
        self.button(row,'保存离线角色',self.store_offline_profile,width=120).pack(side='left',padx=(0,8))
        self.button(row,'添加 LittleSkin',self.add_littleskin,width=150).pack(side='left',padx=(0,12))
        self.button(row,'退出所选账号',self.remove_game_account,width=150).pack(side='left')
        self.refresh_game_accounts()

    def store_offline_profile(self):
        if self.values["game_account"].get() or self.shared or self.launching:
            self.note("请切换到离线身份并结束共享会话",True)
            return
        name=self.values["name"].get().strip()
        try:
            identity=game_uuid(name,self.values["uuid"].get())
        except ValueError as error:
            self.note(str(error),True)
            return
        self.offline_profiles[identity]=name
        self.save()
        self.refresh_game_accounts()

    def refresh_game_accounts(self):
        self.game_choices={'离线游戏账号':''}
        for identity,name in self.offline_profiles.items():
            self.game_choices[f"离线 · {name} · {identity}"]="offline/"+identity
        for key in list(self.game_accounts.rows):
            p=self.game_accounts.public(key);self.game_choices['LittleSkin · '+p['name']+' · '+p['id'][:8]]=key
        self.game_account_menu.configure(values=list(self.game_choices))
        key=self.values['game_account'].get()
        if not key:
            try:
                identity=game_uuid(self.values["name"].get(),self.values["uuid"].get())
                if self.offline_profiles.get(identity)==self.values["name"].get():
                    key="offline/"+identity
            except ValueError:
                pass
        self.game_account_menu.set(next((label for label,value in self.game_choices.items() if value==key),'角色未登录，请重新添加'))
        self.game_name_entry.configure(state='disabled' if key and not key.startswith('offline/') else 'normal')
        self.game_uuid_entry.configure(state='disabled' if key and not key.startswith('offline/') else 'normal')

    def select_game_account(self,label):
        if self.shared or self.launching or self.process and self.process.poll() is None:self.note('请先结束游戏再切换账号',True);self.refresh_game_accounts();return
        key=self.game_choices[label];old=self.values['game_account'].get()
        if key.startswith("offline/"):
            identity=key.split("/",1)[1]
            self.values["name"].set(self.offline_profiles[identity])
            self.values["uuid"].set(identity)
            key=""
        elif key:
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
        role=ChoiceMenu(dialog,values=['登录后选择角色'],fg_color=CARD,button_color=PRIMARY);role.pack(fill='x',padx=24,pady=8)
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
        if not key:
            selected=self.game_choices.get(self.game_account_menu.get(),"")
            if selected.startswith("offline/") and not self.shared:
                identity=selected.split("/",1)[1]
                rooms=[room for room,b in self.bindings.items() if b.get("name")==self.offline_profiles[identity]]
                if messagebox.askyesno("移除离线角色","从角色列表移除？保留已有绑定："+("、".join(rooms) or "无"),parent=self):
                    del self.offline_profiles[identity]
                    self.save()
                    self.refresh_game_accounts()
            return
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

    def build_host_presets(self,parent):
        e=self.settings.data.get("host_presets",{})
        self.host_pvp=tk.StringVar(value=e.get("pvp","随世界"))
        self.host_cheats=tk.BooleanVar(value=e.get("cheats",False))
        self.host_auth=tk.BooleanVar(value=e.get("official_auth",False))
        self.host_mode=tk.StringVar(value=e.get("mode","随世界"))
        self.host_difficulty=tk.StringVar(value=e.get("difficulty","随世界"))
        self.host_time=tk.StringVar(value=e.get("time","随世界"))
        self.host_weather=tk.StringVar(value=e.get("weather","随世界"))
        self.host_extras={key:tk.StringVar(value=e.get(key,"")) for key in
                          ("players","view_distance","simulation_distance","allowlist","game_rules","world_border")}
        content=ctk.CTkScrollableFrame(parent,fg_color="transparent")
        content.pack(fill="both",expand=True)
        card=self.card(content)
        card.pack(fill="x",padx=16,pady=16)
        self.label(card,"Host 联机预设",20,bold=True).pack(anchor="w",padx=20,pady=(16,4))
        self.label(card,"仅在本机接管共享世界并开放局域网时应用。",13,MUTED).pack(anchor="w",padx=20,pady=(0,12))
        for title,values,variable in (
            ("玩家对战",["随世界","允许","禁止"],self.host_pvp),
            ("开服时段",["随世界","白天","正午","夜晚","午夜"],self.host_time),
            ("开服天气",["随世界","晴天","下雨","雷暴"],self.host_weather),
            ("难度",["随世界","和平","简单","普通","困难"],self.host_difficulty),
            ("默认游戏模式",["随世界","生存","创造","冒险","旁观"],self.host_mode),
        ):
            row=ctk.CTkFrame(card,fg_color="transparent")
            row.pack(fill="x",padx=20,pady=6)
            self.label(row,title,14).pack(side="left")
            ChoiceMenu(row,values=values,variable=variable,width=160).pack(side="right")
        for title,variable in (("允许作弊",self.host_cheats),("要求 Minecraft 正版验证",self.host_auth)):
            ctk.CTkSwitch(card,text=title,variable=variable,onvalue=True,offvalue=False).pack(anchor="w",padx=20,pady=8)
        self.label(card,"正版验证使用 Minecraft 官方认证。离线玩家无法加入，LittleSkin 不能用于开启正版验证的 Host。",12,MUTED).pack(anchor="w",padx=20,pady=4)
        for title,key,hint in (
            ("共享房间玩家上限","players","含 Host，2–100，留空沿用默认"),
            ("区块视距","view_distance","2–32 区块，留空沿用游戏选项"),
            ("模拟距离","simulation_distance","5–32 区块，留空沿用游戏选项"),
            ("世界边界直径","world_border","1–59,999,968 方块，留空保持存档设置"),
            ("共享房间白名单","allowlist","Aetherloom 账号名，用逗号分隔；留空允许房间成员"),
            ("游戏规则","game_rules","规则名=值，使用分号分隔，例如 doFireTick=false;keepInventory=true"),
        ):
            row=ctk.CTkFrame(card,fg_color="transparent")
            row.pack(fill="x",padx=20,pady=5)
            self.label(row,title,13).pack(anchor="w")
            ctk.CTkEntry(row,textvariable=self.host_extras[key],placeholder_text=hint,height=34).pack(fill="x",pady=3)
            self.label(row,hint,11,MUTED,wraplength=720).pack(anchor="w")
        self.label(card,"此模式由 Minecraft 内置局域网服务器运行。独立服务端的绑定地址、固定端口、RCON、Query、资源包推送、种子和世界生成器等设置不可用。共享世界使用现有存档。",12,MUTED,wraplength=720).pack(anchor="w",padx=20,pady=(12,0))
        self.button(card,"保存预设",self.save,True).pack(anchor="e",padx=20,pady=16)

    def host_presets(self):
        return dict(pvp=self.host_pvp.get(),mode=self.host_mode.get(),
                    cheats=self.host_cheats.get(),official_auth=self.host_auth.get(),
                    difficulty=self.host_difficulty.get(),time=self.host_time.get(),weather=self.host_weather.get(),
                    **{key:var.get().strip() for key,var in self.host_extras.items()})

    def build_cloud(self):
        p=self.pages["cloud"]
        self.heading(p,"共享世界","连接你的服务器，查看实例与在线会话。")
        bar=ctk.CTkFrame(p,fg_color="transparent")
        bar.pack(fill="x",pady=(0,10))
        self.cloud_state=self.label(bar,"尚未连接",13,MUTED)
        self.cloud_state.pack(side="left")

        self.login_dialog=ctk.CTkToplevel(self)
        self.login_dialog.withdraw()
        self.login_dialog.title("登录 Aetherloom")
        self.login_dialog.transient(self)
        self.login_dialog.protocol("WM_DELETE_WINDOW",self.login_dialog.withdraw)
        card=self.card(self.login_dialog);card.pack(fill="x",pady=(0,16));card.grid_columnconfigure((0,1),weight=1)
        self.label(card,"服务器连接",17,bold=True).grid(row=0,column=0,sticky="w",padx=22,pady=(18,6))
        self.label(card,"软件账号与游戏中的离线身份相互独立。",12,MUTED).grid(row=1,column=0,columnspan=2,sticky="w",padx=22,pady=(0,8))
        self.label(card,"服务器地址",12,MUTED).grid(row=2,column=0,sticky="w",padx=22)
        self.entry(card,"url").grid(row=3,column=0,columnspan=2,sticky="ew",padx=22,pady=(6,12))
        for col,title in [(0,"软件账号"),(1,"软件密码")]:
            self.label(card,title,12,MUTED).grid(row=4,column=col,sticky="w",padx=22)
        self.entry(card,"username").grid(row=5,column=0,sticky="ew",padx=(22,8),pady=6)
        self.password_entry=ctk.CTkEntry(card,textvariable=self.password,show="•",height=40,
            fg_color=SURFACE,border_color=BORDER,font=self.font(13))
        self.password_entry.grid(row=5,column=1,sticky="ew",padx=(8,22),pady=6)
        self.password_entry.bind("<Return>",lambda _:self.login())
        remember=ctk.CTkCheckBox(card,text="在此 Windows 账号下记住登录（30 天）",variable=self.remember_login)
        remember.grid(row=6,column=0,columnspan=2,sticky="w",padx=22,pady=(6,0))
        if os.name!="nt":remember.configure(state="disabled")
        self.login_button=self.button(card,"登录服务器",self.login,True,width=150)
        self.login_button.grid(row=7,column=1,sticky="e",padx=22,pady=(14,20))
        tabs=ctk.CTkTabview(p)
        tabs.pack(fill="both",expand=True)
        local=tabs.add("本地存档")
        local.grid_columnconfigure(0,weight=1)
        self.build_worlds(local)
        p=tabs.add("共享房间")
        self.build_host_presets(tabs.add("Host 联机预设"))
        tabs.set("共享房间")
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
            corner_radius=12,text_color=("#243752","#C4C7D8"),font=self.font(13))
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
        for key,b in self.nav.items():b.configure(fg_color=SELECTED if key==name else "transparent",text_color=ACCENT if key==name else MUTED)
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
        self.notice.configure(text=message[:115],text_color=DANGER if error else MUTED)
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
        try:
            from .game_control import validate_host_settings
            validate_host_settings(self.host_presets())
        except ValueError as error:
            self.note(str(error),True)
            return False
        try:self.settings.save(dict({k:v.get().strip() for k,v in self.values.items()},host_presets=self.host_presets(),offline_profiles=self.offline_profiles,theme=self.theme,room_bindings=self.bindings,auto_run_path=self.auto_run,selected_room=self.selected_room,local_profiles=self.profiles))
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
        deadline=time.monotonic()+.012
        while time.monotonic()<deadline:
            try:callback,result,_=self.events.get_nowait()
            except queue.Empty:break
            if _!='notification':self.pending-=1
            try:callback(result)
            except Exception as e:self.fail(str(e))
        self.after(16 if not self.events.empty() else 100,self.drain)

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
        options={k:self.values[k].get() for k in ("initial_heap","window_width","window_height","extra_jvm","fullscreen")}
        custom_uuid=self.values['uuid'].get().strip()
        mode=self.values['java_mode'].get()
        account=self.values['game_account'].get()
        def start():
            from .shared_session import assets
            self.check_game_identity({'game_account':account,'name':name,'uuid':custom_uuid})
            auth=self.game_accounts.refresh(account,name,custom_uuid) if account else None
            selected=self.resolve_java(root,version,java,mode)
            return launch(root,version,selected,name,run or None,memory,options=options,custom_uuid=custom_uuid,game_auth=auth,authlib_jar=assets()/'authlib-injector.jar' if auth else None),selected
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

    def open_server_account(self):
        if self.token:
            self.account_settings()
            return
        self.login_dialog.deiconify()
        self.login_dialog.lift()
        self.password_entry.focus_set()

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
        remember=self.remember_login.get()
        def done(result):
            self.finish_server_login(url,result)
            from .game_accounts import dpapi
            try:
                if remember:
                    payload=json.dumps({"url":url,"token":self.token}).encode()
                    pending=self.login_file.with_suffix(".tmp")
                    pending.write_bytes(dpapi(payload))
                    os.replace(pending,self.login_file)
                else:
                    self.login_file.unlink(missing_ok=True)
            except (OSError,ValueError):
                self.note("已登录，但 Windows 未能保存登录状态",True)
        def failed(message):
            self.login_busy=False;self.login_button.configure(state="normal",text="登录服务器")
            self.cloud_state.configure(text="连接未完成",text_color=DANGER)
            self.connection.configure(text="●  本地模式");self.home_connection.configure(text="本地模式");self.note(message,True)
        self.task(lambda:self.request(url,"","/api/login",{"username":username,"password":password,**({"remember":True} if remember else {})}),done,failed)

    def finish_server_login(self,url,result):
        self.login_busy=False
        self.login_button.configure(state="normal",text="登录服务器")
        self.token=result["token"]
        self.server_url=url
        self.password.set("")
        self.cloud_user=result["username"]
        self.cloud_role=result["role"]
        self.avatar.configure(text=self.cloud_user[0].upper())
        self.cloud_state.configure(text=self.cloud_user+" · "+self.cloud_role,text_color=ACCENT)
        self.connection.configure(text="●  已连接服务器")
        self.home_connection.configure(text="已连接")
        for button in self.cloud_buttons:
            button.configure(state="normal")
        self.login_dialog.withdraw()
        self.note("服务器登录成功")
        self.rooms()

    def restore_server_login(self):
        if not self.login_file.is_file() or self.login_busy or self.token:
            return
        from .game_accounts import dpapi
        try:
            saved=json.loads(dpapi(self.login_file.read_bytes(),True))
            url,token=saved["url"],saved["token"]
        except (KeyError,OSError,ValueError):
            self.note("无法读取已记住的登录，请手动登录",True)
            return
        self.login_busy=True
        def done(result):
            self.remember_login.set(True)
            self.values["url"].set(url)
            self.values["username"].set(result["name"])
            self.finish_server_login(url,{"username":result["name"],"role":result["role"],"token":token})
        def failed(_message):
            self.login_busy=False
            self.note("未能恢复登录，请点击头像重新登录",True)
        self.task(lambda:self.request(url,token,"/api/me"),done,failed)

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
            now=time.time()
            items=[dict(item,state="recovery_required") if item.get("host") and item.get("expires",0)<=now else item for item in items]
            self.room_items={item['id']:item for item in items}
            scroll=self.room_list._parent_canvas.yview()[0]
            for child in self.room_list.winfo_children():
                if not any(child is row[0] for row in self.room_rows.values()):child.destroy()
            for key in set(self.room_rows)-set(self.room_items):
                self.room_rows.pop(key)[0].destroy()
            self.refresh_summary()
            if not items:self.label(self.room_list,"暂无共享房间 · 先配置游戏，再发布一个本地世界。",13,MUTED).pack(pady=30);return
            for item in items:
                signature=json.dumps([{key:value for key,value in item.items() if key!='expires'},self.bindings.get(item['id']),bool(self.bindings.get(item['id']) and (Path(self.bindings[item['id']]['world'])/'.aetherloom/pending-session.json').is_file())],sort_keys=True)
                old=self.room_rows.get(item['id'])
                if old and old[1]==signature:continue
                if old:old[0].destroy()
                row=ctk.CTkFrame(self.room_list,fg_color=SURFACE,corner_radius=8);row.pack(fill="x",padx=8,pady=5)
                self.room_rows[item['id']]=(row,signature)
                top=ctk.CTkFrame(row,fg_color='transparent');top.pack(fill='x',padx=14,pady=(10,4))
                self.label(top,item.get('name') or item['id'][:12],14,bold=True).pack(side='left')
                self.label(top,("Host "+item["host"]) if item.get("host") else "当前无 Host",12,ACCENT).pack(side='right')
                self.label(row,(item.get('environment') or '未设置环境')+' · 所有者 '+item['owner']+' · '+({'idle':'可接管','preparing':'准备中','recovery_required':'Host 已断开 · 可按云端副本恢复','ready':'可加入','uploading':'上传中'}.get(item['state'],item['state'])),11,MUTED).pack(anchor='w',padx=14)
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
            if existing:
                if existing.get('head'):raise ValueError('已有权威存档，请使用恢复候选审批，不能直接覆盖')
                room=existing['id']
                api('/api/rooms/'+room,dict(name=name,environment=encode(environment),world=world.name),method='PATCH')
            else:
                from .modpack import required_mods
                room=api('/api/rooms',dict(name=name,environment=encode(environment),world=world.name,required_mods=required_mods(binding["run"])))['id']
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
        b={k:self.values[k].get().strip() for k in ('root','run','version','java','name','memory','uuid','java_mode','control_backend','game_account','initial_heap','window_width','window_height','extra_jvm','fullscreen')}
        try:game_uuid(b['name'],b['uuid'])
        except ValueError as e:self.note(str(e),True);return None
        if not b['root'] or (not b['java'] and b['java_mode']=='manual') or b['version']=='尚未选择':
            self.note('先在本地游戏中定位游戏目录、版本和Java',True);self.show('instance');return None
        b['run']=b['run'] or b['root']
        try:self.check_game_identity(b)
        except ValueError as error:self.note(str(error),True);return None
        return b

    def bind_room(self,room,binding=None):
        b=binding or self.current_binding()
        if not b:return
        try:
            from .game_control import select_backend
            from .vanilla_control import name_data_identity
            environment=describe(b['root'],b['version'])
            validate(environment,room.get('environment'),backend=select_backend(b))
            from .modpack import verify_pack
            verify_pack(b['run'],environment,room.get('environment'),room.get('required_mods'))
            name_data_identity(b,environment['minecraft'])
        except (ValueError,OSError,KeyError) as e:self.note(str(e),True);return
        if binding is None and not messagebox.askyesno('绑定共享房间',f"将当前本地版本 {b['version']} 绑定到房间 {room.get('name') or room['id']}？\n请确保版本、加载器和Mods与房间环境一致。\n作为Host时会将云端存档校验下载到专用世界目录。",parent=self):return
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
        mode=ChoiceMenu(dialog,values=['AUTO','RELAY','DIRECT'],fg_color=CARD,button_color=PRIMARY,height=38);mode.set(room.get('mode') or 'AUTO');mode.pack(fill='x',padx=24,pady=8)
        def saved(_):dialog.destroy();self.rooms();self.note('房间配置已更新')
        def save_room():
            body={'name':name.get(),'mode':mode.get()}
            self.cloud_task('/api/rooms/'+room['id'],saved,body,method='PATCH')
        self.button(dialog,'保存名称和连接模式',save_room,True,width=240).pack(anchor='w',padx=24,pady=8)
        self.button(dialog,'审阅并批准恢复候选',lambda:self.review_recovery(room),width=220).pack(anchor='w',padx=24,pady=8)
        if room['owner']==self.cloud_user or self.cloud_role=='root':
            owner=ChoiceMenu(dialog,values=[room['owner']],height=38,fg_color=CARD,button_color=PRIMARY);owner.pack(fill='x',padx=24,pady=8)
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
            target=ChoiceMenu(controls,values=['正在读取账号'],fg_color=CARD,button_color=PRIMARY);target.pack(side='left',padx=4)
            role=ChoiceMenu(controls,values=['member','admin'],width=100,fg_color=CARD,button_color=PRIMARY);role.pack(side='left',padx=4)
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
            choice=ChoiceMenu(dialog,values=list(labels),fg_color=CARD,button_color=PRIMARY);choice.pack(fill='x',padx=24,pady=16)
            def approve():
                if not messagebox.askyesno('批准恢复','确认已经核对候选内容，并用它创建新的权威版本？',parent=dialog):return
                self.cloud_task(base+'/recoveries/'+labels[choice.get()]+'/approve',lambda _:(dialog.destroy(),self.rooms(),self.note('恢复已批准并创建新权威版本')),{'expected_head':head['version']})
            self.button(dialog,'批准恢复',approve,True,width=160).pack(anchor='e',padx=24,pady=16)
        self.task(load,done)

    def account_settings(self):
        if self.shared:self.note('请先结束共享会话，再修改软件账号',True);return
        dialog=ctk.CTkToplevel(self)
        dialog.title("个人中心")
        dialog.transient(self)
        self.label(dialog,self.cloud_user+" · "+self.cloud_role,18,bold=True).pack(padx=24,pady=18)
        def choose(action):
            dialog.destroy()
            if action in ("退出登录","换账号登录"):
                def logout(result):
                    self.clear_server_login(result)
                    if action=="换账号登录":
                        self.values["username"].set("")
                        self.open_server_account()
                self.cloud_task('/api/logout',logout,{},method='POST')
            else:
                self.edit_server_account(action)
        for action in ("改名","改密","换账号登录","退出登录"):
            self.button(dialog,action,lambda item=action:choose(item)).pack(fill="x",padx=24,pady=6)

    def clear_server_login(self,_result):
        self.token=self.cloud_user=self.cloud_role=""
        self.avatar.configure(text="👤")
        try:
            self.login_file.unlink(missing_ok=True)
        except OSError:
            self.note("未能清理本地登录记录",True)
        self.cloud_state.configure(text="尚未连接")
        self.connection.configure(text="●  本地模式")
        self.home_connection.configure(text="本地模式")
        for button in self.cloud_buttons:
            button.configure(state="disabled")
        for child in self.room_list.winfo_children():
            child.destroy()
        self.room_rows.clear()
        self.room_items.clear()
        self.refresh_summary()

    def edit_server_account(self,choice):
        dialog=ctk.CTkInputDialog(text='输入新名称' if choice=='改名' else '输入新密码（至少6位）',title=choice)
        if choice=='改密':dialog.after(30,lambda:getattr(dialog,'_entry',None) and dialog._entry.configure(show='•'))
        value=dialog.get_input()
        if not value:return
        def done(result):
            if choice=='改名':
                self.cloud_user=result['username'];self.values['username'].set(result['username']);self.save()
                self.cloud_state.configure(text=self.cloud_user+' · '+self.cloud_role)
            else:
                self.clear_server_login(result);self.cloud_state.configure(text='密码已更新，请重新登录')
                self.connection.configure(text='●  本地模式');self.home_connection.configure(text='本地模式')
                for button in self.cloud_buttons:button.configure(state='disabled')
                self.note('密码已修改，原登录已失效，请使用新密码重新登录')
        self.cloud_task('/api/me',done,{'username' if choice=='改名' else 'password':value},method='PATCH')

    def play_room(self,room):
        room=self.room_items.get(room["id"],room)
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
        self.selected_room=room['id']
        if not self.save():return
        try:
            self.shared=session_type(self.server_url,self.token,self.settings.path.parent/'cache',room['id'],dict(self.bindings[room['id']],host_presets=self.host_presets()),notify,recovery,game_accounts=self.game_accounts)
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
        self.cancel_session.configure(state='normal');self.cancel_session.grid()
        def finished(_):
            self.shared=None;self.launching=False
            self.cancel_session.grid_remove()
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
            self.profiles[self.profile_key]={k:self.values[k].get() for k in ('run','java','memory','name','uuid','java_mode','control_backend','game_account','initial_heap','window_width','window_height','extra_jvm','fullscreen')}

    def select_version(self,save=True):
        self.remember_profile()
        previous=self.profile_key
        self.profile_key=self.values['root'].get()+'|'+self.values['version'].get()
        profile=self.profiles.get(self.profile_key)
        if previous and previous!=self.profile_key:
            for key in ("initial_heap","window_width","window_height","extra_jvm","fullscreen"):
                self.values[key].set("0" if key=="fullscreen" else "")
        if profile:
            self.values['uuid'].set(profile.get('uuid',''))
            self.values['java_mode'].set(profile.get('java_mode','auto'));self.values['control_backend'].set('agent');self.values['game_account'].set(profile.get('game_account',''))
            for key,value in profile.items():
                if key in self.values and key!="control_backend":self.values[key].set(value)
        else:
            if previous and previous!=self.profile_key:
                self.values['uuid'].set('');self.values['java_mode'].set('auto');self.values['control_backend'].set('agent');self.values['game_account'].set('')
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

        if room.get("required_mods") is None or self.shared or not self.token:
            return
        current=self.current_binding()
        if not current:
            return
        profiles=dict(self.profiles)
        existing=self.bindings.get(room["id"])
        url,token=self.server_url,self.token
        def candidates():
            from .modpack import verify_pack
            root=Path(current["root"])
            choices={}
            errors=[]
            for version_dir in sorted((root/"versions").iterdir()):
                version=version_dir.name
                if not (version_dir/(version+".json")).is_file():
                    continue
                item=dict(current,version=version)
                isolated=any((version_dir/k).is_dir() for k in ("mods","saves","config"))
                item["run"]=str(version_dir if isolated else root)
                item.update(profiles.get(str(root)+"|"+version,{}))
                if existing and existing.get("version")==version and existing.get("root")==str(root):
                    item.update(existing)
                try:
                    env=describe(root,version)
                    validate(env,room["environment"],backend="agent")
                    verify_pack(item["run"],env,room["environment"],room["required_mods"])
                except (OSError,ValueError,KeyError) as error:
                    errors.append(version+" · "+str(error))
                    continue
                choices[version]=item
            return choices,errors
        def found(result):
            if room["id"]!=self.selected_room or token!=self.token or url!=self.server_url:
                return
            choices,errors=result
            if existing and existing.get("version") in choices and choices[existing["version"]].get("run")==existing.get("run"):
                return
            if not choices:
                self.note("没有兼容的本地实例："+ "；".join(errors),True)
                return
            if len(choices)==1:
                self.bind_room(room,next(iter(choices.values())))
                return
            dialog=ctk.CTkToplevel(self)
            dialog.title("选择匹配的本地实例")
            dialog.transient(self)
            choice=ChoiceMenu(dialog,values=list(choices),width=280)
            choice.pack(padx=20,pady=16)
            def confirm():
                item=choices[choice.get()]
                dialog.destroy()
                if self.selected_room==room["id"] and self.token==token:
                    self.bind_room(room,item)
            self.button(dialog,"绑定所选实例",confirm,True).pack(pady=12)
        self.task(candidates,found)

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
        self.cancel_session=self.button(panel,"停止在线会话",self.cancel_online_launch,width=100)
        self.cancel_session.grid(row=0,column=2,rowspan=2,padx=(0,12))
        self.cancel_session.grid_remove()

    def cancel_online_launch(self):
        if self.shared:
            self.shared.stop=True
            self.cancel_session.configure(state="disabled")
            self.note("已请求停止在线会话，正在结束当前步骤并处理已启动的世界。")

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
        self.transfer_label.configure(text=safe(message)[:105],text_color=MUTED if success else DANGER)
        self.transfer_number.configure(text='100.0%' if success else f'未完成 · {self.transfer_percent:.1f}%')

    def session_status(self,state):
        self.session_info=dict(state)
        names={'created':'待启动','preflight':'校验环境／权威版本','claiming':'申请Host租约','syncing':'同步存档','connecting':'建立代理','loading':'游戏加载中','ready':'Host就绪／等待玩家','active':'运行中','saving':'保存与断开','uploading':'最终上传','inspection':'离线检查','complete':'正常完成','ended':'已结束','failed':'失败'}
        room=state.get('room','');item=self.room_items.get(room,{})
        details=f"实例：{item.get('name',room)}\n角色：{state.get('role','待确认')} · 策略：{state.get('mode','AUTO')} · 状态：{names.get(state.get('phase'),state.get('phase',''))}"
        details+=f"\n代次：{state.get('epoch') if state.get('epoch') is not None else '待确认'} · LAN端口：{state.get('lan_port') or '尚未就绪'} · 已就绪对端：{state.get('players',0)}"
        if state.get('message'):details+='\n'+safe(state['message'])
        self.network_summary.configure(text=details,text_color=DANGER if state.get('phase')=='failed' else TEXT)
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

