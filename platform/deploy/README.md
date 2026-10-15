# 云部署准备与验收

当前尚未上线。生产模板使用 SQLite 私有数据卷、Waitress 和 Caddy HTTPS 入口，不需要修改本地运行配置。容器编排尚需在安装 Docker Compose 的目标服务器上验证。

## 首次部署

准备一台支持 Docker Compose 的 Linux 服务器和域名，将域名 DNS 指向该服务器，开放 TCP 80/443。进入服务器上的 platform 目录：

```sh
cp deploy/deploy.env.example deploy.env
# 修改 deploy.env 内 FT_DOMAIN 为真实域名，不含 https:// 或路径
docker compose --env-file deploy.env -f compose.production.yaml config --quiet
docker compose --env-file deploy.env -f compose.production.yaml build
docker compose --env-file deploy.env -f compose.production.yaml up -d
docker compose --env-file deploy.env -f compose.production.yaml logs --tail=100
```

此文件独立使用，不与 compose.yaml 合并。仅 Caddy 发布端口，应用 4180 不对外发布。FT_PROXY_IP=* 仅适用于这个隔离的双容器网络；不要给 ft 发布端口，也不要把其他不可信容器接入这个网络。Caddy 覆盖 HTTPS 转发头，Waitress 只信任协议头。

首次启动为空库。查看本机私有初始化密钥后，在 HTTPS 页面创建管理员：

```sh
docker compose --env-file deploy.env -f compose.production.yaml exec ft cat /data/initial-setup.txt
```

不要分享初始化密钥或写入日志。现有本机数据迁移尚未执行；如需迁移，先停服配套备份，在副本演练，再安排正式切换。不要在空库创建业务数据后直接覆盖为本机库。

## 停服备份与恢复演练

数据库与附件需要同一停服窗口备份。服务器 platform 目录下执行：

```sh
mkdir -p backups
docker compose --env-file deploy.env -f compose.production.yaml stop ft
docker compose --env-file deploy.env -f compose.production.yaml run --rm --no-deps ft python backup.py
# 上条输出 /data/backups/时间戳，用实际时间戳替换下面占位值
docker compose --env-file deploy.env -f compose.production.yaml cp ft:/data/backups/时间戳 ./backups/
docker compose --env-file deploy.env -f compose.production.yaml start ft
```

任一步失败先核查原因；备份完成或决定中止后恢复应用服务。备份包含密钥，限制目录权限，并复制到服务器以外的受控存储。不要执行 down -v，该命令会删除数据卷。

新版 backup.py 自动生成 manifest.json，记录数据库、附件和密钥文件的大小与 SHA-256，检查 SQLite 完整性后才生成最终备份目录。失败的临时备份不会作为完成备份发布。校验清单用于发现损坏或缺失，不是数字签名；备份仍需受控保存。此工具只支持 SQLite。

本地检查备份与恢复到一个尚不存在的目录：

```sh
python backup.py --verify /path/to/backup
python backup.py --restore /path/to/backup --to /path/to/new-runtime
```

恢复会先校验备份，再复制并复验；目标目录已存在时拒绝操作，不提供覆盖选项。恢复后仍需检查应用登录、业务记录和私有附件。旧版无 manifest.json 的备份不支持这个自动校验/恢复命令，保留原备份并按旧版人工流程在副本演练。备份前必须停服，工具不能代替停服协调。

恢复先在独立项目/数据卷演练：停服并备份目标数据，把备份内的数据库、uploads 目录与密钥文件整体还原到目标 /data，确保容器用户 10001 可读写，再执行 migrate 并启动。正式恢复须确认备份和目标，不能直接覆盖当前资料。

## 一键备份流程（服务器部署后使用）

宿主机安装 Python 3.11+、Docker Compose，使用和部署相同的系统账号，在 platform 目录执行：

```sh
python3 backup_compose.py --destination /mnt/ft-backups
```

脚本使用 deploy.env 和 compose.production.yaml，先验证 Compose 配置和应用运行状态，再停服备份；无论备份成功与否都会尝试启动应用。正常备份结束后先启动服务，再复制到宿主机临时目录并校验，校验成功才生成最终备份目录。过程中有短暂停机，页面可能显示代理错误，应安排在允许的维护窗口。

目标路径应是有受控权限的独立挂载盘，并另行安排异地保存。脚本不会创建远程存储、删除旧备份或安装定时任务。退出码 0 表示复制及校验成功，非 0 需检查备份和服务状态；Compose start 成功不代表应用已通过健康验收。宿主机断电或强制结束进程可能使服务停留在停止状态；检查并恢复服务后，才可删除 platform/.compose-backup.lock 重试。该锁也会阻止同一项目目录中的重叠备份。

Docker 实机验收前不要启用周期运行。后续需确定维护窗口、调度方式、失败告警、保留期限和异地备份位置。

## 上线验收清单

- HTTP 跳转 HTTPS，证书可信；登录不循环跳转，注销后私有附件无法读取。
- 首次初始化只能创建一次管理员；管理员、编辑、只读权限分别验证。
- 使用隔离测试环境验证配置录入、图纸上传下载、库存调拨与分批签收。
- 公司外手机网络可登录、查询、录入；验证实际允许的最大附件上传。
- 重建应用容器后资料及附件仍在，服务器重启后自动恢复服务。
- 完成数据库和附件配套恢复演练，并确认异地备份负责人、频率和保留期限。

以上通过后才能标记云部署完成。PostgreSQL、对象存储、旧库迁移和自动备份调度仍未实现或验收。

代理配置依据：[Caddy reverse_proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy)、[Waitress 参数](https://docs.pylonsproject.org/projects/waitress/en/stable/arguments.html)。
