# 实施检查点

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
