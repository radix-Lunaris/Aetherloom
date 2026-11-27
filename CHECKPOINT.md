# 实施检查点

## 2026-11-17 并发传输／NAT完整探测／四加载器适配（进行中）
- 用户反馈下载慢、NAT显示不完整、AQS控制失败，并追加Forge/NeoForge/Fabric/Quilt全部适配。
- 已确认云存档原为逐块串行；改为默认4线程、最大8线程的有界队列，进度汇总仍在协调线程，SHA256/块大小/完整清单/原子替换门禁保留。Java官方下载增加4路Range分段，源不支持时退回流式下载，最终完整哈希与大小验证不变。
- NAT原调用把CraftLink诊断3秒/4响应缩为0.7秒/2响应；已恢复原默认和过滤/对称型细分，保留原算法；状态卡14字段名称与原项目对应，不把未测误报为严格。
- AQS实际为MC1.21.1/NeoForge21.1.264、252个Mods、用户Java25。原错误ClassNotFoundException指向Forge专用ClientModLoader；补充NeoForge总线/事件/登录/服务发现适配，并修正环境识别。
- AQS隔离实测发现实验世界备份确认会拦住QuickPlay：只允许处理回调中明确绑定选定世界的确认，先创建游戏备份再继续，不清缓存。第一次已到LAN就绪，又发现兼容Mod导致旧SRG与官方名称重复匹配；NeoForge改用官方名称后复测中。用户原世界/配置不修改。
- Fabric/Quilt使用隔离命名空间ASM及JDK-only bootstrap桥，钩住正常halt/保存返回、致命异常、玩家构造前身份；不要求额外Fabric API/控制Mod。使用既有Minecraft二进制、官方映射派生别名和加载器依赖，在隔离目录验证。首次Fabric实测暴露未可达RETURN栈帧的this无效，已按完整帧跳过死分支钩子，继续复测。
- 目前所有新增路径尚未发行，按实际测试结果分别记录，不把取消门禁或引导检查当作完整Hop兼容。

## 2026-11-17 Agent取消加载器前置限制
- 按用户要求，Agent仅比较Minecraft游戏版本；Forge主版本、补丁号、加载器类型与支持组合白名单均不作为绑定/启动门禁。Bridge托底边界保持。
- Java premain去除两个适配器的硬编码白名单；新旧事件路径按实际Forge API存在性选择，身份/能力/保存/租约校验保留。未把移除门禁称为全版本兼容。
- 62项回归与桌面检查通过，真实1.20.1/1.21.1控制复测和单EXE构建进行中；无新的生产部署。
- 实测已通过：1.20.1/Forge47与1.21.1/Forge52均自动LAN、正常保存、锁释放和游戏退出；独立JVM接受1.19.2-forge、1.21.4-forge、1.20.1-fabric标签，不再被premain白名单拒绝（此引导检查不代表对应游戏已适配）。开始构建v0.4.0a6单EXE与对应发行草稿。


## 2026-11-17 当前验证进度
- a4未公开：CI Windows发现新增测试对临时目录长短路径别名未规范化，已将范围断言改为resolve后比较；Ubuntu61项与Java全矩阵及Docker均通过。Bridge任务一次官方仓库插件解析失败，独立Bridge同源CI已通过。a4标签保留、不重写，a5重新构建与CI后发行。
- 最终61项自动化回归通过（50.373秒），桌面smoke及实际状态页布局检查通过；等待来源提交CI后公开a4候选版。
- 最终真实双进程：1.21.1／Forge52.1.16 Agent 的离线和外置认证均通过首次/重复入服、自定义UUID 23级2绿宝石保持、Player不上传、Host最终提交和游戏关闭。1.20.1／Forge47.4.22 的最终Agent和Bridge0.1.1外置认证复测均通过；每次两次join/hasJoined及签名皮肤PNG实际请求通过，未使用用户真实LittleSkin账号。
- 独立Bridge来源已更新为58b988891d2f96101b810ecfc0984aaeb2b0dbd5（dev），包含人数监测与外置身份协议；本地离线构建成功，待对应CI后发布v0.1.1。应用a4统一构建/发行中，不修改稳定dev/main或生产ECS。
- 升级时将已识别旧版Bridge保留到游戏目录.aetherloom/disabled-mods，防止0.1.0/0.1.1双Mod ID；不删除原文件。新增幂等升级/备份测试。
- 新增选定实例的自动存档列表：参考 MCsaves-sync scanner/level_info 的字段与范围，原创有界 NBT 读取；只读取所选运行目录 saves 的 level.dat，不计算世界大小、不读 region。运行游戏时暂停探测。
- 对照 CraftLink 补齐运行状态、角色、路径、NAT、入站策略、打洞、房间、人数、本地连接、RTT、速度与累计流量；实际游戏人数由 Bridge/Agent 每两秒报告，流量按传输载荷计数。没有 ECS 全员在线心跳则明确显示未提供，不编造在线人数。
- STUN 诊断移植自 CraftLink 8178a3df，保留 GPL 和哈希；独立诊断套接字不替代实际 P2P 验证。本机实测 6.42 秒完成、两个端点响应、锥形映射、过滤 unknown；界面显示入站未测。
- 60 项回归通过，含存档截断/压缩上限/NBT深度、选定目录范围、CraftLink NAT 展示语义、真实 TCP/UDP 流量、游戏人数校验。桌面导航和状态卡检查通过。
- Agent 1.21.1/Forge52 已通过新世界 LAN/保存/锁释放；已有世界 QuickPlay 暴露事件注册竞态，增加加载屏障与选定世界就绪恢复后通过。双进程进一步暴露离线配置阶段 UUID 报文早于 Forge 身份屏障，正在验证客户端身份对齐，不将未通过场景列为已验收。
- LittleSkin 已用本地 RSA 签名 Yggdrasil 测试端与真实 1.20.1 双进程验证；尚无用户真实 LittleSkin 登录/皮肤验收。当前工作未发布，生产 ECS 未部署。

