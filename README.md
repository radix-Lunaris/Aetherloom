# Aetherloom

以自托管云存档为中心，让玩家轮流托管同一个Minecraft世界，整合离线游戏启动、联机与存档接续。

开发在dev分支，main交付本次已验证的v0.1.0里程碑。客户端使用CustomTkinter，定位用户已准备的完整游戏环境并独立启动，不下载游戏、不调用外部启动器。首个完整目标为Windows x64 / Minecraft1.20.1 / Forge47.4.22。

服务端使用FastAPI与独立MySQL Docker容器。统一软件账号、房间与成员管理，SHA-256增量版本、唯一Host租约、恢复候选审批；CraftLink AUTO传输核心已接入TLS WebSocket中继与认证单端点UDP打洞。Forge Bridge已构建，负责受管LAN与正常保存事件。

客户端业务HTTPS47192；面板HTTPS38443加随机安全路径；443不承载业务。

当前 dev 将首页分为离线／在线启动：无需登录即可离线进入主菜单，在线按钮接续选中的共享房间。在线退出后自动关闭游戏并处理最终保存；提供联机诊断、自动刷新、账号下拉选择和本地多版本配置 Beta。客户端不再捆绑 Java，优先从用户指定游戏根目录发现，未找到时手动指定。此轮服务端改动需另行部署，未自动更新生产环境。

使用见[PLAY.md](PLAY.md)，构建见[BUILD.md](BUILD.md)，Docker部署见[DEPLOY.md](DEPLOY.md)。进度和实测边界见[CHECKPOINT.md](CHECKPOINT.md)。已通过同机双身份A→B→A接管与双进程经ECS自动加入，物品栏/经验保持独立。不同电脑、不同NAT及更广Mods组合仍待验收。
