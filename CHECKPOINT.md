# 实施检查点

## 界面重构：2026-11-16
- 用户要求客户端改为CustomTkinter；已移除桌面PySide6依赖，重写固定侧栏、本地启动首页、实例配置、云端连接与运行记录。
- 配置改为本机JSON，支持只读迁移旧Qt注册表设置；密码和令牌仅在内存；后台任务通过队列回到主线程更新界面。
- 网页面板采用同一深灰/紫色视觉，拆分登录、概况、实例与账号管理，适配手机；保留现有API与权限。
- 9项核心/API测试通过；浏览器登录、导航、临时预览开户刷新、手机宽度检查通过，无JavaScript错误。
- CustomTkinter源码与最终EXE启动检查通过；旧Qt安装包留在.local/backups；服务器保留旧镜像与面板归档。
- 新面板已Docker更新上线；真实HTTPS浏览器验证登录、指标、账号列表、退出；公开路径与未授权访问检查通过。证书、安全路径、账号与数据卷沿用。
- 新客户端为dist/Aetherloom/Aetherloom.exe及dist/Aetherloom-Windows.zip。自动Hop/Bridge/AUTO仍待完成。

## ECS正式部署：2026-11-16
- 用户明确授权部署后，已安装Docker/Compose、宿主Nginx、Certbot；部署目录/opt/aetherloom。
- HTTPS API443、面板38443+随机16位路径；后端仅127.0.0.1:8765。SSH18081保留。
- Let's Encrypt HTTP-01证书签发成功，至2027-02-13；certbot.timer和续期后Nginx重载钩子启用。
- 新增管理面板：管理员登录、内存/负载/磁盘/账号/实例统计、实例会话列表、账号列表及开户。
- Swagger默认关闭；API未登录401、普通用户管理403；登录限流；高位端口错误路径404，公开443不提供面板或开户入口。
- 9项本地测试通过。真实外网TLS验证通过：API健康200、面板正确路径200、错误路径404、未登录401、root登录和管理查询200。
- Docker Hub直连失败，使用Docker官方摘要锁定的Python3.11分发镜像；Python依赖锁版本，以Linux离线轮子构建成功。
- 访问资料仅在.local/deployment-access.json与.local/SERVER-HANDOFF.md，未提交。SSH口令不复制入仓库或镜像。
- 自动Hop、Bridge、AUTO、实例成员管理及完整恢复审批面板仍未交付，不把当前上线控制服务宣称为完整联机服务。

## 工作区迁移：2026-11-16
- 正式工作区：D:/Data_others/Aliyun-Server/上海华东2-书记宝宝-实例-Activity/codex。
- 项目目录：上述工作区下 Aetherloom/；保留 .git、.venv、runtime、dist、build、.local。
- 整体迁移前后10317个文件SHA256全部一致，总计1377571627字节。
- 迁移后修复虚拟环境激活路径和36个命令入口，检查软件已保存路径。
- 新路径8项测试全部通过；pip与PyInstaller入口可用。
- ECS仅只读检查，未安装/部署。域名artherlink.superyk7hero.online；计划目录/opt/aetherloom、API443、面板38443和16位随机路径，尚待实现及明确部署指令。
- 未提交的ECS只读检查资料、主机密钥记录完整保留在.local，不写入Git。
- 旧工作区CraftLink/MCsaves-sync继续作为参考；共同代码学习记录已复制到新工作区根目录。


## GUI/Docker交付更新
- 取消正版授权需求；游戏仅离线身份，软件账号保持独立。
- PySide6 GUI：手动目录/版本、隔离目录、Java、内存、启动、软件登录、实例查询、控制服务状态。
- 发行包含Temurin17 JRE与许可；游戏输出写入运行目录.aetherloom/logs。
- Dockerfile/Compose与DEPLOY.md；非root容器、命名卷、健康检查、资源限制。
- FastAPI账号认证、root初始化/CLI开户、实例/租约/提交API。会话口令仅保存在进程内存，密码PBKDF2。
- 8项测试通过，含真实Java17子进程、中文隔离路径、认证权限。GUI离屏启动与中文截图复查通过。
- 本机无Docker，CI加入容器构建与健康检查；以远端对应提交结果为准。
- 自动Hop、shared-playerdata/Bridge、AUTO与管理面板未完成；GUI云页只是控制API入口，不能开共享世界。
- 下文旧检查点描述保留为历史，其中GUI/HTTP/Java打包已完成，以本更新为准。
- Docker在GitHub Actions实际构建、非root启动、健康检查通过（977cb51与f55e9d7）。
- EXE初测发现打包器从PATH误收集的ICU DLL与Qt冲突；移除并使用Windows10/11系统ICU后EXE离屏启动退出码0。构建脚本已固化修复。
- 已修复Java17在英文Windows上的中文类路径编码问题：使用Windows原生短路径；路径无法表达且没有短路径时明确报错。
- 170aa0e对应远端CI全部通过：Windows测试、Ubuntu测试、Docker构建与健康检查。https://github.com/radix-Lunaris/Aetherloom/actions/runs/43722630250
- 交付文件：dist/Aetherloom-Windows.zip（附Java17）、dist/Aetherloom-Server.zip（Docker源码）。服务端上传清单和命令见DEPLOY.md。

