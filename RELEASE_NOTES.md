# Aetherloom v0.4.0a4 — 存档识别、联机状态与 LittleSkin

- 在本地游戏中添加LittleSkin账号、下拉选择角色；独立于Aetherloom软件账号，角色名称/UUID由LittleSkin确定。
- Windows用户级DPAPI加密保存令牌、启动前刷新；不保存密码，不将令牌写入普通配置或软件游戏日志。
- 官方authlib-injector1.2.8经固定SHA-256校验后原样内嵌单EXE，包含许可与来源；不捆绑Java，不要求额外JAR/ZIP。
- 共享房间可声明离线或LittleSkin模式，管理员显式转换；外置房间Host启用会话认证，保留签名皮肤属性，并按完整UUID校验软件授权成员。不同角色/旧离线UUID不按昵称合并。
- 默认Bridge0.1.1和实验Agent均支持外置模式。中文/特殊符号角色使用真实UUID校验，兼容既有ECS隧道接口，无需数据库迁移或本轮部署。
- 自动安装新版 Bridge 时保留并停用原0.1.0文件，避免重复 Mod ID 阻止游戏启动。
- 参考 MCsaves-sync，自动列出当前实例 saves 内的世界名称、游戏版本、模式、难度和最近游玩时间，支持直接发布；损坏元数据显示原因。仅读取 level.dat，游戏运行时暂停，不扫盘、不读区块。
- 对照 CraftLink 完整显示运行状态、身份、通路、NAT、入站策略、打洞进度、房间、人数、本地连接、延迟、速度和累计载荷流量。STUN 使用上游探测算法；无测量结果显示未测。诊断套接字与实际游戏直连验证分开。
- 游戏人数来自 Bridge/Agent；ECS 未提供全体大厅在线心跳时明确标注，不以已加入世界人数冒充大厅在线人数。
- Forge 房间绑定改为 Minecraft 精确版本与 Forge 主代际，不再锁定 47.4.22 补丁号；仍要求玩家自行确保 Mod/协议兼容，不承诺所有 Forge 组合互通。
- 实验 Agent 新增 1.21.1／Forge52，已通过 Java21 真实双进程自动 LAN、重复入服、自定义 UUID 背包/经验、Player退出不上传及Host最终提交。修正 QuickPlay 事件注册时序和新版离线身份配置阶段差异。Bridge 托底仍为 1.20.1／Forge47。
- 手动 Java 版本继续允许自行尝试。个人启动不受上述在线适配范围限制；Fabric、NeoForge及其他Minecraft版本的完整自动Hop尚未验收。Agent默认关闭，需启用并重新绑定房间。

验证使用本地RSA签名Yggdrasil测试服务与真实Minecraft双进程，1.20.1 Bridge/Agent及1.21.1 Agent均通过，包含服务端join/hasJoined、签名纹理及皮肤PNG、角色数据与最终上传。真实LittleSkin账号/用户皮肤未代为验收，请在新GUI登录确认。OAuth/Passkey尚未接入，采用传统Yggdrasil账号密码登录。

使用：添加角色→个人启动；联机则所有成员选择LittleSkin，管理员结束Host后切换房间账号模式，各自重新绑定。旧离线背包不会自动迁移。当前为实验分支Prerelease，不替换稳定Latest，不合main，不部署ECS。
