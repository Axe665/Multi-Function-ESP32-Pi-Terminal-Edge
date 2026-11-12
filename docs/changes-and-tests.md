# 本次改动与测试记录（端边云联调）

日期：2026-11-12/13
范围：边节点（本仓库）的云连接、搜索云、非容器部署、启动弹窗与网页设置页。

## 一、改动清单

### 1. 云连接（edge/）

| 文件 | 改动 |
|---|---|
| `edge/config.py` | 新增 `apply_cloud_override()`：读 `data/cloud.json` 覆盖 `CLOUD_URL` / `CLOUD_TOKEN`，优先于环境变量，重启保留 |
| `edge/api.py` | 新增 `POST /api/v1/cloud/config`（运行时配置云地址/令牌）、`GET /api/v1/cloud/discovery`（现场搜索 `_orpi-cloud._tcp`）；补缺失的 `import json` |
| `edge/mdns.py` | ① `EDGE_LAN_IP` 覆盖广播地址（多网卡/代理网卡时会广播 198.18.x）② 新增 `browse_cloud(seconds)` 现场搜索云 ③ `browse_cloud` 与 `_CloudListener` 都优先用 TXT 的 `url` 字段（IP 字面量做 TLS SNI 会被网关判 421） |

文档依据：README `mDNS` 行（广播 `_orpi-edge._tcp`、发现 `_orpi-cloud._tcp`）、§8.4（mDNS 只解决地址，信任靠 CA 指纹）。

### 2. Web 前端（web/）

| 文件 | 改动 |
|---|---|
| `web/src/views/Settings.vue` | 设置页新增「云连接」卡片：云地址 + 访问令牌 + 保存并连接 + 搜索云（列出节点地址、CA 指纹、可信状态，点连接即写入并上报一次） |

### 3. 非容器部署（deploy/、scripts/）

| 文件 | 改动 |
|---|---|
| `deploy/systemd/edge-{node,web,mqtt}.service.in` | 三个 systemd user 服务模板（`EnvironmentFile` 读 `deploy/edge.env`） |
| `scripts/install_systemd.sh` | 渲染路径/npm 路径 → 安装 unit、`enable --now`、复制图标、写应用菜单、放桌面快捷方式 |
| `deploy/edge.env.example` | 运行环境模板（MQTT/云，token 留空；`EDGE_DEMO=0` 关闭演示横幅） |
| `deploy/edge.desktop.in` + `deploy/icons/edge.svg` | 应用「边」的菜单项与图标（端-边-云三节点） |

### 4. 启动弹窗（tools/edge-launch/）

| 文件 | 改动 |
|---|---|
| `tools/edge-launch/edge_launch.py` | tkinter 小窗：本机/局域网网址 + 打开按钮、启动/关闭边服务、开机自启开关；异步启停（`systemctl --no-block`）、防抖、按期望状态轮询、`pack` 自适应布局、配色对齐 `web/src/styles/m3.css` 亮色 token |
| `tools/edge-launch/edge-launch.desktop` | autostart 模板 |
| `tools/edge-launch/README.md` | 使用说明 |

### 5. 其它

| 文件 | 改动 |
|---|---|
| `.gitignore` | 增加 `cloud-certs/`、`.venv/`、`deploy/edge.env`（证书/虚拟环境/本机配置不入库） |
| `README.md` | 补「非容器部署」说明（systemd 与 Compose 等价） |
| `docker/mosquitto/edge-local.conf` | 本机联调 broker 配置（18883 mTLS + ACL） |

### 6. 未改动 / 未引入

- 没有新增 Python/Node 第三方依赖（zeroconf、cryptography、httpx 等均为原仓库已有）。
- 模型、显卡相关代码与配置未触碰。
- 容器部署方式（`docker/compose.yml`）保持原样。

## 二、测试结果

### 1. 搜索云（mDNS）

```
$ avahi-browse -rt _orpi-cloud._tcp
  address = [192.168.31.184]  port = [8443]
  txt = ["ca_fp=0604bb19eea1493e" "url=https://cloud.local:8443" ...]

$ GET /api/v1/cloud/discovery
{"pinned_fp":"0604bb19eea1493e",
 "found":[{"url":"https://cloud.local:8443","ca_fp":"0604bb19eea1493e",
           "name":"cloud-lab-01","trusted":true}]}
```

### 2. 边 → 云（mTLS + 边令牌）

```
POST /api/v1/report/cloud
{"queued":false,"cloud":"ok",
 "detail":"{\"accepted\":true,\"duplicate\":false,\"rows\":0}"}
cloud: {configured: true, last_sent_at: 1794508050229, last_error: null}
```

### 3. 树莓派 → 边 → 云（假数据灌入）

- 树莓派上 4 台设备 × 288 个 5 分钟窗口（24h），`POST /ingest/telemetry`（Bearer ingest token）
- 边：`batches = 575`，`devices = mt-3b-01 / mt-fake-01 / mt-fake-02`
- 云库：`reports = 10`、`telemetry_daily = 96` 行（`mt-3b-01` 的血压三项各 30 天）

### 4. 部署与服务管理

```
edge-node = active/enabled   edge-web = active/enabled   edge-mqtt = active/enabled
自启开关：disable → disabled → enable → enabled
关闭服务：stop → inactive ×3；启动服务：start → active ×3，网页 5173 = 200
```

### 5. 图标与启动项

- `~/.local/share/icons/hicolor/scalable/apps/edge.svg` 已安装
- `~/.local/share/applications/edge.desktop`：Name=边，Exec/Icon 正确
- `~/桌面/edge.desktop` 桌面快捷方式可执行

## 三、部署方式（两种并存，均可使用）

| 方式 | 组成 | 适用 |
|---|---|---|
| **容器**（文档 §5.1，官方） | `docker/compose.yml` 四服务：mosquitto / ingest / api / web | 生产/完整部署；靠 `restart: unless-stopped` + docker.service 自启 |
| **非容器**（开发机补充） | systemd user：edge-node（8001）/ edge-web（5173）/ edge-mqtt（18883） | 开发机裸跑，改代码即时生效、省资源 |

两种方式**并存**：容器部署的代码与 compose 文件本分支未改动，可照常使用；
非容器只是给开发机多提供一种启动方式，不替代容器部署。

```sh
# 容器（原方式，不变）
cd docker && docker compose up -d --build

# 非容器（可选）
cp deploy/edge.env.example deploy/edge.env   # 按需改
./scripts/install_systemd.sh                 # 装服务 + 图标 + 桌面入口
systemctl --user status edge-node edge-web edge-mqtt
```

## 四、已知注意

- 云用 IP 直连 8443 会被 Caddy 判 `421`（IP 字面量不发 SNI）；需要域名访问
  （本机 `/etc/hosts` 加 `192.168.31.184 cloud.local`），或由云仓同时接受 IP 站点。
- `EDGE_DEMO=1` 时网页顶部会显示「演示数据，mock 生成」；部署模板里已设 `EDGE_DEMO=0`。
- `cloud-certs/`、`data/`、`.venv/` 不入库，按部署环境自行生成。
