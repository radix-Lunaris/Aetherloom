# Aetherloom

以自托管云存档为中心，让玩家轮流托管同一个 Minecraft 世界，自动完成游戏启动、联机与存档接续。

开发分支 dev；main 仅接收验收交付。当前提供Windows离线GUI启动器与Docker控制API开发包，尚未完成真实游戏Hop。

Python 3.11+：`python -m unittest discover -s tests -v`。

双击发行包内Aetherloom.exe；配套Java17，无需安装HMCL/PCL。用户提供完整.minecraft目录，仅支持离线游戏身份。

服务端上传dist/Aetherloom-Server.zip；Docker构建和初始化步骤详见DEPLOY.md。自动Hop、Bridge、AUTO仍待接通，不可用当前包管理正式共同世界。

详见 PLAN.md、CHECKPOINT.md。