## 追加需求：广版本、存档检测、CraftLink状态页（进行中）
- 用户要求去除Forge补丁号精确限制；已将房间匹配改为Minecraft版本+加载器代际（Forge47.*同族），Agent增加1.21.1/Forge52官方名接口适配，尚待真实游戏验收。个人启动原本不受1.20.1限制；不把未验证环境伪装已支持。
- 用户要求参考MCsaves-sync自动检测存档。已阅读client/core/scanner.py的list_saves和nbt.level_info；新增独立有界只读NBT摘要和当前运行目录saves平级枚举，不扫描区块/磁盘。GUI列表在切换实例、新目录出现、游戏退出时自动更新，受管游戏中暂停。
- 用户要求照搬CraftLink联机状态字段。已阅读GUI运行状态卡及NAT展示规则，固定引入原STUN探测算法；仅把枚举导入改为最小适配，不改探测/分类逻辑。NAT1/2合并、入站宽松/中等/严格/未测与上游一致，界面接线及测试进行中。
- LittleSkin当前代码默认Bridge和Agent的本地真实双进程认证/皮肤首次与重复入服已通过；UUID查询改为完整已验证身份以支持中文角色、兼容旧ECS隧道标签。一次重复入服曾报告控制错误，后续复测通过；保留记录，不宣称所有网络组合已验收。
- 本轮尚未发行应用a4；独立Bridge0.1.1来源为232b215be5f0f808fe44a35f21ae5bdc58c613bc，已推dev且CI成功。待追加任务测试完成后统一单EXE构建与Prerelease，不部署ECS。

## 2026-11-16 LittleSkin外置登录实施中
- 使用官方LittleSkin Yggdrasil端点，已以无凭据请求确认authenticate仍可用；不读取其他启动器缓存。新增游戏账号与角色选择，密码不保存，Windows DPAPI保存令牌，启动前刷新授权。
- 内嵌未经修改authlib-injector1.2.8（官方build56，SHA256固定），保留AGPLv3+AUTHLIB-INJECTOR例外及依赖许可，客户端无需额外JAR/ZIP或Java。
- 房间认证模式放入现有environment声明，避免数据库变更；旧房间默认offline。LittleSkin房间必须所有成员选择LittleSkin身份，管理员显式转换且结束Host后才可修改。不能用任意自定义UUID覆盖外置角色。
- Bridge和Agent在外置房间启用在线会话验证，校验服务端已验证UUID与软件授权对端一致，保留签名皮肤属性，不改写真实外置身份。离线修复逻辑不用于合并外置角色。
- 55项回归及桌面检查通过。Agent真实双进程本地RSA测试认证服务已通过：join/hasJoined、签名profile及皮肤PNG请求、角色UUID/23级/2绿宝石、退出上传行为。默认Bridge真实认证已通过，最终0.1.1强制新纹理缓存未命中复测中。
- 未使用真实LittleSkin账号，真实账号登录/实际皮肤由用户在交付GUI验证；不将本地协议测试当成用户授权实测。
- 独立Bridge dev已同步70498955b1cbe1e49dc31cfc991a22d32ddb4f2f，应用SOURCE固定；本地Forge证书预检异常，已用现有离线缓存构建成功，客户端运行无需Gradle。main、生产ECS均未动。

## 2026-11-16 整合包 primary_jar_name 热修复
- 已在用户当前DeceasedCraft版本预检查中复现Unsupported variable: primary_jar_name；另一整合包Construct Technological Innovation也引用该变量。
- 核对实际版本配置与HMCL公开变量语义，只补本项目参数映射，不导入启动器源码。primary_jar指向最终继承／jar指定的实际客户端文件；primary_jar_name取Java实际classpath使用的路径文件名（含Windows短路径情况），不按界面版本昵称猜测。
- 同时支持primary_jar、libraries_directory、file_separator；未知变量仍严格报错，不替换为空掩盖后续错误。
- 已增加真实Java进程回归，覆盖继承版本主JAR与子版本名不同、中文目录、JVM ignoreList和完整路径。正在复核实际整合包启动，随后按唯一release目录规则发行v0.2.1。
- 修复后两个实际整合包完整参数检查通过，45项核心回归通过；主JAR名进一步改为中文含空格的真实Java专项回归也通过。
- DeceasedCraft首次隔离冷启动已创建游戏窗口、进入Forge／Mod加载；4GiB测试在240秒时限内未完成渲染，未标记主菜单通过。已清理测试派生CrashAssistant及副本；按用户配置12900MiB继续复测，不加载原世界。

## 唯一release目录与v0.2.0发行（用户追加）
- 用户明确要求：不再另打ZIP，所有构建产物在release独一份，每轮版本迭代发布一次GitHub Release。已落入项目AGENTS.md，后续执行沿用。
- 当前改为单文件Aetherloom.exe（内嵌JAR／许可）、单份Docker tar.gz和SHA256SUMS；辅助模块在_MEIPASS/assets访问。许可入口在“运行记录→许可与来源”。
- 完整构建脚本先生成产物，再核验清理路径位于本项目且不经过链接，删除旧dist、编译中间目录和本项目测试Mod副本。保留用户世界、配置、Java和依赖缓存，不删除历史远端发行。
- 发行脚本只读取release中的唯一文件，不复制版本目录；核对客户端／服务端来源、校验和、dev／标签和CI，再草稿上传、验证远端摘要并公开。沿用现有Git凭据且不落盘。
- 本轮版本v0.2.0，从已验证dev发布；不擅自合main，不自动再部署服务端。当前正在验证单文件构建与发布流程。
- 45项回归与扩展桌面smoke通过，含单文件_MEIPASS资源路径和许可查看入口；后续将验证真实单文件EXE、唯一产物清理、远端CI和Release附件摘要。

