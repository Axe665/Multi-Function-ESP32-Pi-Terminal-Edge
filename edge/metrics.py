"""指标登记表 —— 与终端仓的真实模块和字段对齐。

来源（终端仓 `pi_terminal/`）：
  - module-devkit/examples/{smart-planter,xiaotian-fence,blood-pressure}/manifest.json
  - pi_terminal/modules/example/manifest.json
  - pi_terminal/src/core/ModuleDataApi.cpp（字段白名单）
  - pi_terminal/src/security/UserDatabase.cpp（三张事实表）

数据表与字段都是终端真实存在的列名，不是蓝图里的占位：
  measurements : systolic / diastolic / pulse
  samples      : temperature_c / humidity_rh / light_lux / battery_v / battery_pct
  readings     : 模块自定义 metric + value + unit
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Module:
    module_id: int
    package_id: str
    name: str
    scene: str


# 终端仓里真实存在的六个 module_id（129/130/131 是测试模块，不进 deb，用来当无头机）
MODULES: dict[int, Module] = {
    m.module_id: m for m in [
        Module(80, "planter.environment", "智能盆栽 · 环境看板", "env"),
        Module(82, "xiaotian.fence", "啸天红外围界", "env"),
        Module(83, "health.pressure", "血压读数", "health"),
        Module(129, "test.environment", "环境监测", "env"),
        Module(130, "test.counter", "计数器", "energy"),
        Module(131, "test.camera", "相机", "env"),
    ]
}


@dataclass(frozen=True)
class Metric:
    key: str          # 终端表里的真实字段名
    label: str
    unit: str
    decimals: int
    module_id: int
    table: str        # samples / readings / measurements
    device_id: str


def _m(key, label, unit, decimals, module_id, table, device_id) -> Metric:
    return Metric(key, label, unit, decimals, module_id, table, device_id)


# 一台带屏 + 两台无头，与 v2.2 方案的三机布局一致。
# 带屏机跑 83 + 80（血压 + 环境），两台无头分别跑 129（环境）与 130（计数器）。
DEVICES: list[dict] = [
    {"device_id": "mt-3b-01", "name": "诊室屏 · Pi 3B", "scene": "health",
     "modules": [83, 80], "fw": "orpi 1.4.2", "headless": False},
    {"device_id": "mt-a64-02", "name": "温室无头 · Pine64", "scene": "env",
     "modules": [129], "fw": "orpi 1.4.2", "headless": True},
    {"device_id": "mt-rk64-03", "name": "配电无头 · Rock64", "scene": "energy",
     "modules": [130], "fw": "orpi 1.4.2", "headless": True},
]

METRICS: list[Metric] = [
    # 带屏机：83 血压（measurements）+ 80 盆栽环境（samples）
    _m("systolic", "收缩压", "mmHg", 0, 83, "measurements", "mt-3b-01"),
    _m("diastolic", "舒张压", "mmHg", 0, 83, "measurements", "mt-3b-01"),
    _m("pulse", "脉搏", "bpm", 0, 83, "measurements", "mt-3b-01"),
    _m("temperature_c", "温度", "°C", 1, 80, "samples", "mt-3b-01"),
    _m("humidity_rh", "湿度", "%", 1, 80, "samples", "mt-3b-01"),
    # 无头机 A：129 测试环境
    _m("temperature_c", "温度", "°C", 1, 129, "samples", "mt-a64-02"),
    _m("humidity_rh", "湿度", "%", 1, 129, "samples", "mt-a64-02"),
    _m("light_lux", "光照", "lx", 0, 129, "samples", "mt-a64-02"),
    # 无头机 B：130 计数器（readings 表，metric 由模块自定义）
    _m("counter_delta", "计数增量", "次", 0, 130, "readings", "mt-rk64-03"),
    _m("counter_rate", "计数速率", "次/min", 1, 130, "readings", "mt-rk64-03"),
]

BY_DEVICE: dict[str, list[Metric]] = {}
for _metric in METRICS:
    BY_DEVICE.setdefault(_metric.device_id, []).append(_metric)

BY_KEY: dict[tuple[str, str], Metric] = {(m.device_id, m.key): m for m in METRICS}


def for_device(device_id: str) -> list[Metric]:
    return BY_DEVICE.get(device_id, [])


def get(device_id: str, metric: str) -> Metric | None:
    return BY_KEY.get((device_id, metric))


def decimals(device_id: str, metric: str) -> int:
    m = get(device_id, metric)
    return m.decimals if m else 1


def unit(device_id: str, metric: str) -> str:
    m = get(device_id, metric)
    return m.unit if m else ""


def label(device_id: str, metric: str) -> str:
    m = get(device_id, metric)
    return m.label if m else metric


def module_of(device_id: str, metric: str) -> Module | None:
    m = get(device_id, metric)
    return MODULES.get(m.module_id) if m else None


def device(device_id: str) -> dict | None:
    return next((d for d in DEVICES if d["device_id"] == device_id), None)
