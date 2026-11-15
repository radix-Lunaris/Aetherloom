# 构建发行包

Windows Python3.11：
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
powershell -ExecutionPolicy Bypass -File scripts/build-client.ps1
powershell -ExecutionPolicy Bypass -File scripts/package-server.ps1
```
客户端构建前，把Eclipse Temurin17 Windows x64 JRE解压到runtime/，保留NOTICE和legal/。
来源：https://adoptium.net/temurin/releases/?version=17 （本次17.0.21+9）
Java来源构建信息见runtime/release。CustomTkinter来源：https://github.com/TomSchimansky/CustomTkinter （5.2.2，MIT）。
客户端使用CustomTkinter 5.2.2，打包时收集其主题、字体和图片资源；发行包包含_internal目录，不要只复制EXE。
源代码：https://github.com/radix-Lunaris/Aetherloom/tree/dev 。项目按GPLv3交付。

Docker构建方式见DEPLOY.md；无需Windows构建依赖。

桌面流程检查：python scripts/smoke_desktop.py，使用临时实例和模拟进程，不启动真实游戏。软件配置写入本机LOCALAPPDATA/Aetherloom/settings.json，首次可读取旧Qt版本的注册表配置；不保存软件密码或登录令牌。
