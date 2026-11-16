# Aetherloom

以自托管云存档为中心，让玩家轮流托管同一个Minecraft世界，整合离线游戏启动、联机与存档接续。

开发在dev分支，main保留验收后的总交付；每次迭代从已通过验证的提交发布GitHub Release。客户端使用CustomTkinter，定位用户已准备的完整游戏环境并独立启动，不下载游戏、不调用外部启动器。首个完整目标为Windows x64 / Minecraft1.20.1 / Forge47.4.22。

服务端使用FastAPI与独立MySQL Docker容器。统一软件账号、房间与成员管理，SHA-256增量版本、唯一Host租约、恢复候选审批；CraftLink AUTO传输核心已接入TLS WebSocket中继与认证单端点UDP打洞。Forge Bridge已构建，负责受管LAN与正常保存事件。

客户端业务HTTPS47192；面板HTTPS38443加随机安全路径；443不承载业务。

当前 dev 将首页分为离线／在线启动：无需登录即可离线进入主菜单，在线按钮接续选中的共享房间。在线退出后自动关闭游戏并处理最终保存；提供联机诊断、自动刷新、账号下拉选择和本地多版本配置 Beta。客户端不捆绑 Java：自动发现系统及游戏运行时，按实例选择稳定匹配版本；缺失时可一键下载官方 Temurin，并校验 SHA-256，或手动指定。线上服务端已部署 ec22e7c；本轮 Java 管理只更新客户端，无需重新部署服务器。

使用见[PLAY.md](PLAY.md)，构建见[BUILD.md](BUILD.md)，Docker部署见[DEPLOY.md](DEPLOY.md)。进度和实测边界见[CHECKPOINT.md](CHECKPOINT.md)。已通过同机双身份A→B→A接管与双进程经ECS自动加入，物品栏/经验保持独立。不同电脑、不同NAT及更广Mods组合仍待验收。

构建仅输出到 `release/`：独立单文件 `Aetherloom.exe`、`Aetherloom-Server.tar.gz` 和校验和，不再另打客户端ZIP或保留dist副本。见BUILD.md。

联机状态持续显示会话阶段和等待玩家状态；顶部进度条展示发布、上传、下载及Java安装进度，提交成功后才显示100%。Bridge已作为[独立GPLv3项目](https://github.com/radix-Lunaris/Aetherloom-Bridge)公开，应用内源码由bridge/SOURCE.json固定；当前只承诺上述经过验证的游戏／加载器组合。

实验分支experiment/java-agent提供默认关闭的Java Agent控制原型，详见AGENT_EXPERIMENT.md。此分支发布Prerelease，不替代v0.3.0稳定版；当前在线环境仍限定1.20.1/Forge47.4.22。
