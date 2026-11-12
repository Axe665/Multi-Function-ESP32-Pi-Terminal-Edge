# PR：边节点的云连接、搜索云与非容器部署

## 摘要

本分支给边节点补齐了「上云」这条链路的可操作性，并给开发机补了非容器部署方式。

1. **云连接可运行时配置**：`data/cloud.json` 覆盖 `CLOUD_URL/TOKEN`，新增
   `POST /api/v1/cloud/config`，不必改环境变量重启。
2. **搜索云**：`GET /api/v1/cloud/discovery` + `mdns.browse_cloud()`，现场搜
   `_orpi-cloud._tcp`，返回地址、CA 指纹与是否可信；Web 设置页可直接连接。
3. **mDNS 修复**：① `EDGE_LAN_IP` 覆盖广播地址 ② 云发现优先用 TXT 的 `url`
   （IP 字面量做 TLS SNI 会被网关判 421）。
4. **Web 设置页**：新增「云连接」卡片（地址/令牌/保存并连接/搜索云）。
5. **可选非容器部署**：`deploy/systemd/*.service.in` + `scripts/install_systemd.sh`，
   装成 systemd user 服务（edge-node/edge-web/edge-mqtt）并生成「边」的图标、
   应用菜单与桌面快捷方式。
6. **启动弹窗**：`tools/edge-launch/edge_launch.py`，显示本机/局域网网页地址，
   并提供启动/关闭服务与开机自启开关。

## 测试

见 `docs/changes-and-tests.md`：搜索云（mDNS + 指纹）、边→云 mTLS 上报（ok）、
树莓派→边→云灌数（575 批 / 云 96 行）、systemd 自启与启停、图标与启动项。

## 如何验证

两种部署方式（容器 + 非容器）**都活着**：容器是原方式、本分支未改动其代码与 compose；
非容器是给开发机新增的启动方式，二者并存、不互相替代。

```sh
# 容器方式（原方式不变）
cd docker && docker compose up -d --build

# 非容器方式
cp deploy/edge.env.example deploy/edge.env
./scripts/install_systemd.sh
systemctl --user status edge-node edge-web edge-mqtt

# 云连接（示例）
curl -X POST localhost:8001/api/v1/cloud/config \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://cloud.local:8443","token":"<edge token>"}'
curl -X POST localhost:8001/api/v1/report/cloud
curl localhost:8001/api/v1/cloud/discovery
```

## 注意

- 没有新增 Python/Node 第三方依赖；模型与显卡相关代码未动。
- `cloud-certs/`、`data/`、`.venv/` 不入库。
- 云用 IP 直连 8443 会 421，需要域名（如 `cloud.local`）并在 hosts 映射。
