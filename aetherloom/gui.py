"""Offline-only desktop. Background workers keep preflight and HTTP off the UI thread."""
import json
import os
from pathlib import Path
import sys
import urllib.request
import urllib.error
from PySide6.QtCore import QObject, QThread, Signal, Slot, QSettings, QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import (QApplication,QMainWindow,QWidget,QVBoxLayout,QHBoxLayout,
    QFormLayout,QLineEdit,QPushButton,QFileDialog,QComboBox,QSpinBox,QPlainTextEdit,
    QTabWidget,QLabel,QMessageBox,QTableWidget,QTableWidgetItem)
from .launcher import launch, inside

class Worker(QObject):
    done=Signal(object)
    failed=Signal(str)
    def __init__(self,fn,callback):
        super().__init__()
        self.fn=fn
        self.callback=callback
    def run(self):
        try: self.done.emit((self.callback,self.fn()))
        except Exception as e: self.failed.emit(str(e))

class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Aetherloom · 离线启动与共享世界")
        self.resize(980,740)
        self.settings=QSettings("Aetherloom","Desktop")
        self.jobs=[]
        self.token=""
        self.server_url=""
        self.process=None
        tabs=QTabWidget()
        self.setCentralWidget(tabs)
        local=QWidget()
        layout=QVBoxLayout(local)
        title=QLabel("Aetherloom")
        title.setStyleSheet("font-size:30px;font-weight:700;color:#86d9d1")
        layout.addWidget(title)
        layout.addWidget(QLabel("选择已准备好的游戏目录，直接启动。游戏账号仅使用离线身份。"))
        form=QFormLayout()
        self.root=QLineEdit(self.settings.value("root",""))
        self.run_dir=QLineEdit(self.settings.value("run",""))
        base=Path(sys.executable).parent if getattr(sys,"frozen",False) else Path(__file__).resolve().parent.parent
        default_java=base/"runtime"/"bin"/"java.exe"
        self.java=QLineEdit(self.settings.value("java",str(default_java) if default_java.exists() else ""))
        self.name=QLineEdit(self.settings.value("name","Player"))
        self.version=QComboBox()
        self.memory=QSpinBox()
        self.memory.setRange(512,65536)
        self.memory.setSingleStep(512)
        self.memory.setValue(int(self.settings.value("memory",4096)))
        self.memory.setSuffix(" MiB")
        for label,field,isfile in [("游戏根目录",self.root,False),("运行目录（留空使用根目录）",self.run_dir,False),("Java 路径",self.java,True)]:
            row=QWidget()
            h=QHBoxLayout(row)
            h.setContentsMargins(0,0,0,0)
            h.addWidget(field)
            button=QPushButton("选择")
            button.clicked.connect(lambda checked=False,f=field,file=isfile:self.pick(f,file))
            h.addWidget(button)
            form.addRow(label,row)
        form.addRow("游戏版本",self.version)
        refresh=QPushButton("读取所选目录的版本")
        refresh.clicked.connect(self.versions)
        form.addRow("",refresh)
        form.addRow("离线玩家名称",self.name)
        form.addRow("最大游戏内存",self.memory)
        layout.addLayout(form)
        self.start=QPushButton("启动游戏")
        self.start.clicked.connect(self.start_game)
        layout.addWidget(self.start)
        self.game_status=QLabel("尚未启动")
        layout.addWidget(self.game_status)
        layout.addStretch()
        tabs.addTab(local,"本地游戏")
        cloud=QWidget()
        cloud_layout=QVBoxLayout(cloud)
        cloud_layout.addWidget(QLabel("软件账号用于访问自托管 ECS，与游戏离线身份无关。"))
        cf=QFormLayout()
        self.url=QLineEdit(self.settings.value("url","http://127.0.0.1:8765"))
        self.username=QLineEdit(self.settings.value("username",""))
        self.password=QLineEdit()
        self.password.setEchoMode(QLineEdit.Password)
        cf.addRow("服务器地址",self.url)
        cf.addRow("软件账号",self.username)
        cf.addRow("软件密码",self.password)
        cloud_layout.addLayout(cf)
        row=QHBoxLayout()
        for text,callback in [("登录",self.login),("刷新实例",self.rooms),("创建实例记录",self.create_room),("服务器状态",self.server_status)]:
            button=QPushButton(text);button.clicked.connect(callback);row.addWidget(button)
        cloud_layout.addLayout(row)
        self.cloud_status=QLabel("未登录")
        cloud_layout.addWidget(self.cloud_status)
        self.table=QTableWidget(0,4)
        self.table.setHorizontalHeaderLabels(["实例ID","所有者","Host","状态"])
        self.table.horizontalHeader().setStretchLastSection(True)
        cloud_layout.addWidget(self.table)
        cloud_layout.addWidget(QLabel("此构建提供控制服务连接；自动 Hop、Bridge 和 AUTO 隧道仍未接通。"))
        tabs.addTab(cloud,"云服务")
        logpage=QWidget();ll=QVBoxLayout(logpage)
        self.log=QPlainTextEdit();self.log.setReadOnly(True);ll.addWidget(self.log)
        tabs.addTab(logpage,"运行日志")
        self.setStyleSheet("""
QWidget { background:#15232c;color:#e0e9ef;font-size:14px; }
QLineEdit,QComboBox,QSpinBox,QPlainTextEdit,QTableWidget {background:#203440;border:1px solid #38505d;padding:7px;border-radius:5px;}
QPushButton {background:#286b71;padding:10px;border-radius:6px;}
QPushButton:disabled {background:#34444c;color:#81909a;}
QTabBar::tab {padding:12px 24px;} QLabel {padding:4px;}
""")
        self.timer=QTimer(self);self.timer.timeout.connect(self.poll);self.timer.start(1500)
        if self.root.text(): self.versions()

    def pick(self,field,file):
        value=QFileDialog.getOpenFileName(self,"选择 Java","", "Java (java.exe);;全部文件 (*)")[0] if file else QFileDialog.getExistingDirectory(self,"选择目录",field.text())
        if value:
            field.setText(value)
            if field is self.root:self.versions()

    def versions(self):
        self.version.clear()
        try:
            root=Path(self.root.text()).resolve()
            versions=inside(root,"versions")
            for p in sorted(versions.iterdir()):
                if p.is_dir() and (p/(p.name+".json")).is_file():
                    self.version.addItem(p.name)
            self.version.setCurrentText(self.settings.value("version",self.version.currentText()))
        except OSError as e:self.error(str(e))

    def save(self):
        for key,value in [("root",self.root.text()),("run",self.run_dir.text()),("java",self.java.text()),
            ("name",self.name.text()),("version",self.version.currentText()),("memory",self.memory.value()),
            ("url",self.url.text()),("username",self.username.text())]:
            self.settings.setValue(key,value)
        self.settings.sync()

    def task(self,fn,done):
        thread=QThread(self);worker=Worker(fn,done);worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.done.connect(self.completed);worker.failed.connect(self.error)
        worker.done.connect(thread.quit);worker.failed.connect(thread.quit)
        thread.finished.connect(worker.deleteLater)
        self.jobs.append((thread,worker))
        thread.finished.connect(lambda:self.finish_job(thread))
        thread.start()

    @Slot(object)
    def completed(self,payload):
        callback,result=payload
        callback(result)

    def finish_job(self,thread):
        self.jobs=[pair for pair in self.jobs if pair[0] is not thread]
        thread.deleteLater()

    @Slot(str)
    def error(self,message):
        self.log.appendPlainText(message)
        self.start.setEnabled(not self.process or self.process.poll() is not None)
        QMessageBox.warning(self,"Aetherloom",message)

    def start_game(self):
        self.save()
        if not self.root.text() or not self.java.text() or not self.version.currentText():
            self.error("请选择完整游戏目录、版本和 Java。");return
        if self.process and self.process.poll() is None:
            self.error("本窗口已有游戏运行中。");return
        values=(self.root.text(),self.version.currentText(),self.java.text(),self.name.text(),self.run_dir.text() or None,self.memory.value())
        self.start.setEnabled(False)
        self.game_status.setText("正在检查游戏文件并准备启动…")
        self.task(lambda:launch(*values),self.started)

    def started(self,process):
        self.process=process
        self.game_status.setText(f"游戏运行中 · PID {process.pid}")
        self.log.appendPlainText("已直接启动游戏进程。")

    def poll(self):
        if self.process and self.process.poll() is not None:
            self.game_status.setText(f"游戏进程结束 · 返回码 {self.process.returncode}（不能据此判定世界正常保存）")
            self.start.setEnabled(True);self.process=None

    def request(self,path,body=None):
        url=self.server_url
        if not url.startswith(("http://","https://")):raise ValueError("需要 http:// 或 https:// 地址")
        headers={"Content-Type":"application/json"}
        if self.token:headers["Authorization"]="Bearer "+self.token
        req=urllib.request.Request(url+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        try:
            with urllib.request.urlopen(req,timeout=20) as r:return json.load(r)
        except urllib.error.HTTPError as e:
            try:message=json.load(e).get("detail",str(e))
            except Exception:message=str(e)
            raise ValueError(str(message))

    def login(self):
        self.save()
        self.server_url=self.url.text().strip().rstrip("/")
        self.token=""
        body={"username":self.username.text(),"password":self.password.text()}
        def done(result):
            self.token=result["token"];self.password.clear()
            self.cloud_status.setText("已登录："+result["username"]+" · "+result["role"])
            self.rooms()
        self.task(lambda:self.request("/api/login",body),done)

    def rooms(self):
        def done(rows):
            self.table.setRowCount(len(rows))
            for i,row in enumerate(rows):
                for j,key in enumerate(["id","owner","host","state"]):
                    self.table.setItem(i,j,QTableWidgetItem(str(row.get(key) or "—")))
            self.table.resizeColumnsToContents()
        self.task(lambda:self.request("/api/rooms"),done)

    def create_room(self):
        if QMessageBox.question(self,"创建实例记录","创建一个空的云实例记录？本构建尚不能绑定或上传世界。")!=QMessageBox.Yes:return
        self.task(lambda:self.request("/api/rooms",{}),lambda result:self.rooms())

    def server_status(self):
        self.task(lambda:self.request("/api/status"),lambda r:QMessageBox.information(self,"服务器状态",
            f"磁盘剩余 {r['disk_free']/1024**3:.2f} GiB / {r['disk_total']/1024**3:.2f} GiB\n账号 {r['accounts']} · 实例 {r['rooms']}"))

    def closeEvent(self,event):
        if self.jobs:
            QMessageBox.information(self,"任务运行中","请等待当前检查或请求结束后关闭。");event.ignore();return
        self.save();event.accept()

def main():
    app=QApplication(sys.argv)
    if sys.platform == 'win32':
        for filename in ('segoeui.ttf','msyh.ttc'):
            font=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/filename
            if font.exists():QFontDatabase.addApplicationFont(str(font))
        app.setFont(QFont('Microsoft YaHei',10))
    window=Window();window.show()
    if "--smoke-test" in sys.argv:
        QTimer.singleShot(500,app.quit)
    sys.exit(app.exec())