## Java 自动发现与一键下载（2026-11-16）
- 用户要求参考 HMCL，扩大 Java 搜索、自动选择合适版本，缺失时一键下载；本轮仅客户端开发与 dev 推送，不自动部署服务器或发行 Release。
- 已只读审阅 HMCL JavaManager、JavaRuntime、GameJavaVersion、JavaVersionConstraint；自行实现，不复制其源码。范围为已知 Java 安装位置／注册表／环境变量／用户 .jdks／官方 Minecraft 与 HMCL 运行时目录／所选游戏附近已知运行时子目录，不递归全盘、不访问启动器账号缓存。
- 实机已找到截图中的 HMCL Java17.0.15、Loom25、Microsoft25.0.3，以及Minecraft Java21.0.7。1.20.1/Forge自动选择稳定64位17.0.15，不选择Loom或Java25。
- 已增加 auto/manual 每版本设置、版本／位数／来源候选、重新检测和下载／取消入口；缺失时不会自行联网下载。
- 下载采用 Temurin 官方 API 元数据、Windows x64 GA JRE（无JRE时查同版本JDK），校验大小与SHA-256，有界解压、拒绝越界和链接、探测版本／架构后原子安装，保留上游许可。不改系统环境变量，不随客户端ZIP打包Java。
- 正在验证真实下载、故障回归、UI与游戏启动，尚未提交或标记全部通过。线上服务端仍为上一轮ec22e7c。

### 本轮验证结果
- 44项完整回归通过，包含版本／架构／稳定性选择、已知目录发现去重、JRE缺失时同主版本JDK回退、SHA-256错误／取消／错误版本不发布、ZIP越界／重复／符号链接／设备名拒绝、共享会话在任何云操作前选择Java。
- 扩展桌面smoke通过：候选列表、auto/manual切换、每版本设置、下载完成自动选用、取消不改变旧设置；真实窗口布局检查通过。
- 实际官方下载安装：Temurin17.0.21+9 x64 JRE，43,860,024字节，SHA-256 fe4656bd78fb09812dc38c49da777f79cc33e7ee435a254be82f9e7f40d9d117。下载、大小与哈希、解压、执行探测、重新发现均通过；仅写项目 .local 测试目录。
- 真实Minecraft/Forge双运行时分别验证通过：HMCL目录自动发现的17.0.15，以及新下载的17.0.21；均完成自动LAN、协议763、保存回执、文件锁释放、归档及进程退出。测试新建独立世界，不连接生产ECS、不使用用户原存档。记录在 .local/real-game-java-*.json。
- 不导入HMCL源码，不调用HMCL/PCL可执行程序；只复用用户机器上已有的Java运行时文件。完成提交后构建无捆绑Java的客户端及对应源码包，结果记录在 .local/dev-build-receipt.json。
- 旧房间绑定未记录Java模式时迁移为auto，避免其残留捆绑Java路径绕过新选择器；已有明确manual模式不变。打包EXE也已验证实际发现HMCL Java17且内含下载模块。

## 2026-11-16 重启恢复后的新一轮（仅 dev，禁止自动部署／发版）
- 已恢复命令工具。正在实现首页离线／在线分离、所选房间提示、版本配置管理 Beta、目录内 Java 发现、在线退出关闭游戏、详细轮转日志、联机状态页、无感刷新和账号下拉选择。
- 本轮不捆绑 Java；只在明确所选根目录的已知 Java/runtime 布局中有界发现，找不到时提示手动指定。用户给出的嵌套游戏根未发现 Java，已确认 1.20.1-Forge 元数据确为 MC 1.20.1 / Forge 47.4.22。
- 最新 Bridge 已构建。真实 Minecraft 新建隔离测试世界通过自动 LAN、763 状态查询、保存回执、文件锁释放、归档与整个游戏退出；未连接生产 ECS，未加载用户原世界。
- 首轮 27 项回归中 26 项通过，发现新诊断代码对 urllib.Request.method 的错误访问；已改 get_method，待重跑。桌面 smoke 已通过。
- 待办：新增覆盖 Java/环境/账号选择权限/刷新保留状态的回归、浏览器验证、完整测试、无 Java 客户端及 Docker 源码包重建、审查后提交推送 dev。main、v0.1.0 和线上容器保持原状态。

### 本轮最终验证（0.2.0.dev0）
- 32 项完整回归通过，含新增运行时发现、明确环境声明、账号选项权限、诊断凭据过滤、取消与内存预算清理回归。
- AUTO 关闭时重复取消可打断上游 finally 的清理，已在本地 PolicyStream 适配层用受保护工作任务等待完成；上游 vendor 文件保持未修改。协议回归改为覆盖实际适配层。
- 桌面扩展 smoke 通过：首页离线／在线入口、普通启动不传 Bridge、房间行保留、滚动保持、所选房间提示、多版本运行目录独立保存和恢复。
- Edge 浏览器通过：5秒轮询保留 DOM 行、滚动、未提交弹窗输入；所有权与成员账号使用数据库下拉；诊断弹窗可读取实际中继附着状态。
- 最终 Bridge 构建成功；本机临时服务端（非生产 ECS）双进程真实 Forge 游戏复核通过：Player 自动加入、离开后进程自动关闭且云版本不变；Host 自动关闭、正常保存、文件锁释放、最终提交成功。记录在忽略的 .local/local-join-iteration.json。
- Java 自动发现仅在所选目录内搜索，最多2048个目录、5层、不跟随越界链接；手动指定仍可用。客户端日志 DEBUG（Python 数值10）开启，屏幕提示与文件轮转并存；凭据不进入日志。
- 完整 Hop 仍限定 MC1.20.1 / Forge47.4.22。不同电脑／不同NAT及更广Mods组合不计入本轮通过；旧房间仅有昵称式版本声明时需先明确补充。
- 源码与文档准备提交 dev，再从该提交构建无 Java 客户端和 Docker 服务端包；构建回执保存在 .local，线上部署另待用户指令。

