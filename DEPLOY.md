# Aetherloom Docker 控制服务部署

当前交付为离线启动GUI及控制API开发版。**自动Hop、Bridge、AUTO联机尚未完成**；不要把此包作为已经可用的共同存档联机服务。
不提供Minecraft正版登录。软件账号仅用于ECS服务。

## 客户端
解压 Aetherloom-Windows.zip 后运行 Aetherloom.exe。
手动选择完整.minecraft、版本和Java；运行目录为空时使用根目录，隔离实例请选择真实游戏目录。
发行包附带Temurin Java17；也可指定适配的Java。不会调用HMCL/PCL或下载游戏。
云服务页可登录、查询实例和服务器状态；实例创建仅为控制层记录。

## 上传什么
将 Aetherloom-Server.zip 解压至 /opt/aetherloom。压缩包包含：
aetherloom/、server/、compose.yaml、.dockerignore、LICENSE及本说明。
不要上传客户端EXE、.minecraft、.venv或本机账号配置。

Ubuntu24.04上先安装Docker Engine及Compose插件（使用Docker官方Ubuntu安装说明）。
也可使用Ubuntu24.04仓库的软件包：
```bash
sudo apt update
sudo apt install -y docker.io docker-compose-v2 unzip
sudo systemctl enable --now docker
```
以下Docker命令需以root执行，或在前面加sudo。
首次部署：
```bash
cd /opt/aetherloom
docker compose build --pull
docker compose run --rm control python -m aetherloom.server init-root
docker compose up -d
docker compose ps
curl http://127.0.0.1:8765/health
docker compose logs --tail=100 control
```
init-root交互输入12位以上密码，不在命令行或Compose中保存密码。不要重复初始化已有root。
服务默认只绑定127.0.0.1:8765，前置HTTPS反向代理后供客户端访问。
如仅测试，可建立SSH本地转发：ssh -L 8765:127.0.0.1:8765 user@ecs，客户端连接http://127.0.0.1:8765。
不要把软件密码通过公网明文HTTP发送。

数据存储在Docker命名卷aetherloom-data（实际卷名前缀由Compose项目决定）。
更新：上传新源码后 docker compose build --pull，再 docker compose up -d。
停止：docker compose down。**不要使用 down -v，它会删除数据卷。**
备份须先停止服务，再备份整个数据卷（含SQLite及blobs），恢复到空卷后启动。
容器使用非root用户、512MiB限制、单worker；按实际空间管理数据。

## HTTPS 与管理面板

控制服务采用Docker，Nginx反代采用宿主机服务。客户端API使用443；管理面板使用38443及每次部署单独生成的16位字母数字路径，且仍需root/admin登录。
Compose中设置 AETHERLOOM_PANEL=1 才会提供面板静态页面。后端8765保持本机绑定；Nginx公开443仅转发API及health，不转发面板静态资源，/api/users仅在面板入口提供。
FastAPI的/docs和/openapi.json默认关闭。面板支持资源概况、实例与会话只读列表、账号列表与开户；不代表自动Hop已经实现。
证书使用Let's Encrypt HTTP-01，域名解析到服务器后无需TXT记录；80端口保留验证路径用于续期。Certbot续期后执行nginx -t并重载。
真实入口、root初始密码与本次验证结果保存在部署工作区.local，禁止提交。

## 网络受限环境的离线依赖构建

server/requirements.txt锁定已验证依赖版本。可在联网机器准备Linux amd64/Python3.11轮子：
```bash
python -m pip download --only-binary=:all: --platform manylinux_2_28_x86_64 --platform manylinux2014_x86_64 --python-version 311 --implementation cp --abi cp311 -r server/requirements.txt -d wheelhouse
docker compose -f compose.yaml -f compose.offline.yaml build
docker compose -f compose.yaml -f compose.offline.yaml up -d
```
把wheelhouse/与源码一同上传。可在.env设置 COMPOSE_FILE=compose.yaml:compose.offline.yaml，后续直接使用docker compose。
基础镜像可由 AETHERLOOM_PYTHON_IMAGE 指定分发源，但应锁定并核对Docker官方Registry摘要；不要将不明镜像直接当作官方镜像。

## 创建普通软件账号
最简单的方式（需服务器Docker管理权限）：
```bash
docker compose exec control python -m aetherloom.server create-user --username friend
```
按提示输入12位以上密码；创建服务器管理员可附加 --role admin。

也可通过高位端口的安全路径进入管理面板，由root/admin开户；只有root可创建服务器admin。
GUI在云服务页填写同一服务器地址、软件账号与密码登录。

## 当前验证边界
本机没有Docker引擎；170aa0e在远端CI通过Compose构建、非root容器启动与健康检查：
https://github.com/radix-Lunaris/Aetherloom/actions/runs/43722630250
源码API通过本地TestClient测试；客户端通过离屏GUI测试和EXE启动测试。
真实Minecraft/Forge及双机Hop均未验证。所有缺项记入CHECKPOINT.md。

