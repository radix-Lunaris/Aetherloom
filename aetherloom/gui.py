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
from .runtime import discover_java
from .environment import describe, encode, validate
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
        self.selected_room=self.settings.data.get("selected_room", "")
        self.profiles=self.settings.data.get("local_profiles", {})
        self.profile_key=None
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
        self.auto_run=data.get('auto_run_path','')
        saved_java=data.get("java","")
        self.values={key:tk.StringVar(value=str(data.get(key,default))) for key,default in
            [("root",""),("run",""),("name","Player"),("version","尚未选择"),("memory",4096),
             ("url","https://artherlink.superyk7hero.online:47192"),("username",""),("uuid","")]}
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
        self.label(foot,"离线游戏身份",size=12,color=ACCENT).pack(anchor="w",padx=14,pady=(12,2))
        self.identity=self.label(foot,self.values["name"].get(),size=14,bold=True)
        self.identity.pack(anchor="w",padx=14,pady=(0,12))
        self.label(self.sidebar,'v'+__version__,size=11,color="#696C81").grid(row=10,column=0,sticky="w",padx=28,pady=(0,24))
        self.body=ctk.CTkFrame(self,fg_color=BG,corner_radius=0)
        self.body.grid(row=0,column=1,sticky="nsew",padx=34,pady=28)
        self.body.grid_columnconfigure(0,weight=1)
        self.body.grid_rowconfigure(1,weight=1)
        self.top=ctk.CTkFrame(self.body,fg_color="transparent")
        self.top.grid(row=0,column=0,sticky="ew",pady=(0,18))
        self.breadcrumb=self.label(self.top,"工作台  /  开始游戏",size=12,color=MUTED)
        self.breadcrumb.pack(side="left")
        self.connection=self.label(self.top,"●  本地模式",size=12,color=ACCENT)
        self.connection.pack(side="right")
        self.pages={}
        for name in self.nav:
            frame=ctk.CTkFrame(self.body,fg_color="transparent")
            frame.grid(row=1,column=0,sticky="nsew")
            self.pages[name]=frame
        self.notice=self.label(self.body,"就绪",size=12,color=MUTED)
        self.notice.grid(row=2,column=0,sticky="w",pady=(12,0))
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
        for col,key,title in [(0,"name","离线玩家名称"),(1,"memory","最大内存 / MiB")]:
            f=ctk.CTkFrame(row,fg_color="transparent");f.grid(row=0,column=col,sticky="ew",padx=(0,10) if col==0 else (10,0))
            self.label(f,title,12,MUTED).pack(anchor="w",pady=(0,6));self.entry(f,key).pack(fill="x")
        self.label(c,'自定义 UUID · 可选，留空按名称生成；修改后须重新绑定共享房间',12,MUTED).grid(row=2,column=0,sticky='w',padx=22,pady=(10,6))
        self.entry(c,'uuid').grid(row=3,column=0,sticky='ew',padx=22)
        self.path_row(c,4,"Java · 从所选游戏目录自动查找，也可手动指定","java",True)
        self.java_menu=ctk.CTkOptionMenu(c,values=['尚未发现 Java'],variable=self.values['java'],fg_color=CARD,button_color=PRIMARY,command=lambda _:self.save())
        self.java_menu.grid(row=6,column=0,sticky='ew',padx=22,pady=8)
        self.path_row(c,8,"运行目录 · 自动识别版本隔离，可手动修改","run",False)
        self.button(c,"保存配置",self.save,primary=True,width=120).grid(row=10,column=0,sticky="e",padx=22,pady=20)

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

    def show(self,name):
        self.page=name;self.pages[name].tkraise()
        for key,b in self.nav.items():b.configure(fg_color="#302B49" if key==name else "transparent",text_color=ACCENT if key==name else MUTED)
        self.breadcrumb.configure(text="工作台  /  "+{"home":"开始游戏","instance":"本地游戏","cloud":"共享世界","network":"联机状态","logs":"运行记录"}[name])
        self.refresh_summary()

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
        self.refresh_summary();self.note("配置已保存");return True

    def pick(self,key,file=False):
        value=filedialog.askopenfilename(parent=self,title="选择 Java",filetypes=[("Java","*.exe"),("所有文件","*")]) if file else filedialog.askdirectory(parent=self,title="选择目录",initialdir=self.values[key].get() or None)
        if value:
            self.values[key].set(value)
            if key=="root":self.load_versions()
            self.save()

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
        if self.shared or self.launching or (self.process and self.process.poll() is None):return
        if not self.save():return
        try:
            root,version,java,name,run,memory=[self.values[k].get().strip() for k in ("root","version","java","name","run","memory")]
            if not root or not java or version=="尚未选择":raise ValueError("请先在本地游戏中选择游戏目录、版本和 Java")
            memory=int(memory)
            if not 512<=memory<=65536:raise ValueError("内存范围为 512—65536 MiB")
        except ValueError as e:self.note(str(e),True);self.show("instance");return
        self.launching=True;self.start.configure(state="disabled",text="正在准备…")
        self.game_state.configure(text="正在检查游戏文件")
        def failed(message):
            self.launching=False;self.start.configure(state="normal",text="离线启动   →");self.game_state.configure(text="启动未完成");self.note(message,True)
        custom_uuid=self.values['uuid'].get().strip()
        self.task(lambda:launch(root,version,java,name,run or None,memory,custom_uuid=custom_uuid),self.started,failed)

    def started(self,process):
        self.launching=False;self.process=process;self.start.configure(text="游戏运行中")
        self.game_state.configure(text="游戏已启动");self.note(f"游戏进程 {process.pid} 已启动")

    def poll_game(self):
        if self.process and self.process.poll() is not None:
            code=self.process.returncode;self.process=None
            self.start.configure(state="disabled" if self.shared else "normal",text="离线启动   →")
            self.game_state.configure(text="游戏已结束")
            self.note(f"游戏进程结束，返回码 {code}；详细日志在运行目录 .aetherloom/logs")
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

    def create_room(self,existing=None):
        if self.shared or (self.process and self.process.poll() is None):self.note('请先保存退出游戏',True);return
        binding=self.current_binding()
        if not binding:return
        selected=filedialog.askdirectory(parent=self,title='选择要发布的世界（包含level.dat）',initialdir=str(Path(binding['run'])/'saves'))
        if not selected:return
        world=Path(selected).resolve()
        if (world/'.aetherloom/pending-session.json').exists():self.note('此世界有未处理的Host会话，请先恢复，禁止重新发布覆盖',True);return
        if not (world/'level.dat').is_file() or world.parent!=Path(binding['run']).resolve()/'saves':
            self.note('请选择当前运行目录 saves 下包含 level.dat 的世界目录',True);return
        binding['world']=str(world)
        name=existing.get('name') if existing else ctk.CTkInputDialog(text='共享房间名称',title='发布共同世界').get_input()
        if not name:return
        from .cloud import API,CloudWorld,LeaseGuard
        api=API(self.server_url,self.token)
        def publish():
            if existing:
                if existing.get('head'):raise ValueError('已有权威存档，请使用恢复候选审批，不能直接覆盖')
                room=existing['id']
                api('/api/rooms/'+room,dict(name=name,environment=encode(describe(binding['root'],binding['version'])),world=world.name),method='PATCH')
            else:room=api('/api/rooms',dict(name=name,environment=encode(describe(binding['root'],binding['version'])),world=world.name))['id']
            self.events.put((lambda _:self.note('正在发布 '+name+'，请勿打开此世界'),None,'notification'))
            lease=api('/api/rooms/'+room+'/claim',{})
            guard=LeaseGuard(api,room,lease)
            try:
                from .shared_session import repair
                from .launcher import offline_uuid
                repair(world,binding['java'],game_uuid(binding['name'],binding.get('uuid')))
                version=CloudWorld(api,self.settings.path.parent/'cache').upload(room,world,guard.lease,None)
                return room,version
            except Exception:
                # Creation failed before any managed game launch; safe to release.
                try:api('/api/rooms/'+room+'/cancel',guard.lease)
                except Exception:pass
                raise
            finally:guard.close()
        def done(result):
            self.bindings[result[0]]=binding;self.save();self.note('共同存档发布成功');self.rooms()
        self.task(publish,done)

    def current_binding(self):
        b={k:self.values[k].get().strip() for k in ('root','run','version','java','name','memory','uuid')}
        try:game_uuid(b['name'],b['uuid'])
        except ValueError as e:self.note(str(e),True);return None
        if not b['root'] or not b['java'] or b['version']=='尚未选择':
            self.note('先在本地游戏中定位游戏目录、版本和Java',True);self.show('instance');return None
        b['run']=b['run'] or b['root']
        return b

    def bind_room(self,room):
        b=self.current_binding()
        if not b:return
        try:validate(describe(b['root'],b['version']),room.get('environment'))
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
        dialog=ctk.CTkToplevel(self);dialog.title('管理共享房间');dialog.geometry('520x420');dialog.configure(fg_color=BG);dialog.transient(self)
        self.label(dialog,room.get('name') or room['id'],19,bold=True).pack(anchor='w',padx=24,pady=(24,12))
        name=ctk.CTkEntry(dialog,height=40,fg_color=CARD,border_color=BORDER);name.insert(0,room.get('name') or room['id']);name.pack(fill='x',padx=24,pady=8)
        mode=ctk.CTkOptionMenu(dialog,values=['AUTO','RELAY','DIRECT'],fg_color=CARD,button_color=PRIMARY,height=38);mode.set(room.get('mode') or 'AUTO');mode.pack(fill='x',padx=24,pady=8)
        def saved(_):dialog.destroy();self.rooms();self.note('房间配置已更新')
        self.button(dialog,'保存名称和连接策略',lambda:self.cloud_task('/api/rooms/'+room['id'],saved,{'name':name.get(),'mode':mode.get()},method='PATCH'),True,width=220).pack(anchor='w',padx=24,pady=8)
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
        if self.shared or self.launching or (self.process and self.process.poll() is None):self.note('已有游戏或共享任务运行，请先退出',True);return
        if room['id'] not in self.bindings:self.bind_room(room);return
        recovery=False
        if room.get('host') and room['expires']<=time.time():
            recovery=messagebox.askyesno('上一位Host异常离线','上一会话没有完成最终上传。\n是否明确使用最近已确认的云端版本接管？\n旧Host未上传的进度需要随后通过恢复审批处理。',parent=self)
            if not recovery:return
        from .shared_session import SharedSession
        self.start_session(SharedSession,room,recovery)

    def inspect_room(self,room):
        if self.shared or self.launching or (self.process and self.process.poll() is None):self.note('请先退出游戏及当前任务',True);return
        if not messagebox.askyesno('离线恢复检查','保留旧Host原始存档，复制一份进行离线检查。\n不开LAN、不占公共Host。正常退出后上传不可变候选，等待Owner或实例管理员审批。\n检查副本需要额外磁盘空间，继续？',parent=self):return
        from .shared_session import OfflineInspection
        self.start_session(OfflineInspection,room)

    def start_session(self,session_type,room,recovery=False):
        def notify(kind,value):
            def apply(_):
                if kind=='process':self.started(value)
                elif kind=='network':self.network_status(value)
                else:self.note(value)
            self.events.put((apply,None,'notification'))
        self.selected_room=room['id'];self.save()
        self.shared=session_type(self.server_url,self.token,self.settings.path.parent/'cache',room['id'],dict(self.bindings[room['id']]),notify,recovery)
        session=self.shared
        self.network_rows.clear()
        for widget in self.network_list.winfo_children():widget.destroy()
        self.launching=True;self.online.configure(state='disabled',text='在线准备中…');self.start.configure(state='disabled')
        def finished(_):
            self.shared=None;self.launching=False
            self.online.configure(state='normal',text='在线启动   →')
            self.start.configure(state='normal' if not self.process or self.process.poll() is not None else 'disabled',text='离线启动   →')
            self.rooms()
        def failed(error):finished(None);self.note(error,True)
        self.task(lambda:asyncio.run(session.run()),finished,failed)

    def remember_profile(self):
        if self.profile_key:
            self.profiles[self.profile_key]={k:self.values[k].get() for k in ('run','java','memory','name','uuid')}

    def select_version(self,save=True):
        self.remember_profile()
        previous=self.profile_key
        self.profile_key=self.values['root'].get()+'|'+self.values['version'].get()
        profile=self.profiles.get(self.profile_key)
        if profile:
            self.values['uuid'].set(profile.get('uuid',''))
            for key,value in profile.items():
                if key in self.values:self.values[key].set(value)
        else:
            if previous and previous!=self.profile_key:self.values['uuid'].set('')
            if previous and previous!=self.profile_key or self.values['run'].get()==self.auto_run:self.values['run'].set('')
            self.suggest_run()
        root,version=self.values['root'].get(),self.values['version'].get()
        def discover():
            from .launcher import manifest
            required=manifest(Path(root),version).get('javaVersion',{}).get('majorVersion',17)
            return discover_java(root,required)
        def found(paths):
            if root!=self.values['root'].get() or version!=self.values['version'].get():return
            self.java_menu.configure(values=paths or ['未发现 Java，请使用浏览手动指定'])
            current=self.values['java'].get()
            if paths and (not current or not profile):
                self.values['java'].set(paths[0])
                self.note('已在游戏目录内发现 Java：'+paths[0])
            elif not current:self.note('所选游戏目录内未找到合适 Java，请在启动参数中手动指定',True)
            if save:self.save()
        self.task(discover,found,lambda error:event('java.discovery.failed',error=error))
        self.refresh_summary()

    def select_room(self,room):
        self.selected_room=room['id'];self.save()
        self.note('在线实例已选中：'+room.get('name',room['id']))

    def start_online(self):
        if not self.token:self.show('cloud');self.note('在线启动需要登录软件账号',True);return
        room=self.room_items.get(self.selected_room)
        if not room:self.show('cloud');self.note('请在共享世界选择一个在线实例',True);return
        self.play_room(room)

    def auto_refresh(self):
        if self.token and not self.login_busy:self.rooms()
        self.after((5000 if self.page in ('cloud','home') else 15000)*2**self.refresh_failures,self.auto_refresh)

    def build_network(self):
        p=self.pages['network']
        self.heading(p,'联机状态','显示实际流状态、P2P 打洞与中继回退；控制通道不等于游戏直连。')
        self.network_list=ctk.CTkScrollableFrame(p,fg_color=CARD)
        self.network_list.pack(fill='both',expand=True)
        self.label(self.network_list,'尚未启动在线会话',13,MUTED).pack(anchor='w',padx=16,pady=16)

    def network_status(self,state):
        key=state.get('session_id','network')
        display={k:state[k] for k in ('peer','channel','mode','active_path','relay_ready','direct_ready','switch_phase','last_reason','relay_rtt_ms','direct_rtt_ms','direct_endpoint','attempt','stage') if k in state}
        event('network.state',stream=key,**display)
        if key not in self.network_rows:
            row=self.label(self.network_list,'',12,MUTED,justify='left',wraplength=650)
            row.pack(fill='x',padx=16,pady=10);self.network_rows[key]=row
        titles={'peer':'对端','channel':'通道','mode':'策略','active_path':'当前路径','relay_ready':'中继就绪','direct_ready':'直连验证','switch_phase':'迁移阶段','last_reason':'原因','relay_rtt_ms':'中继 RTT / ms','direct_rtt_ms':'直连 RTT / ms','direct_endpoint':'直连端点','attempt':'打洞轮次','stage':'打洞进度'}
        self.network_rows[key].configure(text='流 '+str(key)[:12]+'\n'+'  ·  '.join(titles[k]+'：'+str(v) for k,v in display.items()))

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