### 追加可选 UUID（用户本轮追加）
- 初始功能提交为19e1f2e，尚未推送；构建过此中间提交的无 Java 包，不作为最终交付。
- UUID 字段按本地版本保存，空白使用原离线名称算法；支持32位和标准带连字符 UUID，拒绝无效或全零值。启动、修复、正常归档和恢复检查统一使用选定身份。
- 原版离线 LAN 会重建 UUID，新增作用域连接身份声明与 Host Bridge 的 Forge 入服协商；禁止并发身份冲突和修改当前成员身份，不读取其他启动器令牌。
- UUID 配置／身份约束新增回归后34项通过，桌面配置切换回归通过。真实自定义UUID Player已加入，并在正确 UUID 文件下保存；正在复核再次加载原有物品栏，首次失败分别是服务发现超时和测试夹具未包含uuid字段，已继续排查而未标记通过。
- 最终完成后需追加提交、重建客户端／服务端包再推送 dev。main、Release、线上容器仍保持原状态。
- 自定义 UUID Player 再次加入实测通过：Bridge确认身份一致，正确UUID玩家文件存在，恢复2绿宝石和23级经验；Player退出不上传，Host最终提交正常。记录 .local/custom-uuid-join-verification.json，测试房间已清理。
- 自定义 UUID Host 新建隔离世界也通过：自动LAN、763状态、正常保存、文件锁释放、按指定UUID归档和游戏进程自动退出；记录 .local/custom-uuid-host-verification.json。最终34项回归、桌面 smoke、Forge构建均通过。后续产物以最终提交的 BUILD_INFO.json 为准，不使用19e1f2e中间包。
- 远端2bc04ca：Ubuntu34项、Docker/MySQL构建与健康检查、Forge构建通过；Windows34项通过后，桌面smoke因临时目录的显示路径与resolve路径字符串比较失败。改为比较解析后的目录，仍严格检查正确实例目录；随后重新运行CI。打包回执保存在 .local/dev-build-receipt.json，产物不含Java和Fixture jar。

## 界面重构：2026-11-16
- 用户要求客户端改为CustomTkinter；已移除桌面PySide6依赖，重写固定侧栏、本地启动首页、实例配置、云端连接与运行记录。
- 配置改为本机JSON，支持只读迁移旧Qt注册表设置；密码和令牌仅在内存；后台任务通过队列回到主线程更新界面。
- 网页面板采用同一深灰/紫色视觉，拆分登录、概况、实例与账号管理，适配手机；保留现有API与权限。
- 9项核心/API测试通过；浏览器登录、导航、临时预览开户刷新、手机宽度检查通过，无JavaScript错误。
- CustomTkinter源码与最终EXE启动检查通过；旧Qt安装包留在.local/backups；服务器保留旧镜像与面板归档。
- 新面板已Docker更新上线；真实HTTPS浏览器验证登录、指标、账号列表、退出；公开路径与未授权访问检查通过。证书、安全路径、账号与数据卷沿用。
- 新客户端为dist/Aetherloom/Aetherloom.exe及dist/Aetherloom-Windows.zip。自动Hop/Bridge/AUTO仍待完成。

## ECS正式部署：2026-11-16
- 用户明确授权部署后，已安装Docker/Compose、宿主Nginx、Certbot；部署目录/opt/aetherloom。
- HTTPS API443、面板38443+随机16位路径；后端仅127.0.0.1:8765。SSH18081保留。
- Let's Encrypt HTTP-01证书签发成功，至2027-02-13；certbot.timer和续期后Nginx重载钩子启用。
- 新增管理面板：管理员登录、内存/负载/磁盘/账号/实例统计、实例会话列表、账号列表及开户。
- Swagger默认关闭；API未登录401、普通用户管理403；登录限流；高位端口错误路径404，公开443不提供面板或开户入口。
- 9项本地测试通过。真实外网TLS验证通过：API健康200、面板正确路径200、错误路径404、未登录401、root登录和管理查询200。
- Docker Hub直连失败，使用Docker官方摘要锁定的Python3.11分发镜像；Python依赖锁版本，以Linux离线轮子构建成功。
- 访问资料仅在.local/deployment-access.json与.local/SERVER-HANDOFF.md，未提交。SSH口令不复制入仓库或镜像。
- 自动Hop、Bridge、AUTO、实例成员管理及完整恢复审批面板仍未交付，不把当前上线控制服务宣称为完整联机服务。

## 工作区迁移：2026-11-16
- 正式工作区：D:/Data_others/Aliyun-Server/上海华东2-书记宝宝-实例-Activity/codex。
- 项目目录：上述工作区下 Aetherloom/；保留 .git、.venv、runtime、dist、build、.local。
- 整体迁移前后10317个文件SHA256全部一致，总计1377571627字节。
- 迁移后修复虚拟环境激活路径和36个命令入口，检查软件已保存路径。
- 新路径8项测试全部通过；pip与PyInstaller入口可用。
- ECS仅只读检查，未安装/部署。域名artherlink.superyk7hero.online；计划目录/opt/aetherloom、API443、面板38443和16位随机路径，尚待实现及明确部署指令。
- 未提交的ECS只读检查资料、主机密钥记录完整保留在.local，不写入Git。
- 旧工作区CraftLink/MCsaves-sync继续作为参考；共同代码学习记录已复制到新工作区根目录。


## GUI/Docker交付更新
- 取消正版授权需求；游戏仅离线身份，软件账号保持独立。
- PySide6 GUI：手动目录/版本、隔离目录、Java、内存、启动、软件登录、实例查询、控制服务状态。
- 发行包含Temurin17 JRE与许可；游戏输出写入运行目录.aetherloom/logs。
- Dockerfile/Compose与DEPLOY.md；非root容器、命名卷、健康检查、资源限制。
- FastAPI账号认证、root初始化/CLI开户、实例/租约/提交API。会话口令仅保存在进程内存，密码PBKDF2。
- 8项测试通过，含真实Java17子进程、中文隔离路径、认证权限。GUI离屏启动与中文截图复查通过。
- 本机无Docker，CI加入容器构建与健康检查；以远端对应提交结果为准。
- 自动Hop、shared-playerdata/Bridge、AUTO与管理面板未完成；GUI云页只是控制API入口，不能开共享世界。
- 下文旧检查点描述保留为历史，其中GUI/HTTP/Java打包已完成，以本更新为准。
- Docker在GitHub Actions实际构建、非root启动、健康检查通过（977cb51与f55e9d7）。
- EXE初测发现打包器从PATH误收集的ICU DLL与Qt冲突；移除并使用Windows10/11系统ICU后EXE离屏启动退出码0。构建脚本已固化修复。
- 已修复Java17在英文Windows上的中文类路径编码问题：使用Windows原生短路径；路径无法表达且没有短路径时明确报错。
- 170aa0e对应远端CI全部通过：Windows测试、Ubuntu测试、Docker构建与健康检查。https://github.com/radix-Lunaris/Aetherloom/actions/runs/43722630250
- 交付文件：dist/Aetherloom-Windows.zip（附Java17）、dist/Aetherloom-Server.zip（Docker源码）。服务端上传清单和命令见DEPLOY.md。

