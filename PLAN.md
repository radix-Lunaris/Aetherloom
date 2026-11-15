# Aetherloom 首版计划
## 范围
独立 Windows 客户端，自研最小启动层，用户手动绑定完整 .minecraft、版本和运行目录。不扫盘、不下载游戏、不安装加载器、不导入导出整合包。首个验收：1.20.1 / Forge47.4.22。
未登录可普通启动；软件账号与Minecraft账号独立。发行包配套Java17。
ECS权威存档，玩家电脑轮流计算。一个持久实例房间对应一个环境一个世界，Owner无需在线。
root/admin/player、Owner/Instance Admin/Member、Host/Player分层。实例管理员由Owner或root任免，Host不自动获得管理权。
默认租约60s，5s续租，事务唯一Host，递增epoch，提交检查父版本、租约、身份。
只在接管前、正常退出后、明确恢复时同步。运行中不定期扫描或上传。
SHA256内容寻址，正常退出上传成功后释放Host。失败保留本地及待传任务。
旧Host原始副本保留，离线检查后生成恢复候选，上传不改变权威版，Owner/Instance Admin审批，必须无活动会话。恢复生成新版本保留旧版本，不按时间猜测、不自动合并。
shared-playerdata固定基线2d0cf068ff252d7542d44536a677a2fdb247cff7，MIT。只修选定世界，修复完成后启动，禁全目录扫描及双修复器；保留双方冲突数据。
Bridge负责LAN、身份、世界就绪和正常保存事件。普通启动不受共享控制。
AUTO先中继后验证P2P升级，故障回退。高级设置relay/direct/auto。网络波动先重连，不做无缝换Host。
Ubuntu24.04 2核2GB约30GB；不限制账号房间总数，空间低于10%拒绝新占用，保护上传块与历史版本。
Python/PySide6；FastAPI/SQLite WAL；独立中继STUN与管理面板。
## 阶段
1 建仓、文档来源、dev同步。
2 独立启动：manifest继承、参数、依赖、native、assets、Java、离线游戏账号与GUI；不做正版授权。
3 单世界修复、Bridge、LAN及生命周期。
4 认证权限、唯一Host、块存储、恢复审批、AUTO与编排。
5 Windows/Java17打包、Ubuntu部署、面板、双机实测，验收后合main。
## 验收
无外部启动器可启动；中文隔离路径/缺文件/Java错误处理。
A Host/B Player -> A保存上传 -> B Host/A Player，角色/物品/经验/模组数据保持。
并发唯一Host，过期epoch拒绝；崩溃、断电、网络波动、旧Host候选审批。
坏哈希、缺块、空间满、路径越界、GC不损权威版。权限矩阵验证。
运行中无定期扫描上传，未变块零上传。真实双机与目标ECS验证，不以单测替代。
## 远端
https://github.com/radix-Lunaris/Aetherloom
保留历史，dev开发，main总交付，不强推。每阶段更新检查点。



## 本轮发行调整（2026-11-16）
用户要求将当前已验证的v0.1.0里程碑合入main并发布Release。已通过同机双身份接管及双进程真实ECS联机；两台不同Windows、不同NAT、复杂整合包及更广玩家数据组合仍保留为后续验收项，不据本次发行标记完成。
