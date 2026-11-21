# Aetherloom v0.4.0a14 — 在线启动、打洞与存档维护

- Forge 1.21.1 从游戏主菜单打开指定共享存档，避开已观察到的 Quick Play 资源初始化崩溃。
- LittleSkin 从房间准入选项移除，继续提供游戏身份和皮肤来源。房间成员和游戏 UUID 仍由 Aetherloom 会话验证。
- 接入 CraftLink 的 NAT 打洞核心。直连套接字仍需匹配 Aetherloom 当前的会话密钥。旧服务器或旧客户端可走原路径。
- 本地存档页增加 MCSync 区块清理。预览并确认后生成可增量发布的副本。增量下载可复用本地已有存档中 SHA-256 匹配的分片。
- 新的 CraftLink 路径需要两端客户端与 ECS 服务端更新。发行包不包含 Java。
