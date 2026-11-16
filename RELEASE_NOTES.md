# Aetherloom v0.4.0a7 — 多加载器与并发同步实验版

- 云存档缺失块默认四线程上传和下载，最多八线程；仍逐块校验 SHA-256，全部完成后才能提交或加载。缓存命中不重复传输。
- Java 官方下载支持四路 HTTP Range；源不支持时回退流式下载，完整校验后安装，不捆绑 Java。
- 联机状态按 CraftLink 展示十四项内容，加入短期房间成员心跳。心跳仅用于人数显示，不决定 Host 或存档权限。
- 恢复 CraftLink 完整 NAT 探测预算，并提供独立双端口 STUN Docker 服务（UDP 52718、52719），支持替换源端口的过滤测试。NAT 分类依据实测，不把未知伪装为确定结果。
- 修复 AQS NeoForge 类加载、协商及服务发现；Forge、NeoForge、Fabric、Quilt 使用各自控制路径。Fabric/Quilt 通过内嵌 Java Agent 工作，不要求 Fabric API 或额外控制 Mod。
- 选定世界的备份确认只在验证世界路径后由游戏创建备份并继续；错误信息保留实际原因。保存确认失败或异常退出不能提交权威存档。
- 内嵌私有命名空间 ASM 9.7.1 和最小映射，保留 BSD、CC0 及 Mojang 来源声明。单文件 EXE，不包含 Java 运行时。

实机隔离测试通过：1.20.1/Forge 47.4.22（Java 17）、1.21.1/NeoForge 21.1.264 AQS 252 Mods（Java 25）、1.21.1/Fabric 0.20.1 和 Quilt 0.30.2（Java 21）。四组均验证双玩家加入、退出上传、接手及重新加入；自定义 UUID 的经验与物品数据保持。以上不是对所有 Minecraft 或 Mod 组合的兼容承诺。

实验分支预发行，不合入 main，不替换稳定 Latest。独立 Bridge 托底模式保留。
