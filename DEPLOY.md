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

## 创建普通软件账号
最简单的方式（需服务器Docker管理权限）：
```bash
docker compose exec control python -m aetherloom.server create-user --username friend
```
按提示输入12位以上密码；创建服务器管理员可附加 --role admin。

也可通过API：
运行服务后，在服务器本机浏览 http://127.0.0.1:8765/docs（远程可通过上述SSH转发）。
POST /api/login 以root登录，得到token。
页面Authorize输入token（若该版本文档未显示Authorize，可用curl附Authorization: Bearer TOKEN）。
POST /api/users，JSON为 {"username":"friend","password":"至少12位密码","role":"player"}。
GUI在云服务页填写同一服务器地址、软件账号与密码登录。

## 当前验证边界
本机没有Docker引擎；远端CI配置了Compose构建和容器健康检查，结果以对应提交的Actions为准。
源码API通过本地TestClient测试；客户端通过离屏GUI测试和EXE启动测试。
真实Minecraft/Forge及双机Hop均未验证。所有缺项记入CHECKPOINT.md。

