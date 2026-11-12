# 边节点管理台（Qt 6.5.3）

边的图形化管理界面：查看节点健康状态与设备列表，并为设备显示/刷新配对码。

## 运行

```sh
# Qt 6.5.3 的 qml 运行时；QML 从本地文件加载时需要放开 XHR 网络访问
QML_XHR_ALLOW_FILE_READ=1 /opt/Qt/6.5.3/gcc_64/bin/qml tools/edge-manager/EdgeManager.qml

# 指定别的边 API（默认 http://127.0.0.1:8001）
QML_XHR_ALLOW_FILE_READ=1 qml tools/edge-manager/EdgeManager.qml -- http://192.168.77.2:8001
```

## 界面

- 顶部：边 ID、MQTT 连接状态、批次/设备/收包/拒收/磁盘余量/库类型，每 3 秒刷新
- 左侧：设备列表（在线状态、链路、模块号），点选设备
- 右侧：为该设备生成 6 位配对码，显示倒计时（默认 10 分钟），过期或已使用后可刷新

配对码在终端「设置 → 网络连接管理」的发现边面板里输入，由终端生成 CSR 后向边的
`POST /api/v1/pair/redeem` 兑换设备证书。

## 说明

- QML 通过 `XMLHttpRequest` 调边 API：`GET /api/v1/health`、`GET /api/v1/devices`、
  `POST /api/v1/devices/{id}/pair`。
- 无管理员 token 时（默认单机演示）`/pair` 直接可用；部署了 `EDGE_ADMIN_TOKEN`
  时需要额外在请求头带令牌（当前 UI 未做 token 输入，按需扩展）。
