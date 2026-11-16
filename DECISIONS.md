# 决策
2026-11-15补充：用户明确只使用Minecraft离线账号，取消正版授权路线。软件服务账号仍需登录。提供Windows GUI与Docker控制服务开发包。
2026-11-15：自研最小启动层，完整目录外部提供；运行中无定期备份；ECS为权威版本中心；异常恢复必须独立候选及审批。



## 2026-11-16 真实Forge验证后的接入决策
- Host保留Quick Play单人入口；开放LAN等待本地玩家实际加载完成，不在ServerStartedEvent立即调用publishServer。
- 受管退出先断开客户端并halt(false)，再clearLevel；否则clearLevel可能一直等待仍在运行的集成服务器。
- Player由Bridge先执行ServerStatusPinger，取得Forge元数据后调用ConnectScreen。实测原版Quick Play直接进入连接会超时，直接LAN对照同样复现；改用该流程后真实ECS加入通过。
- 正常结束以Bridge事件与Minecraft session.lock释放共同确认。任何受管Host/Player均关闭原shared-playerdata扫描器，普通启动保持原行为。
- 本次实际验收使用隔离测试世界、同机双身份/双进程及真实ECS。跨电脑不同NAT不标记通过。


## 2026-11-16 dev：启动入口、运行时与可观测性
- 个人离线启动与在线受管会话明确分开；普通启动不传 Bridge 配置、不激活 LAN、不管理租约。在线正常退服后游戏退出，Host 保存事件和文件锁仍是提交前提。
- Java 不进入客户端包；只在用户指定根目录的已知运行时布局下有界发现，不查全盘或调用外部启动器。手动指定现有 Java 作为缺失情况下的入口。
- 游戏版本声明采用可归一化的 Minecraft/加载器/加载器版本；保留 room_settings.environment 列兼容现有 MySQL，无损读取明确的旧 Forge 声明。未知旧名称不能推断为兼容，需管理者明确设置。
- 客户端展示 CraftLink 实际 AutoStream 快照及本实现打洞状态；服务器诊断只展示可观测的中继附着，不把中继存在宣称为 P2P 已连通，不新增不支持的 NAT 类型判断。
- 前台客户端和网页5秒自动刷新，隐藏页面降低频率，失败指数退避，进行中的请求不重叠；保留滚动、账号选择及表单编辑。
- account-options 仅 Owner/root 获取可用账号名称，避免开放完整账号管理 API；实例管理员可改房间策略和恢复审批但无所有权转移／成员任免权。
- 本轮只推送 dev，不合并 main、不重新发行 v0.1.0、不更新线上容器。
