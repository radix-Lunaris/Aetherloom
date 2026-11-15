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
from .launcher import launch, inside

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
        self.events=queue.Queue()
        self.pending=0
        self.process=None
        self.token=""
        self.server_url=""
        self.page="home"
        self.logs=[]
        self.launching=False
        self.login_busy=False
        data=self.settings.data
        base=Path(sys.executable).parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parent.parent
        bundled=base/"runtime"/"bin"/("java.exe" if os.name=="nt" else "java")
        saved_java=data.get("java","")
        self.values={key:tk.StringVar(value=str(data.get(key,default))) for key,default in
            [("root",""),("run",""),("name","Player"),("version","尚未选择"),("memory",4096),
             ("url","https://artherlink.superyk7hero.online"),("username","")]}
        self.values["java"]=tk.StringVar(value=saved_java if saved_java and Path(saved_java).is_file() else str(bundled) if bundled.exists() else "")
        self.password=tk.StringVar()
        self.grid_rowconfigure(0,weight=1)
        self.grid_columnconfigure(1,weight=1)
        self.sidebar=ctk.CTkFrame(self,width=216,corner_radius=0,fg_color=SIDE)
        self.sidebar.grid(row=0,column=0,sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_rowconfigure(7,weight=1)
        self.label(self.sidebar,"A",size=30,color=ACCENT,bold=True).grid(row=0,column=0,sticky="w",padx=28,pady=(30,4))
        self.label(self.sidebar,"Aetherloom",size=21,bold=True).grid(row=1,column=0,sticky="w",padx=28)
        self.label(self.sidebar,"让世界，继续。",size=12,color=MUTED).grid(row=2,column=0,sticky="w",padx=28,pady=(4,34))
        self.nav={}
        for row,(key,title) in enumerate([("home","开始游戏"),("instance","实例配置"),("cloud","共享世界"),("logs","运行记录")],3):
            b=ctk.CTkButton(self.sidebar,text=title,anchor="w",width=176,height=44,
                corner_radius=8,fg_color="transparent",hover_color="#252633",
                text_color=MUTED,font=self.font(14),command=lambda k=key:self.show(k))
            b.grid(row=row,column=0,padx=20,pady=4)
            self.nav[key]=b
        foot=ctk.CTkFrame(self.sidebar,fg_color="#20212D",corner_radius=10)
        foot.grid(row=8,column=0,padx=20,pady=(20,14),sticky="ew")
        self.label(foot,"离线游戏身份",size=12,color=ACCENT).pack(anchor="w",padx=14,pady=(12,2))
        self.identity=self.label(foot,self.values["name"].get(),size=14,bold=True)
        self.identity.pack(anchor="w",padx=14,pady=(0,12))
        self.label(self.sidebar,"v0.1 · 开发版",size=11,color="#696C81").grid(row=9,column=0,sticky="w",padx=28,pady=(0,24))
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
        self.build_logs()
        self.load_versions(silent=True)
        self.show("home")
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
        self.heading(p,"开始你的下一段旅程","选择本地实例，准备好就出发。")
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
        self.instance_hint=self.label(left,"到实例配置中选择 .minecraft 目录",12,MUTED)
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
        self.start=self.button(bottom,"启动游戏   →",self.start_game,primary=True,width=190)
        self.start.pack(side="right",padx=22,pady=20)

    def build_instance(self):
        p=self.pages["instance"]
        self.heading(p,"实例配置","只访问你选定的目录；已有游戏文件原地使用。")
        scroll=ctk.CTkScrollableFrame(p,fg_color="transparent")
        scroll.pack(fill="both",expand=True)
        scroll.grid_columnconfigure(0,weight=1)
        c=self.card(scroll);c.grid(row=0,column=0,sticky="ew",pady=(0,16));c.grid_columnconfigure(0,weight=1)
        self.label(c,"游戏实例",17,bold=True).grid(row=0,column=0,sticky="w",padx=22,pady=(18,10))
        self.path_row(c,1,"游戏根目录","root",False)
        self.label(c,"游戏版本",12,MUTED).grid(row=3,column=0,sticky="w",padx=22,pady=(14,6))
        vr=ctk.CTkFrame(c,fg_color="transparent");vr.grid(row=4,column=0,sticky="ew",padx=22,pady=(0,22));vr.grid_columnconfigure(0,weight=1)
        self.version_menu=ctk.CTkOptionMenu(vr,variable=self.values["version"],values=["尚未选择"],height=40,
            fg_color="#282A3A",button_color="#373A50",button_hover_color="#474B66",font=self.font(13),
            command=lambda _:self.save())
        self.version_menu.grid(row=0,column=0,sticky="ew")
        self.button(vr,"刷新版本",self.load_versions,width=100).grid(row=0,column=1,padx=(12,0))
        c=self.card(scroll);c.grid(row=1,column=0,sticky="ew",pady=(0,16));c.grid_columnconfigure(0,weight=1)
        self.label(c,"启动参数",17,bold=True).grid(row=0,column=0,sticky="w",padx=22,pady=(18,10))
        row=ctk.CTkFrame(c,fg_color="transparent");row.grid(row=1,column=0,sticky="ew",padx=22,pady=(0,12));row.grid_columnconfigure((0,1),weight=1)
        for col,key,title in [(0,"name","离线玩家名称"),(1,"memory","最大内存 / MiB")]:
            f=ctk.CTkFrame(row,fg_color="transparent");f.grid(row=0,column=col,sticky="ew",padx=(0,10) if col==0 else (10,0))
            self.label(f,title,12,MUTED).pack(anchor="w",pady=(0,6));self.entry(f,key).pack(fill="x")
        self.path_row(c,2,"Java 可执行文件","java",True)
        self.path_row(c,4,"运行目录 · 可选，用于版本隔离","run",False)
        self.button(c,"保存配置",self.save,primary=True,width=120).grid(row=6,column=0,sticky="e",padx=22,pady=20)

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
        self.label(toolbar,"实例列表",17,bold=True).pack(side="left")
        self.cloud_buttons=[]
        for title,callback in [("刷新",self.rooms),("创建记录",self.create_room),("服务器概况",self.server_status)]:
            b=self.button(toolbar,title,callback,width=95);b.pack(side="right",padx=(8,0));b.configure(state="disabled");self.cloud_buttons.append(b)
        self.room_list=ctk.CTkScrollableFrame(p,fg_color=CARD,corner_radius=12,border_width=1,border_color=BORDER)
        self.room_list.pack(fill="both",expand=True)
        self.label(self.room_list,"登录后，这里会显示服务器中的实例。",13,MUTED).pack(padx=20,pady=28)
        self.label(p,"共享开服尚未开放 · 当前版本提供本地启动与云端查询。",11,MUTED).pack(anchor="w",pady=(12,0))

    def build_logs(self):
        p=self.pages["logs"];self.heading(p,"运行记录","查看启动与服务器连接的处理结果。")
        self.logbox=ctk.CTkTextbox(p,fg_color=CARD,border_color=BORDER,border_width=1,
            corner_radius=12,text_color="#C4C7D8",font=self.font(13))
        self.logbox.pack(fill="both",expand=True);self.logbox.configure(state="disabled")
        self.button(p,"清空记录",self.clear_logs,width=100).pack(anchor="e",pady=(12,0))

    def show(self,name):
        self.page=name;self.pages[name].tkraise()
        for key,b in self.nav.items():b.configure(fg_color="#302B49" if key==name else "transparent",text_color=ACCENT if key==name else MUTED)
        self.breadcrumb.configure(text="工作台  /  "+{"home":"开始游戏","instance":"实例配置","cloud":"共享世界","logs":"运行记录"}[name])
        self.refresh_summary()

    def refresh_summary(self):
        version=self.values["version"].get()
        self.instance_title.configure(text=(version[:32] if version!="尚未选择" else "尚未绑定"))
        self.instance_hint.configure(text="已选择本地游戏目录" if self.values["root"].get() else "到实例配置中选择 .minecraft 目录")
        self.identity.configure(text=self.values["name"].get() or "Player")
        self.game_detail.configure(text=f"{self.values['name'].get()}  ·  {self.values['memory'].get()} MiB" if version!="尚未选择" else "先选择一个完整的本地游戏实例")

    def note(self,message,error=False):
        self.notice.configure(text=message[:115],text_color="#F0AF9C" if error else MUTED)
        line=time.strftime("%H:%M:%S")+"  "+message
        self.logs.append(line)
        self.logbox.configure(state="normal");self.logbox.insert("end",line+"\n");self.logbox.see("end");self.logbox.configure(state="disabled")

    def clear_logs(self):
        self.logs.clear();self.logbox.configure(state="normal");self.logbox.delete("1.0","end");self.logbox.configure(state="disabled")

    def save(self):
        try:self.settings.save({k:v.get().strip() for k,v in self.values.items()})
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
            self.refresh_summary()
            if not silent:self.note(f"找到 {len(versions)} 个已安装版本")
        except (OSError,ValueError) as e:
            if not silent:self.note("无法读取版本："+str(e),True)

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
            self.pending-=1
            try:callback(result)
            except Exception as e:self.fail(str(e))
        self.after(100,self.drain)

    def fail(self,message):
        self.note(message,True)

    def start_game(self):
        if self.launching or (self.process and self.process.poll() is None):return
        if not self.save():return
        try:
            root,version,java,name,run,memory=[self.values[k].get().strip() for k in ("root","version","java","name","run","memory")]
            if not root or not java or version=="尚未选择":raise ValueError("请先在实例配置中选择游戏目录、版本和 Java")
            memory=int(memory)
            if not 512<=memory<=65536:raise ValueError("内存范围为 512—65536 MiB")
        except ValueError as e:self.note(str(e),True);self.show("instance");return
        self.launching=True;self.start.configure(state="disabled",text="正在准备…")
        self.game_state.configure(text="正在检查游戏文件")
        def failed(message):
            self.launching=False;self.start.configure(state="normal",text="启动游戏   →");self.game_state.configure(text="启动未完成");self.note(message,True)
        self.task(lambda:launch(root,version,java,name,run or None,memory),self.started,failed)

    def started(self,process):
        self.launching=False;self.process=process;self.start.configure(text="游戏运行中")
        self.game_state.configure(text="游戏已启动");self.note(f"游戏进程 {process.pid} 已启动")

    def poll_game(self):
        if self.process and self.process.poll() is not None:
            code=self.process.returncode;self.process=None
            self.start.configure(state="normal",text="再次启动   →")
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

    def cloud_task(self,path,done,body=None):
        if not self.token:self.note("请先登录服务器",True);return
        url,token=self.server_url,self.token
        self.task(lambda:self.request(url,token,path,body),done)

    def rooms(self):
        def done(items):
            for child in self.room_list.winfo_children():child.destroy()
            if not items:self.label(self.room_list,"暂无实例 · 你可以创建一个云端记录。",13,MUTED).pack(pady=30);return
            for item in items:
                row=ctk.CTkFrame(self.room_list,fg_color="#232532",corner_radius=8);row.pack(fill="x",padx=8,pady=5)
                self.label(row,item["id"][:12]+"…",14,bold=True).pack(side="left",padx=14,pady=14)
                self.label(row,"所有者 "+item["owner"],12,MUTED).pack(side="left",padx=12)
                self.label(row,("Host "+item["host"]) if item.get("host") else "当前无 Host",12,ACCENT).pack(side="right",padx=14)
            self.note(f"已加载 {len(items)} 个实例")
        self.cloud_task("/api/rooms",done)

    def create_room(self):
        if messagebox.askyesno("创建实例记录","当前版本仅创建云端记录，尚不能绑定存档或自动开服。继续？",parent=self):
            self.cloud_task("/api/rooms",lambda _:self.rooms(),{})

    def server_status(self):
        def done(r):
            self.note(f"服务器：磁盘剩余 {r['disk_free']/1024**3:.2f} GiB / {r['disk_total']/1024**3:.2f} GiB · 账号 {r['accounts']} · 实例 {r['rooms']}")
        self.cloud_task("/api/status",done)

    def close(self):
        if self.pending:self.note("正在处理请求，请稍后再关闭");return
        self.save();self.destroy()

def main():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("blue")
    window=Window()
    if "--smoke-test" in sys.argv:window.after(1000,window.destroy)
    window.mainloop()

if __name__=="__main__":main()