## 已落地
- 从远端初始化提交克隆独立 Aetherloom 目录，建立 dev。
- 名称、计划、决策、GPLv3许可证、来源清单、跨Windows/Linux CI。
- 独立离线启动CLI：manifest继承、参数替换、libraries/assets检查、native解包、Java检查、直接启动。
- SQLite事务唯一Host、60s租约、epoch与父版本校验、独立恢复候选、Owner/manager恢复权限。
- SHA256分块快照与校验重组，无后台定期任务，保留spd_backup。

## 验证
6项unittest通过（Windows正常权限）。沙箱中os.replace遭拒，正常权限重跑通过。
新增原子块落盘补丁后全部6项测试再次通过；git diff --check通过。
没有真实游戏、Forge、双机或ECS实测。启动CLI尚未验证Forge47.4.22。

## 重要限制
这不是完成的首版，不能用于生产共同世界。
Authority是可信调用者的内部原语，尚无软件认证、HTTP接口、完整权限/审计、容量预留。
snapshot/materialize目前要求调用者保证世界已关闭；尚未集成OS游戏锁和Bridge。
materialize尚未处理云端删除文件、精确镜像、空目录与完整恢复备份；不是安全接管入口。
启动器暂仅离线身份，Java手动指定；native缓存清理、依赖哈希与旧资源格式兼容待完善。
尚未实现GUI、正版授权、shared-playerdata集成、Bridge、AUTO、完整编排、管理面板、安装与部署包。

## 下一步
1. 补启动器进程模拟测试、文件哈希与native ZIP限制，隔离缓存清理。
2. 获取shared-playerdata固定提交并保留MIT声明，接入单世界修复和冲突回归。
3. Forge Bridge及本地受保护协议，证明正常退出与锁释放。
4. HTTP认证和完整权限，世界锁/备份/精确checkout，AUTO适配与UI。
5. 获取用户准备的实际游戏目录，真实双机验证后才能合main。

远端描述修改未完成：当前连接未提供仓库元数据写接口，本机无gh。


## 2026-11-16 实质功能补齐（进行中）
- 用户保持现有CustomTkinter和Web样式，要求补齐账号、房间、真实联机。
- 离线启动补充clientid/auth_xuid等元变量；真实Java测试通过，未拿到用户实际游戏目录复测。
- CraftLink权限策略适配：root保护、admin/player、仅root任免admin、改名/改密/停用/删除、令牌撤销、玩家每自然月三次自助改名+改密、审计。
- 持久共享房间增加名称/环境/世界/模式、成员权限、转移Owner、删除；活动Host禁止删除房间，账号需先处理其拥有的房间。
- 11项本地回归测试通过。
- 服务端MySQL独立容器准备完成，迁移和备份执行中。客户端业务HTTPS使用47192；面板38443加原安全路径，443不承载业务。
- 尚未将UI房间记录误标为完整Hop；CraftLink AUTO与游戏Bridge仍需实际适配与验收。

- MySQL线上迁移通过：accounts=3,sessions=5,rooms=1，SQLite保留；control/mysql健康，外部HTTPS47192与原面板通过验证。
- Bridge Forge47.4.22完整编译/reobf成功，Java17辅助模块构建成功；尚无真实游戏双机验收。
- 已引入CraftLink未修改的AutoStream/AutoPeer/可靠UDP等传输源码（SOURCE.json含哈希与GPL许可）；统一软件认证接入TLS WebSocket中继，单成员共享UDP承载与独立流，AUTO在中继上先可用并后台尝试认证UDP打洞。
- 24项本地测试通过，包括上游流协议测试、真实WebSocket+UDP升级/多流/回退；发现连接关闭时ASGI重复close错误，已修正，需再次验证清理无错误。
- 正在补充单世界修复冲突测试、恢复审批、完整客户端包与第二次部署。


### 2026-11-16 持久化检查点：管理/网络已部署，游戏保存验收中
- 26项自动化测试已通过；后续增加了成员鉴权和Bridge错误回执，需最终重跑。
- MySQL独立临时库实测通过：模式、6位口令、8并发唯一Host、版本提交、改名冲突回滚、活动Host恢复保护、审计；临时库与授权已清理。
- 生产API已更新，HTTPS47192/WSS实际512KiB端到端往返通过，临时账号和房间已删除，原有房间未修改。
- Docker新目录受umask077影响无法由非root读取，已改COPY显式权限，并在up之前验证App工厂；先前失败更新已自动回滚，无数据覆盖。
- 用户提供实际游戏根：D:/Data_games/MC/PCL 正式版 2.8.12/.minecraft/versions/new/.minecraft，版本1.20.1-Forge（47.4.22）。检查已通过clientid参数，独立启动不调用外部启动器。
- 真实Minecraft：使用项目.local内独立运行目录和新测试世界；未加载或改动用户原有存档。已验证入世、自动LAN、协议763状态响应。
- 实测修正Bridge：需pack.mcmeta避免Forge警告页阻止自动启动；不能在ServerStartedEvent直接publishServer，因为LocalPlayer尚为空，现等玩家进入世界后开放LAN；路径匹配使用Files.isSameFile兼容8.3短路径。
- 正常退出的保存回执仍在实测诊断，未标记完整Hop通过。双机不同NAT、Host→Player→Host物品栏连续性尚未验收，main保持不合入。
- 已构建过Windows包，但最终交付需以Bridge最新验证结果重新构建，不能把之前dist当最终验收包。


