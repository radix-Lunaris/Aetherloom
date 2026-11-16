# Aetherloom 工作约定

- 客户端独立实现，保留 CustomTkinter 现有界面风格；不调用 HMCL/PCL，不引入其源码。账号令牌和部署凭据不得进入日志、Git 或发行包。
- 最终构建产物只在项目根目录 `release/` 保留一份。使用 `scripts/build-release.ps1`，交付为单文件 `Aetherloom.exe`、`Aetherloom-Server.tar.gz` 和 `SHA256SUMS.txt`，不额外生成客户端 ZIP、dist 副本或版本子目录副本。
- Java 不捆绑进客户端；支持已知位置发现、按实例自动选择和用户点击的官方校验下载。Java 辅助 JAR 嵌入单文件 EXE，冻结程序从 `_MEIPASS/assets` 访问。许可证嵌入 EXE，可在“运行记录→许可与来源”查看。
- 成功构建后清除当前项目生成的中间产物和旧 dist；不得删除用户世界、配置、账号、依赖缓存、安装的 Java 或其他项目。任何递归清理先验证绝对路径与链接状态。
- 每次版本迭代更新版本与发行说明、验证并推送 dev，发布一次对应 GitHub Release。标签与附件必须匹配已通过 CI 的来源提交，不覆盖既有已发布版本。开发阶段可从 dev 发布；main 合并仍须符合用户验收／明确要求。
- 服务器部署只在用户明确要求时执行，先检查活动 Host、备份数据库和存档卷，保留 HTTPS、既有端口、安全路径和独立 MySQL 数据。
- 将阶段验证、阻塞、下一步记录在 CHECKPOINT.md；私有部署回执和凭据只放被忽略的 .local。
