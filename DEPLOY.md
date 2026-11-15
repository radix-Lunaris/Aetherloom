# Docker服务端与HTTPS部署

Aetherloom控制服务与MySQL各用一个Docker容器，数据库不发布主机端口。容器通过私有Docker网络使用 `mysql:3306` 连接；容器的127.0.0.1各自独立，不能相互连接。

生产路径 `/opt/aetherloom`。客户端业务为HTTPS **47192**；面板为HTTPS **38443 + 16位随机路径**，二者不相邻。443不提供业务接口；80仅保留证书HTTP-01验证。

## 上传与首次构建

上传 `dist/Aetherloom-Server.zip`，解压到 `/opt/aetherloom`。包里有aetherloom、server、Compose、环境示例和说明。不要上传EXE、游戏目录、.venv或本机配置。

Ubuntu24.04安装Docker Engine/Compose和Nginx、Certbot。然后以root执行：

```bash
cd /opt/aetherloom
cp .env.example .env
chmod 600 .env
# 编辑.env，把两个MYSQL密码改为不同的随机密码；不改变软件账号密码。
docker compose build
docker compose up -d --wait mysql
docker compose run --rm --no-deps --entrypoint python control -m aetherloom.server init-root
docker compose up -d --wait control
curl --fail http://127.0.0.1:8765/health
```

init-root交互输入软件root账号密码，最低6位。已有root不要再次初始化。root改密通过SSH执行 `docker compose exec control python -m aetherloom.server reset-root`，交互输入新密码并撤销旧会话。普通软件账号通过面板创建。后端HTTP只绑定宿主机127.0.0.1:8765。

数据卷：`aetherloom-data`保存内容寻址块及保留的旧SQLite；`aetherloom-mysql`保存权威元数据。实际卷名带Compose项目前缀。不要执行 `docker compose down -v`。

## Nginx、证书与端口

域名 `artherlink.superyk7hero.online` 解析到ECS。证书使用Let's Encrypt HTTP-01，不需要TXT记录；80端口的验证目录和certbot.timer用于自动续期。

`server/nginx.conf.template`用于配置47192业务入口与38443面板入口；替换域名、端口和安全路径。生产配置含16位路径，不提交仓库。也可在私有部署profile含api_url/panel_path后，运行 `scripts/render_nginx.py --profile 私有profile.json --output 私有nginx.conf`，默认API47192、面板38443。

Nginx需加载WebSocket Upgrade设置，`/api/relay`与API一起使用47192 TLS。业务入口屏蔽账号管理和审计路由；账号管理从面板安全路径进入，仍须root/admin认证。443全部返回404。

安全组及防火墙开放：SSH管理端口、80/TCP、47192/TCP、38443/TCP；P2P发现使用52861/UDP。MySQL3306和后端8765不开放公网。52861映射到control容器，只有HTTPS发出的短时能力凭据才得到端点发现回复；UDP失败时AUTO继续使用中继。

实例root初始密码、面板路径及交接资料只保存在本地 `.local/SERVER-HANDOFF.md`。软件账号令牌不进入游戏命令行。Bridge使用单次随机凭据和回环HTTP，不向外提供控制接口。

## 更新与备份

更新前备份两个数据卷及配置。MySQL逻辑备份示例（输出文件要保持私有）：

```bash
umask 077
mkdir -p backups
docker compose exec -T mysql sh -c 'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction --routines --triggers aetherloom' > backups/aetherloom.sql
# 内容寻址块不可省略；停control后备份aetherloom-data卷。
docker compose stop control
# 使用Docker卷备份工具完整备份aetherloom-data，记录与SQL备份的一致检查点。
docker compose build control
docker compose up -d --wait control
```

停服备份两个完整卷可取得更明确的一致检查点。恢复到空卷，并同时恢复MySQL元数据与对应块。仅恢复SQL而丢失blobs会导致世界无法校验。

原SQLite迁移工具：停API、备份旧数据后，在新MySQL空库运行 `docker compose run -T --rm --no-deps --entrypoint python control -m aetherloom.migrate_mysql /data/authority.db`。工具拒绝覆盖非空目标、逐表核对数量，保留原SQLite。切换失败使用迁移前镜像、Compose和原SQLite回退。不要在已迁移生产库重复运行。

## 网络受限环境

在联网机器准备Linux amd64/Python3.11依赖：

```bash
python -m pip download --only-binary=:all: --platform manylinux_2_28_x86_64 --platform manylinux2014_x86_64 --python-version 311 --implementation cp --abi cp311 -r server/requirements.txt -d wheelhouse
```

将wheelhouse和源码一并上传，使用 `docker compose -f compose.yaml -f compose.offline.yaml build` 及相同文件组合up。可在.env设置 `COMPOSE_FILE=compose.yaml:compose.offline.yaml`。镜像源分别由AETHERLOOM_PYTHON_IMAGE、AETHERLOOM_MYSQL_IMAGE指定；生产应核对官方摘要并固定。不能把未经核验的镜像当作官方镜像。

## 当前验证边界

服务端MySQL迁移和HTTPS已部署验证；游戏Bridge、Hop编排和AUTO具有实现与自动化验证，但真实双机Minecraft验收尚未完成。使用流程及限制见PLAY.md，不将构建成功视为真实游戏验收通过。
