# Aetherloom v0.4.0a13 — 联机启动校验

- 在线启动前检查内嵌 Agent 的 JAR、入口与字节码，发现损坏时直接提示。
- Host 发布房间前，从本机回环地址验证游戏报告的 LAN 端口可连接。失败时，房间不会上报就绪。

本轮不增加 Minecraft 版本适配。完整状态见 COMPATIBILITY.csv。