## 已落地
- 从远端初始化提交克隆独立 Aetherloom 目录，建立 dev。
- 名称、计划、决策、GPLv3许可证、来源清单、跨Windows/Linux CI。
- 独立离线启动CLI：manifest继承、参数替换、libraries/assets检查、native解包、Java检查、直接启动。
- SQLite事务唯一Host、60s租约、epoch与父版本校验、独立恢复候选、Owner/manager恢复权限。
- SHA256分块快照与校验重组，无后台定期任务，保留spd_backup。

## 验证
6项unittest通过（Windows正常权限）。沙箱中os.replace遭拒，正常权限重跑通过。
新增原子块落盘补丁后全部6项测试再次通过；git diff --check通过。
没有真实游戏、Forge、双机或ECS实测。启动CLI尚未验证Forge47.4.22。

## 重要限制
这不是完成的首版，不能用于生产共同世界。
Authority是可信调用者的内部原语，尚无软件认证、HTTP接口、完整权限/审计、容量预留。
snapshot/materialize目前要求调用者保证世界已关闭；尚未集成OS游戏锁和Bridge。
materialize尚未处理云端删除文件、精确镜像、空目录与完整恢复备份；不是安全接管入口。
启动器暂仅离线身份，Java手动指定；native缓存清理、依赖哈希与旧资源格式兼容待完善。
尚未实现GUI、正版授权、shared-playerdata集成、Bridge、AUTO、完整编排、管理面板、安装与部署包。

## 下一步
1. 补启动器进程模拟测试、文件哈希与native ZIP限制，隔离缓存清理。
2. 获取shared-playerdata固定提交并保留MIT声明，接入单世界修复和冲突回归。
3. Forge Bridge及本地受保护协议，证明正常退出与锁释放。
4. HTTP认证和完整权限，世界锁/备份/精确checkout，AUTO适配与UI。
5. 获取用户准备的实际游戏目录，真实双机验证后才能合main。

远端描述修改未完成：当前连接未提供仓库元数据写接口，本机无gh。


## 2026-11-16 实质功能补齐（进行中）
- 用户保持现有CustomTkinter和Web样式，要求补齐账号、房间、真实联机。
- 离线启动补充clientid/auth_xuid等元变量；真实Java测试通过，未拿到用户实际游戏目录复测。
- CraftLink权限策略适配：root保护、admin/player、仅root任免admin、改名/改密/停用/删除、令牌撤销、玩家每自然月三次自助改名+改密、审计。
- 持久共享房间增加名称/环境/世界/模式、成员权限、转移Owner、删除；活动Host禁止删除房间，账号需先处理其拥有的房间。
- 11项本地回归测试通过。
- 服务端MySQL独立容器准备完成，迁移和备份执行中。客户端业务HTTPS使用47192；面板38443加原安全路径，443不承载业务。
- 尚未将UI房间记录误标为完整Hop；CraftLink AUTO与游戏Bridge仍需实际适配与验收。

- MySQL线上迁移通过：accounts=3,sessions=5,rooms=1，SQLite保留；control/mysql健康，外部HTTPS47192与原面板通过验证。
- Bridge Forge47.4.22完整编译/reobf成功，Java17辅助模块构建成功；尚无真实游戏双机验收。
- 已引入CraftLink未修改的AutoStream/AutoPeer/可靠UDP等传输源码（SOURCE.json含哈希与GPL许可）；统一软件认证接入TLS WebSocket中继，单成员共享UDP承载与独立流，AUTO在中继上先可用并后台尝试认证UDP打洞。
- 24项本地测试通过，包括上游流协议测试、真实WebSocket+UDP升级/多流/回退；发现连接关闭时ASGI重复close错误，已修正，需再次验证清理无错误。
- 正在补充单世界修复冲突测试、恢复审批、完整客户端包与第二次部署。


