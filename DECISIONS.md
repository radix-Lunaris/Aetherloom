# 决策
2026-11-15补充：用户明确只使用Minecraft离线账号，取消正版授权路线。软件服务账号仍需登录。提供Windows GUI与Docker控制服务开发包。
2026-11-15：自研最小启动层，完整目录外部提供；运行中无定期备份；ECS为权威版本中心；异常恢复必须独立候选及审批。



## 2026-11-16 真实Forge验证后的接入决策
- Host保留Quick Play单人入口；开放LAN等待本地玩家实际加载完成，不在ServerStartedEvent立即调用publishServer。
- 受管退出先断开客户端并halt(false)，再clearLevel；否则clearLevel可能一直等待仍在运行的集成服务器。
- Player由Bridge先执行ServerStatusPinger，取得Forge元数据后调用ConnectScreen。实测原版Quick Play直接进入连接会超时，直接LAN对照同样复现；改用该流程后真实ECS加入通过。
- 正常结束以Bridge事件与Minecraft session.lock释放共同确认。任何受管Host/Player均关闭原shared-playerdata扫描器，普通启动保持原行为。
- 本次实际验收使用隔离测试世界、同机双身份/双进程及真实ECS。跨电脑不同NAT不标记通过。
