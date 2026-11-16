# Aetherloom v0.4.0a1 — Java Agent experiment

实验预发行，默认仍使用Bridge。可在“本地游戏”勾选实验Agent并重新绑定房间；当前仅允许Minecraft1.20.1/Forge47.4.22，其他版本未开放在线支持。

- Java8字节码、无第三方运行依赖的Agent通过Instrumentation发现游戏加载器，调用显式映射的游戏接口及Forge事件；不需要在客户端安装我们的Bridge Mod，不修改游戏JAR。
- 增加能力握手；保存/身份校验失败保留本地恢复数据，不提交权威版本。普通离线启动不注入Agent。
- 单个Aetherloom.exe包含应用运行依赖、Agent、稳定Bridge和玩家数据辅助模块；Java继续从用户电脑识别，不捆绑、不自动另装。
- CI覆盖Java8/11/17/21/25的Windows和Linux引导检查；该检查不代表任意Minecraft可在这些Java上运行，也不代表广版本Hop通过。
- 广版本适配、每组合20次接管、跨NAT与性能对比未完成；本版只能用于副本实验，不标记稳定支持。稳定Latest和dev保留v0.3.0；可替换回稳定EXE、取消实验选项并重新绑定回退，真实世界恢复仍遵守候选审批。

实测：未安装Bridge Mod的真实Forge世界自动加载/LAN/保存/退出通过；两个游戏进程经本地测试中继自动入服，自定义UUID首次保存后再次加入，23级/2绿宝石保持。Player退出不上传，Host最终提交并退出通过。50项自动化回归及桌面交互检查通过。旧Java游戏的玩家数据辅助模块仍待适配，因此暂不开放旧版在线。

本轮不部署服务器。交付仅release中的单EXE、Docker服务端包及校验和，无客户端ZIP或Java捆绑。