### 2026-11-16 真实游戏关键检查点
- 实际1.20.1/Forge47.4.22的自动LAN、763状态查询、正常保存事件、Java文件锁释放、玩家数据归档及退出均通过。
- 真实ECS上的单机双身份顺序 A→B→A 接管通过，三次分别正常提交版本。A=3钻石/17级，B=2绿宝石/23级；A再接管仍为自己的3钻石/17级，且B阶段A玩家文件SHA-256不变。原用户存档未加载，测试房间已移除。
- Player自动加入仍在排查：直接LAN对照也超时，故不能归因于中继。现将Guest加入交给Bridge先执行Forge服务发现，待forgeData齐备后再ConnectScreen，避免仅依赖原版Quick Play；结果待实测。
- 退出保护已修正：仅clearLevel会等待未停的集成服务器，需先断开并halt(false)再clearLevel。修复后正常保存测试通过。
- 当前最新dev检查点4bbadad，后续修复尚需第二次提交/推送、重建客户端和同步服务端对应源码。main继续保留验收门槛。


### v0.1.0 发行候选：本轮已验证范围
- 本轮用户明确要求：将已验证版本推送dev、合并main并发行Release；当前交付范围按RELEASE_NOTES.md记录，不把未完成的跨电脑/NAT验证标记通过。
- 27项本地自动化测试通过；网络清理专项增加无ASGI错误断言与单侧提前关闭场景，并通过回归。
- 最终真实游戏：1.20.1/Forge47.4.22独立启动、自动LAN、正常保存/锁释放、ECS三次A→B→A接管通过。A=3钻石17级，B=2绿宝石23级，A再接管仍正确。
- 两个真实Minecraft进程经ECS中继自动加入通过，同时收到Player的Bridge入服确认；Player退出不上传，Host保存退出提交最终云版本。测试账号与房间已清理。
- Guest改用Bridge执行Forge服务发现，取得forgeData后连接；原版Quick Play的直接连接与LAN对照都曾出现握手超时，该实测修复已验证。
- 发行包含Windows完整包（Java17及两个Java辅助模块）、Docker服务端、校验和；包内BUILD_INFO.json追踪来源提交。测试Fixture模组不进入客户端包。
- 固定接口：HTTPS47192业务、HTTPS38443+原安全路径面板、52861/UDP端点发现，MySQL不发布主机端口。
- 发布操作进行中；最终合并、CI、Release及线上镜像回执以GitHub和本地.local记录为准。

## 2026-11-16 v0.3.0 联机状态与进度／Bridge 独立仓库
- 原因：旧联机页只渲染实际流事件，Host准备及没有Player时无流导致空白。现在持续显示角色、代次、加载阶段、LAN和对端数量；真实中继/P2P事件继续独立显示，不假报连接。
- 上传／下载／发布／恢复候选／Java安装接入顶部百分比，按实际字节及阶段计量；100%只在提交或安全替换完成后发出。分块传输仍为SHA-256缺失块增量，失败保留未完成百分比。
- Forge大整合包启动等待默认由180秒提高到900秒（边界120–1800）；等待期间保持原续租保护。
- 用户仓库1已原址改名Aetherloom-Bridge并推送GPLv3源码；应用保留可独立构建的源码副本并固定SOURCE.json，不引入子模块构建依赖。
- Java Agent/hook方案仅讨论，架构不变；它仍须适配Minecraft与加载器版本，不能承诺跨版本通用。普通离线启动不依赖Bridge。
- 验证进行中：自动化回归、GUI摘要和失败百分比、本地真实Host/Player会话；通过后推送dev并发行，不合main、不部署ECS。
- 验证已完成：48项自动化回归通过；GUI无流Host摘要、LAN端口、失败百分比保留和100%成功提示通过，并检查实际窗口布局。
- 本地真实1.20.1/Forge47.4.22双进程通过：Host无对端时ready摘要、Player自动入服active、原测试玩家23级/2绿宝石、Player退出不上传并关闭游戏、Host最终上传且游戏关闭。临时房间已删除，无生产ECS写入。
- 独立Bridge在本地及GitHub Forge build均通过，正常JAR包含GPL声明、不含测试Fixture；v0.1.0已发行，源提交58703f093407c8c34750313c86c5e828746c1a0b。

## 2026-11-16 Java Agent隔离实验
- 分支experiment/java-agent，基线v0.3.0/6b2d576；不合dev/main、不部署ECS。新配置默认bridge，实验Agent需在本地游戏设置显式启用并重新绑定。
- 实现Java8字节码、无第三方依赖的启动Agent，通过Instrumentation找到游戏类加载器，使用显式SRG映射和Forge公共事件控制生命周期；没有对每个实例单独编译Mod，也没有修改原始游戏JAR。
- 首轮真实测试暴露Agent参数中文编码及Forge事件转换线程上下文类加载器问题，均已修复。后续增加能力握手、实际UUID检查、远程身份失败断开、异步HTTP、保存确认后退出。
- 实测未安装Bridge Mod的1.20.1/Forge47.4.22副本已完成世界/LAN/正常保存/文件锁释放/游戏退出；自定义UUID双进程复测中。50项自动化回归通过，GUI通过。
- Java8/11/17/21/25的Windows与Linux矩阵是Agent引导检查，不是这些Java都可启动所有Minecraft；其他Minecraft/加载器仍阻止在线，不能将本实验当成广版本验收通过。
- 单EXE内嵌Agent/Bridge/修复器/GUI运行依赖；不捆绑Java，不要求客户额外准备JDK；构建仍唯一release目录。
- 当前玩家数据辅助器仍需Java17；将其连同NBT行为扩展至Java8/11尚未验证。因此本轮不开放旧版完整Hop，不用Agent引导检查掩盖这个限制。
- 真实Agent双进程完成：自动加入、自定义UUID首次保存后再次加入，23级/2绿宝石保持；Player退出不上传、Host最终提交和两个游戏自动关闭通过。测试世界是副本、本地临时服务，未修改生产ECS。结果在.local/agent-custom-uuid-result.json。
- 新增错误锁存：游戏控制报错后不接受后续ready/saved事件，已运行Host也禁止因后续正常保存绕过失败提交。

