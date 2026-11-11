"""线上契约的 Pydantic 模型（telemetry.v1 / edge-report.v1）。

两份契约都禁止额外字段：出现 userId、原始值序列这类字段直接 422，
即使以后有人往载荷里多塞字段也不会被静默接受。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

RISK = Literal["info", "watch", "alert"]

# 出端载荷里出现这些键即视为事故（8.1 硬规则）。
RAW_KEYS = {"user_id", "userId", "user_name", "userName", "subject",
            "values", "raw", "raw_samples", "samples", "records"}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class Window(Strict):
    from_: int = Field(alias="from")
    to: int
    step_ms: int = 300_000


class Aggregate(Strict):
    metric: str = Field(min_length=1, max_length=64)
    module_id: int = Field(ge=0)
    n_subjects: int = Field(ge=1)
    n_samples: int = Field(ge=1)
    mean: float
    slope: float = 0.0
    z: float = 0.0
    k: int = Field(ge=1)
    # 以下都可选：端不报就由边按 metric 名自己兜底。
    # 端报了，边就能在换模块时自动登记新指标（catalog）。
    label: str = Field(default="", max_length=32)
    unit: str = Field(default="", max_length=16)
    table: Literal["samples", "readings", "measurements"] = "samples"
    package_id: str = Field(default="", max_length=64)
    decimals: int = Field(default=1, ge=0, le=4)

    @model_validator(mode="after")
    def _k_le_subjects(self):
        if self.k > self.n_subjects:
            raise ValueError("k 不能大于 n_subjects")
        return self


class Advice(Strict):
    text: str = Field(min_length=1, max_length=160)
    risk: RISK = "info"
    confidence: float = Field(ge=0, le=1, default=0.5)
    source: Literal["local", "cloud", "api"] = "local"
    # advice 主题单独发时可以带产生时间；telemetry 里的 advice 不带
    created_at: int | None = None


class Privacy(Strict):
    k: int = Field(ge=1)
    pseudonym: str = "hmac16"
    raw: bool = False
    suppressed: int = Field(ge=0, default=0)

    @model_validator(mode="after")
    def _no_raw(self):
        if self.raw:
            raise ValueError("raw=true 的载荷不允许进入边")
        return self


class Telemetry(Strict):
    """orpi.telemetry.v1 —— 端 → 边。"""
    schema_: Literal["orpi.telemetry.v1"] = Field(alias="schema")
    device_id: str = Field(min_length=1, max_length=64)
    edge_id: str = Field(min_length=1, max_length=64)
    sent_at: int
    window: Window
    aggregates: list[Aggregate] = Field(default_factory=list, max_length=64)
    advice: list[Advice] = Field(default_factory=list, max_length=16)
    privacy: Privacy

    @model_validator(mode="after")
    def _window_order(self):
        if self.window.to <= self.window.from_:
            raise ValueError("window.to 必须大于 window.from")
        return self


# ---------------------------------------------------------------- 边 → 云

class ReportDevice(Strict):
    device_id: str
    scene: str
    modules: list[int] = Field(default_factory=list)
    last_seen: int | None = None
    online: bool = False


class DailyAggregate(Strict):
    device_id: str
    day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    metric: str
    n_subjects: int
    n_samples: int
    mean: float
    slope: float
    z: float
    k: int
    module_id: int = 0
    label: str = ""
    unit: str = ""
    table: str = "samples"


class ReportAdvice(Strict):
    device_id: str
    text: str
    risk: RISK
    confidence: float
    source: str
    created_at: int


class WordFreq(Strict):
    day: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    word: str
    count: int


class ReportPrivacy(Strict):
    k_min: int = 5
    suppressed_buckets: int = 0
    raw_rejected: int = 0
    subjects_total: int = 0
    # 关掉个性化时置 false（文档 §8.5）；v1 内加可选字段，默认 true 保持兼容
    personalization: bool = True
    # 关掉群体分析时置 false：只上报在线/健康计数，分析数据为空
    group_analysis: bool = True


class Period(Strict):
    from_: int = Field(alias="from")
    to: int


class EdgeReport(Strict):
    """orpi.edge.report.v1 —— 边 → 云。只含日聚合与建议文本。"""
    schema_: Literal["orpi.edge.report.v1"] = Field(alias="schema")
    report_id: str = Field(min_length=8, max_length=64)
    edge_id: str
    edge_name: str = ""
    sent_at: int
    period: Period
    devices: list[ReportDevice] = Field(default_factory=list, max_length=64)
    telemetry_daily: list[DailyAggregate] = Field(default_factory=list, max_length=4096)
    advice: list[ReportAdvice] = Field(default_factory=list, max_length=256)
    word_freq: list[WordFreq] = Field(default_factory=list, max_length=512)
    privacy: ReportPrivacy