### 2026-11-16 持久化检查点：管理/网络已部署，游戏保存验收中
- 26项自动化测试已通过；后续增加了成员鉴权和Bridge错误回执，需最终重跑。
- MySQL独立临时库实测通过：模式、6位口令、8并发唯一Host、版本提交、改名冲突回滚、活动Host恢复保护、审计；临时库与授权已清理。
- 生产API已更新，HTTPS47192/WSS实际512KiB端到端往返通过，临时账号和房间已删除，原有房间未修改。
- Docker新目录受umask077影响无法由非root读取，已改COPY显式权限，并在up之前验证App工厂；先前失败更新已自动回滚，无数据覆盖。
- 用户提供实际游戏根：D:/Data_games/MC/PCL 正式版 2.8.12/.minecraft/versions/new/.minecraft，版本1.20.1-Forge（47.4.22）。检查已通过clientid参数，独立启动不调用外部启动器。
- 真实Minecraft：使用项目.local内独立运行目录和新测试世界；未加载或改动用户原有存档。已验证入世、自动LAN、协议763状态响应。
- 实测修正Bridge：需pack.mcmeta避免Forge警告页阻止自动启动；不能在ServerStartedEvent直接publishServer，因为LocalPlayer尚为空，现等玩家进入世界后开放LAN；路径匹配使用Files.isSameFile兼容8.3短路径。
- 正常退出的保存回执仍在实测诊断，未标记完整Hop通过。双机不同NAT、Host→Player→Host物品栏连续性尚未验收，main保持不合入。
- 已构建过Windows包，但最终交付需以Bridge最新验证结果重新构建，不能把之前dist当最终验收包。


### 2026-11-16 真实游戏关键检查点
- 实际1.20.1/Forge47.4.22的自动LAN、763状态查询、正常保存事件、Java文件锁释放、玩家数据归档及退出均通过。
- 真实ECS上的单机双身份顺序 A→B→A 接管通过，三次分别正常提交版本。A=3钻石/17级，B=2绿宝石/23级；A再接管仍为自己的3钻石/17级，且B阶段A玩家文件SHA-256不变。原用户存档未加载，测试房间已移除。
- Player自动加入仍在排查：直接LAN对照也超时，故不能归因于中继。现将Guest加入交给Bridge先执行Forge服务发现，待forgeData齐备后再ConnectScreen，避免仅依赖原版Quick Play；结果待实测。
- 退出保护已修正：仅clearLevel会等待未停的集成服务器，需先断开并halt(false)再clearLevel。修复后正常保存测试通过。
- 当前最新dev检查点4bbadad，后续修复尚需第二次提交/推送、重建客户端和同步服务端对应源码。main继续保留验收门槛。


### v0.1.0 发行候选：本轮已验证范围
- 本轮用户明确要求：将已验证版本推送dev、合并main并发行Release；当前交付范围按RELEASE_NOTES.md记录，不把未完成的跨电脑/NAT验证标记通过。
- 27项本地自动化测试通过；网络清理专项增加无ASGI错误断言与单侧提前关闭场景，并通过回归。
- 最终真实游戏：1.20.1/Forge47.4.22独立启动、自动LAN、正常保存/锁释放、ECS三次A→B→A接管通过。A=3钻石17级，B=2绿宝石23级，A再接管仍正确。
- 两个真实Minecraft进程经ECS中继自动加入通过，同时收到Player的Bridge入服确认；Player退出不上传，Host保存退出提交最终云版本。测试账号与房间已清理。
- Guest改用Bridge执行Forge服务发现，取得forgeData后连接；原版Quick Play的直接连接与LAN对照都曾出现握手超时，该实测修复已验证。
- 发行包含Windows完整包（Java17及两个Java辅助模块）、Docker服务端、校验和；包内BUILD_INFO.json追踪来源提交。测试Fixture模组不进入客户端包。
- 固定接口：HTTPS47192业务、HTTPS38443+原安全路径面板、52861/UDP端点发现，MySQL不发布主机端口。
- 发布操作进行中；最终合并、CI、Release及线上镜像回执以GitHub和本地.local记录为准。