## 2026-11-16 手动Java版本选择
- 用户要求手动选择Java，不因推荐主版本阻止启动。保留自动推荐/官方下载严格匹配，仅手动和底层直接启动改为可尝试任意主版本或实验版；仍检测执行文件可用、x64/64位架构。
- GUI resolve_java与launcher.prepare均移除主版本硬拦截；在线Host/Player沿用选定绑定，不自动覆盖手动选择。提示推荐差异但明确允许尝试。
- 本机实际Java25执行声明Java17的最小游戏配置通过，含中文目录、继承参数与真实Java进程；不据此宣称所有Forge/Mod组合向下兼容。
- 桌面检查已通过；核心回归进行中。本轮在experiment/java-agent迭代v0.4.0a2，仍为Prerelease，不合dev/main、不部署服务器。

- 远端Windows桌面检查发现临时目录短路径/大小写别名导致手动选择提示匹配失败；改用规范化Path比较。v0.4.0a2候选未公开，保留源标签，不覆盖；修正后发行v0.4.0a3。51项本地回归通过，实际Microsoft Java25.0.3启动Java17配置通过。

## 2026-11-17 / 0.4.0a7 实验候选

- 已完成默认四线程存档块传输、Java Range 下载、CraftLink 完整 NAT 探测及双 UDP responder、十四项运行状态与短期成员在线心跳。
- Forge 1.20.1、AQS NeoForge 1.21.1（252 Mods/Java25）、Fabric 1.21.1、Quilt 1.21.1 均完成真实双玩家接续：重复加入、自定义 UUID、经验/物品、Player 不上传、Host 最终上传及角色交换。Forge 服务发现旧条件导致的回归已修复并复测通过。
- 67 项 Python 最终回归（48.985 秒）和桌面 smoke 已通过。映射与 ASM 来源声明已落盘。
- 用户明确授权本次 ECS 更新，并开放 UDP 52718、52719。部署须再次确认无活动 Host、备份 SQL/存档/配置，保留 MySQL 和 HTTPS；部署与公网测试回执保存在忽略的 .local。
- 下一步：最终回归、提交实验分支、唯一 release 构建、CI/预发行、ECS 更新及公网双端口实测。尚未将部署或公网 NAT 测试记为通过。

### 部署与公网复核

- ECS 已更新至 0.4.0a7，SQL、存档卷、原 HTTPS 配置均已备份。3 个账号、2 个房间、23 个版本和 MySQL 容器均保留，无活动 Host 时执行。
- UDP 52718、52719 已放行；容器内两方向 CHANGE-PORT 成功，Windows 本机访问两个公网端口成功。完整四端点实测为 NAT3/APDF，约 4.61 秒；此前公共端点只得到过滤未知。
- CI 发现英文 Windows 控制台无法输出 STUN 中文日志，补强 best-effort 日志并增加回归；6 项并发/STUN 测试通过。Agent Java 8/11/17/21/25 双平台启动检查、Linux 测试及 Docker CI 通过。
- Forge 官方 Maven 的 Gradle 插件解析再次失败；不跳过 Bridge 构建检查，不将未通过 CI 的预发行草稿标为已发布。本地缓存离线完整构建已通过。
- 将控制台日志修正纳入最终构建，完成来源一致的 ECS 补充更新；私有部署与构建回执保存在 .local。

## 2026-11-19 / 0.4.0a8

- 已按已安装实例自动选择联机控制，兼容既有绑定。Forge 47／1.20.1 优先 Bridge，其他 Forge、NeoForge、Fabric、Quilt 走 Agent。
- 新增无 Quick Play 的世界打开路径和较旧的连接接口，补 Forge 1.19.2 精确 SRG 别名。Fabric／Quilt 包含 16 组映射和同一系列补丁回退，新版可读类名路径及 ASM 9.8。
- 本机 Forge 1.19.2／43.4.12／Java 17 单机 Host 通过。双玩家脚本已验证自动加入、自定义 UUID 和 Player 退出不上传，完整接续结果记于私有测试回执。
- 69 项 Python 回归通过。扩展映射及运行时路径尚未覆盖每个版本实机组合，26.x 和全部整合包不计为已认证。交付仍为实验版单 EXE，复用现有 ECS 接口。

## 0.4.0a9 正式版覆盖

- 使用 Mojang 当前清单下载并校验 103 个正式版 JSON，含 1.0 到 26.3。逐版以测试文件运行原版启动计划生成，103 通过。结果和测试口径见 COMPATIBILITY.csv、COMPATIBILITY.md。
- 内置 39 个 Fabric／Quilt 精确映射，涵盖 1.14.4、1.15 至 1.21.11 所有正式补丁。检查每份资源的 SHA-256 和补丁索引；保留 Forge 两个精确别名的来源记录。
- 测试报告区分启动计划、映射覆盖和真实双玩家接续。26.x 未做完整接续实测。此迭代只更新客户端发布和兼容记录。
- Fabric 1.19.2／0.20.1／Java 17 同机双实例实测通过，包含两位玩家轮流托管、保存上传、重新加入和自定义 UUID。测试日志为 .local/fabric119-hop.log。

## 0.4.0a10 原版联机

- 原版联机增加 39 个精确混淆别名和 5 个 26.x 正式版所用的可读 API 路径。范围来自本项目 103 个正式版清单，另外 59 个历史原版版本仍需独立适配。
- 1.19.2 原版／Java 17 和 26.3 原版／Java 25 均通过同机隔离双实例接续，含两次 Host 保存上传、自定义 UUID 物品栏和经验、原 Host 重入。回执为 .local/vanilla119-final.log、.local/vanilla263-hop-v2.log。
- 修复原版混淆方法重名、Windows 首次并发存档缓存解析问题、26.3 玩家文件读取早于实体构建造成的身份错位。26.x 处理 `players/data` 和 `singleplayer_uuid`，保持既有文件分离。
- 26.3 用已迁移布局完成接续。原版旧布局升级后自动进入仍未通过，早期无内置 LAN 的版本仍需独立服务器方案，其他加载器组合保持原验收状态。

