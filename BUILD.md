# 构建与发行

Windows Python3.11：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-desktop.txt
# 设置 JAVA_HOME 为 JDK17；或使用项目 .local/jdk17 中的构建 JDK。
powershell -ExecutionPolicy Bypass -File scripts/build-release.ps1
```

最终产物只保留在项目根目录 `release/`：

- `Aetherloom.exe`：独立单文件客户端，直接运行，不需要旁边的 _internal、assets 或 runtime 目录，也不另生成客户端ZIP。
- `Aetherloom-Server.tar.gz`：Docker服务端上传包，包含独立MySQL容器配置、源码和部署说明。
- `SHA256SUMS.txt`：上述两个文件的校验和。

构建后清理本项目的旧dist和编译中间目录，不另外复制到版本子目录。用户世界、配置、依赖缓存和已安装Java不清理。构建两个Java辅助模块仍需构建机JDK17；辅助JAR嵌入单文件EXE，运行时从PyInstaller临时资源目录加载，构建结束不在源码目录留下JAR副本。

客户端不捆绑Java。自动发现已知系统／用户／游戏运行时并选择匹配版本；缺失时用户可点击官方校验下载。下载的Java在客户端配置目录 `java` 下，保持与发行产物分开。

PyInstaller收集CustomTkinter的主题／字体／图片以及项目和第三方许可证。EXE内的许可证在“运行记录→许可与来源”查看。源码与许可见 https://github.com/radix-Lunaris/Aetherloom 。

## 每轮发布

1. 更新项目版本、`aetherloom.__version__`、面板版本和 RELEASE_NOTES.md；完成相应验证后提交并推送dev。
2. 从该提交执行完整构建，检查来源提交、SHA-256和单文件EXE启动。
3. 建立不覆盖旧历史的对应版本标签（例如v0.2.0），推送标签。
4. `.\.venv\Scripts\python.exe scripts/publish_release.py verify` 校验唯一一份本地产物；`stage` 创建草稿并直接上传release目录中的文件。
5. 同一来源提交的Core checks通过后执行 `publish` 公开发行版，不覆盖已发布附件。

发布工具使用现有Git凭据，仅在内存中处理，不写令牌。开发阶段Release可来自dev；main仍在用户验收／要求后合入。服务器部署需要用户明确要求，不随发布自动执行。

桌面检查：`python scripts/smoke_desktop.py`；核心检查：`python -m unittest discover -s tests -v`。源码运行共享功能前需构建Java模块；完整发行构建会自动处理和清理这些中间文件。Docker构建与升级见DEPLOY.md。
# 实验 Agent 构建

实验分支的完整构建会先用已有开发JDK编译无第三方依赖的Java8字节码Agent，并连同Bridge、玩家数据修复器、Python及GUI运行依赖嵌入唯一的Aetherloom.exe。客户电脑不需要开发环境；Java从已有安装识别，发行包不包含Java。单独验证Agent可运行 `python scripts/build_agent.py`，但最终交付使用完整构建脚本并清理中间JAR。

LittleSkin发行构建会在开发机获取固定SHA-256的authlib-injector1.2.8并内嵌EXE，用户无需下载。Forge开发依赖已有缓存时可使用 `scripts/build-release.ps1 -Offline`，该模式仅跳过离线构建无意义的Forge证书预检，网络认证HTTPS校验不受影响。缺失构建依赖仍报错，不从未验证镜像补齐。
