"""指标登记表：单位、精度、归属设备与模块。前端标签也来自这里。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    unit: str
    device_id: str
    module_id: int
    decimals: int


METRICS: dict[str, Metric] = {
    m.key: m
    for m in [
        Metric("bp.systolic", "收缩压", "mmHg", "mt-3b-01", 83, 0),
        Metric("spo2", "血氧饱和度", "%", "mt-3b-01", 83, 1),
        Metric("weight", "体重", "kg", "mt-3b-01", 84, 1),
        Metric("env.temp", "室内温度", "°C", "mt-a64-02", 21, 1),
        Metric("env.humidity", "相对湿度", "%", "mt-a64-02", 21, 1),
        Metric("env.co2", "CO₂ 浓度", "ppm", "mt-a64-02", 22, 0),
        Metric("energy.load", "用电负荷", "kW", "mt-rk64-03", 31, 2),
        Metric("energy.pv", "光伏出力", "kW", "mt-rk64-03", 32, 2),
    ]
}


def for_device(device_id: str) -> list[Metric]:
    return [m for m in METRICS.values() if m.device_id == device_id]


def decimals(metric: str) -> int:
    m = METRICS.get(metric)
    return m.decimals if m else 1


def unit(metric: str) -> str:
    m = METRICS.get(metric)
    return m.unit if m else ""


def label(metric: str) -> str:
    m = METRICS.get(metric)
    return m.label if m else metric
