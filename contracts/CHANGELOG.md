# 契约变更记录

语义化版本：v1 内只能加可选字段（带默认值）；删改字段必须升 v2。

| 契约 | 版本 | Owner | 消费方 |
|---|---|---|---|
| `wire/telemetry.v1.json` | 1.0.0 | 端仓 | 边（vendor 到 `contracts/vendor/terminal/`） |
| `wire/edge-report.v1.json` | 1.0.0 | 边仓（本仓） | 云（vendor 到 `contracts/vendor/edge/`） |

## v1.0.0 — 2026-11-09

首版。

- `telemetry.v1`：`aggregates[].k` 必填；`privacy.raw` 只能是 `false`。
- `edge-report.v1`：`telemetry_daily[].k` 的下界是 5，k<5 的行不允许出现在报表里。
- 两份契约都 `additionalProperties: false`：多塞一个字段就是违约，
  不是「忽略未知字段」。这样 `user_id`、`values` 这类字段会在边界上直接炸出来。

## 已知的消费方假设

- 边把 `telemetry.v1` 的示例当单测夹具（`tests/test_contracts.py`）。
- 云把 `edge-report.v1.example.json` 当摄取单测夹具。
- 改字段时两边同时改；消费方不修改 vendor 副本。
