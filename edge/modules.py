"""终端模块的能力表 —— 只给演示数据生成器用。

真实部署里这些信息来自终端的 manifest 与 status 主题；
这里只是让「模拟的终端」知道每种模块能产出什么指标。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Capability:
    module_id: int
    package_id: str
    name: str
    scene: str
    metrics: tuple[tuple[str, str, str, str, int], ...] = field(default_factory=tuple)
    # (metric, label, unit, table, decimals)


CAPS: dict[int, Capability] = {c.module_id: c for c in [
    Capability(80, "planter.environment", "智能盆栽环境看板", "env", (
        ("temperature_c", "温度", "°C", "samples", 1),
        ("humidity_rh", "湿度", "%", "samples", 1),
        ("light_lux", "光照", "lx", "samples", 0),
        ("battery_v", "电池电压", "V", "samples", 2),
    )),
    Capability(82, "xiaotian.fence", "啸天红外围界", "env", (
        ("intrusion_count", "触发次数", "次", "readings", 0),
        ("battery_v", "电池电压", "V", "samples", 2),
    )),
    Capability(83, "health.pressure", "血压读数", "health", (
        ("systolic", "收缩压", "mmHg", "measurements", 0),
        ("diastolic", "舒张压", "mmHg", "measurements", 0),
        ("pulse", "脉搏", "bpm", "measurements", 0),
    )),
    Capability(129, "test.environment", "环境监测", "env", (
        ("temperature_c", "温度", "°C", "samples", 1),
        ("humidity_rh", "湿度", "%", "samples", 1),
        ("light_lux", "光照", "lx", "samples", 0),
    )),
    Capability(130, "test.counter", "计数器", "energy", (
        ("counter_delta", "计数增量", "次", "readings", 0),
        ("counter_rate", "计数速率", "次/min", "readings", 1),
    )),
    Capability(131, "test.camera", "相机", "env", (
        ("frames", "抓拍帧数", "帧", "readings", 0),
        ("battery_pct", "电量", "%", "samples", 0),
    )),
]}

# 演示里可能出现的板子：型号 + 是否带屏。模块不预先绑定。
BOARDS = [
    {"device_id": "mt-3b-01", "name": "诊室屏 Pi 3B", "headless": False, "fw": "orpi 1.4.2"},
    {"device_id": "mt-a64-02", "name": "温室无头 Pine64", "headless": True, "fw": "orpi 1.4.2"},
    {"device_id": "mt-rk64-03", "name": "配电无头 Rock64", "headless": True, "fw": "orpi 1.4.2"},
    {"device_id": "mt-pi4-04", "name": "备机 Pi 4", "headless": False, "fw": "orpi 1.5.0"},
]

SCENES = ["health", "env", "energy", "mixed"]


def metrics_for(module_ids: list[int]) -> list[dict]:
    """把一组模块展开成指标列表（同名字段只登记一次，保留先出现的模块）。"""
    seen: dict[str, dict] = {}
    for mid in module_ids:
        cap = CAPS.get(mid)
        if not cap:
            continue
        for key, label, unit, table, decimals in cap.metrics:
            seen.setdefault(key, {
                "metric": key, "label": label, "unit": unit,
                "table": table, "decimals": decimals,
                "module_id": mid, "package_id": cap.package_id,
            })
    return list(seen.values())