## 0.4.0a11 历史客户端适配

- 增加 15 个正式版的原版及 Legacy Fabric 精确映射和旧版客户端线程、开世界、LAN、连接及保存控制。1.13.2 使用显式端口接口，较老组合读取游戏自行分配的端口。
- 玩家数据辅助模块产出 Java 8 字节码，接续时支持旧版 UUIDMost／UUIDLeast，旁路保存失败保护不变。
- 验证采用编译、映射检查、自动化和桌面测试，未把新增历史版本列为双玩家全流程实测。仍缺 44 个历史原版版本的自动联机路径，尤其是无内置 LAN 的最早版本。历史 Forge 等其他命名空间不与 Legacy Fabric 混用。

## 0.4.0a12 历史原版联机候选

- 补齐 37 个正式版原版候选。16 个旧补丁按名称归档，21 个补丁按 UUID 处理。1.14 至 1.14.4 另有普通 Fabric 别名。保存事件及旧游戏进程退出后才处理归档上传。
- 75 项自动化测试及 Windows 桌面冒烟通过。新增版本未逐个启动 Minecraft。本轮只取得版本元数据和映射文件，没有下载 Minecraft 游戏二进制，之前清理的 loader-test 目录未重建。
- 1.0、1.1、1.2.1 至 1.2.5 缺少内置 LAN，兼容表保留独立服务端待办。官方清单中只有 1.2.5 的版本元数据提供服务端下载项。

## 0.4.0a13 启动前校验与本机 LAN 探测

- 采纳附件的 Agent 包预检与 LAN 端口探测，加入在线会话的现有启动流程。选择依据见 DECISIONS.md。
- 77 项自动化测试和 Windows 桌面冒烟通过，包含损坏 Agent 包与未监听端口用例。未下载或启动 Minecraft。没有新增版本适配，七个早期版本按用户决定保留离线启动。
- 测试后清理专用游戏版本下载与夹具链接目录，保留玩家既有游戏、已具有用途的测试存档和映射许可证记录。

## 0.4.0a14 在线会话与存档维护

- 复核本机两份 1.21.1 Forge 崩溃日志，均由游戏线程在 Quick Play 路径上抛出 LootModifierManager 未初始化异常。Forge 1.21.1 改用 Agent 主菜单进世界。使用现有 Forge 52.1.16 和隔离测试世界实测双玩家自动加入、UUID 物品栏与经验、保存上传、接续及原 Host 重入均通过。
- MCSync b31d0f9 提供区块与 NBT 核心，预览确认后清理副本，支持现有发布/增量下载。复用本地同 SHA-256 分片，云端仍验证完整文件，不主动清理在线权威版本。
- CraftLink 7d77067 的 punch.py 原样移植。Aetherloom 保留独立租约、端点登记、直连 HMAC、旧协议和中继回退。已通过真实回环 UDP 的 CraftLink 握手测试；用户现场 NAT 未验证。
- LittleSkin 房间标记继续可读取，准入按 Aetherloom 账号和会话身份统一处理；没有实机验证 LittleSkin 皮肤的跨客户端渲染。
- 79 项自动化测试及桌面冒烟通过，没有下载测试游戏。本轮没有部署 ECS。

## 0.4.0a15 Windows 路径修正

- v0.4.0a14 的 Windows CI 发现真实目录与 8.3 短名别名无法直接比较。生成区块清理计划时统一解析实际路径，再校验是否位于所选世界下。a14 保留为未发布草稿。

## 2026-11-23 · 工作台与面板升级

本地已接入角色、启动选项、房间环境匹配、应用 UDP、会话流、设置授权及入口试运行。原 79 项测试与桌面冒烟已通过，新增实际 UDP 中继回环通过。生产部署前核对租约、备份、Nginx 配置及新入口回退，公网 P2P 与真实整合包待独立复核。

### a16 发行与线上验证

发行来源为 dev 提交 481f348，单文件客户端自检、80 项本地测试和 14 项 GitHub CI 均通过。ECS 已升级；MySQL 容器、账号、房间与存档版本元数据在切换前后核对一致。公网浏览器验证了登录、双主题、房间与会话流页面及授权账号选择。面板入口已验证同入口确认、新路径可达、旧路径拒绝确认和 180 秒回退。业务 UDP 的双向数据报在实际生产中继通过，单流撤销通过。

Forge 52.1.16 / Minecraft 1.21.1 使用独立测试世界完成两端加入、退出上传、角色背包经验核对、托管接续与原 Host 重入。模组清单单独验证了客户端专用模组、缺失必需项和加载器不匹配。该轮双客户端游戏实测为同机运行，尚无两处真实 NAT 环境的直连、UDP 路径热切换和故障恢复验收记录。安全路径、凭据及私有部署回执不进入版本库。

## 2026-11-27 · Host 联机预设与桌面体验

工作区迁至 VPS 下的 Aetherloom 项目。接入 Host 预设、登录会话恢复、页面头像、存档封面与 MCSync 清理控件。原档清理使用独立全量备份，权限验证与桌面预览不改动线上实例。30 天会话有效期随服务端包提供，当前部署需另行授权。

Forge 1.21.1 / 52.1.16 实测通过禁止 PvP、创造模式、开启作弊及关闭正版验证组合下的双客户端加入、退出上传、换 Host 和重新加入。Windows 桌面自检覆盖了加密会话恢复、512 像素封面与无封面回退。临时服务端验证了 12 小时默认会话、30 天可选会话和退出撤销。

用户确认保留 Minecraft 内置局域网服务器。Host 预设扩展了难度、视距、模拟距离、时间、天气、世界边界和版本原生规则，代理限制房间人数及软件账号。PLAY.md 记录了哪些值进入存档及独立服务端专用选项。
