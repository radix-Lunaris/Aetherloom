# 构建发行包

Windows Python3.11：
```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
# 设置JAVA_HOME为JDK17，先构建两个Java模块。
powershell -ExecutionPolicy Bypass -File scripts/build-playerdata.ps1
powershell -ExecutionPolicy Bypass -File scripts/build-bridge.ps1
powershell -ExecutionPolicy Bypass -File scripts/build-client.ps1
powershell -ExecutionPolicy Bypass -File scripts/package-server.ps1
```
客户端不再捆绑、下载或复制 Java。客户端会在已知 Java 安装位置、注册表、环境变量、用户 .jdks 和游戏／启动器的运行时专用目录有界发现，并实际探测版本与架构；也可手动指定。找不到时提供用户点击的一键官方运行时下载，默认安装到配置目录 java 下。下载目录不进入发行包，仍不要求构建机提供捆绑 JRE。
构建两个 Java 辅助模块仍需要构建机 JDK17（JAVA_HOME）；这是构建依赖，不进入客户端包。
CustomTkinter 来源：https://github.com/TomSchimansky/CustomTkinter （5.2.2，MIT）。
客户端使用CustomTkinter 5.2.2，打包时收集其主题、字体和图片资源；发行包包含_internal目录，不要只复制EXE。
源代码：https://github.com/radix-Lunaris/Aetherloom/tree/dev 。项目按GPLv3交付。

Docker构建方式见DEPLOY.md；无需Windows构建依赖。

桌面流程检查：python scripts/smoke_desktop.py，使用临时实例和模拟进程，不启动真实游戏。软件配置写入本机LOCALAPPDATA/Aetherloom/settings.json，首次可读取旧Qt版本的注册表配置；不保存软件密码或登录令牌。

Bridge使用Forge官方MDK的Gradle8.8包装器（Apache-2.0），ForgeGradle和官方1.20.1映射。玩家数据辅助模块仅引入shared-playerdata的MIT NBT核心，不引入全目录扫描器或轮询。assets下构建产物会随完整客户端复制；源码构建需先完成两个Java模块。
