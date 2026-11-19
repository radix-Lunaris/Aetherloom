# Minecraft Java 正式版兼容表

[逐版本 CSV](COMPATIBILITY.csv) 包含 Mojang 清单中的 103 个 Java Edition 正式版，从 1.0 到 26.3。快照和测试版不在表中。[Mojang 正式版本元数据入口](https://piston-meta.mojang.com/mc/game/version_manifest_v2.json)

| 列 | 判定条件 |
| --- | --- |
| 推荐 Java | 优先读取版本的官方声明，旧版没有声明时按发行版本选择 |
| 原版启动计划 | 使用官方版本 JSON 和测试文件运行启动器准备流程，检查 Java 版本解析、依赖和原生库路径、参数及主类。这个检查没有运行游戏 |
| Fabric／Quilt 精确映射 | 内置与该 Minecraft 补丁对应的类名及成员别名。还需由实际加载器与游戏协议通过运行时检查 |
| 双玩家接续实测 | 用该具体加载器组合启动真实游戏，验证自动加入、保存上传、下一人接手和原 Host 重入。空白表示没有这项实测记录 |

1.14.4 和 1.15 至 1.21.11 的 39 个补丁有精确 Fabric／Quilt 映射。Minecraft 26.x 走新版可读类名路径，目前只有原版启动计划检查结果。Forge、NeoForge 的联机控制依据该版本的加载器 API，已验证的组合见表中最后一列。
