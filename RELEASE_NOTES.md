# Aetherloom v0.2.1

修复部分已安装 Forge 整合包在启动前报 `Unsupported variable: primary_jar_name`。

## 修复内容

- 支持启动元数据中的 `primary_jar_name`、`primary_jar`、`libraries_directory`、`file_separator`。
- 主JAR来自实际版本继承／jar指向，文件名与Java使用的classpath路径一致；兼容Windows短路径、中文和含空格名称，不使用界面版本昵称猜测。
- 不修改游戏版本JSON，不调用其他启动器，不把未知变量静默置空。

## 验证

- 在用户当前DeceasedCraft中复现原错误；修复后DeceasedCraft和Construct Technological Innovation完整参数校验通过。
- 45项核心回归通过；真实Java进程验证JVM ignoreList、主JAR完整路径、中文含空格名称和父子版本名不同。
- 大型整合包的完整主菜单加载以实际验证记录为准，参数校验通过不代表所有Mod组合已验收。

## 下载与使用

直接下载新的 `Aetherloom.exe`，退出旧客户端后替换；已有账号、版本配置和UUID设置保留。

工作区仍只在release保留EXE、Aetherloom-Server.tar.gz和SHA256SUMS.txt，无客户端ZIP或dist副本。Java自动选择、官方校验下载和其他v0.2.0功能继续保留。本次仅客户端参数修复，现有服务端无需重新部署；历史发行不覆盖。
