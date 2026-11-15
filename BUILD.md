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
Java来源构建信息见runtime/release。Qt/PySide6来源：https://code.qt.io/cgit/pyside/pyside-setup.git/ （6.10.1）；Qt6.10.1来源：https://download.qt.io/archive/qt/6.10/6.10.1/single/ 。
PySide6与Qt动态链接，发行包包含可替换的_internal目录，不要只复制EXE。
源代码：https://github.com/radix-Lunaris/Aetherloom/tree/dev 。项目按GPLv3交付。

Docker构建方式见DEPLOY.md；无需Windows构建依赖。
