# 实施检查点：2026-11-15

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
- Windows远端Java进程测试与本机结果不同，已固定Temurin17环境并增加失败日志，跟进最终CI结果。

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
