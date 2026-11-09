"""文本脱敏：建议文案进库前先过一遍。

方案 8.2 要求「建议文案不含姓名、地名、设备序列号；生成后跑正则 + 词典二次过滤」。
正则处理号码类，词典处理姓名/地名。命中次数进 counters，审计页可查。
"""
from __future__ import annotations

import re
from typing import Iterable

# 号码类：手机、证件、邮箱、设备序列号
PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"1[3-9]\d{9}"), "[手机号]", "phone"),
    (re.compile(r"\b\d{17}[\dXx]\b"), "[证件号]", "id_card"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "[邮箱]", "email"),
    (re.compile(r"\b(?:SN|SNR|序列号)[:：]?\s*[A-Z0-9][A-Z0-9-]{5,}\b"), "[设备号]", "serial"),
    (re.compile(r"\b(?:mt|orpi)-[a-z0-9-]{3,}\b", re.I), "[设备号]", "device_id"),
]

# 词典：姓氏 + 常见地名后缀。命中即替换，不做 NER。
SURNAMES = "赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜戚谢邹喻柏水窦章云苏潘葛奚范彭郎鲁韦昌马苗凤花方俞任袁柳鲍史唐费廉岑薛雷贺倪汤滕殷罗毕郝邬安常乐于时傅皮卞齐康伍余元卜顾孟平黄和穆萧尹"
HONORIFICS = ["先生", "女士", "老师", "阿姨", "叔叔", "大爷", "大妈", "医生", "护士"]
PLACES = ["北京市", "上海市", "广州市", "深圳市", "杭州市", "成都市", "武汉市", "西安市",
          "朝阳区", "海淀区", "浦东新区", "天河区", "西湖区", "高新区", "开发区"]


def _extra_terms() -> Iterable[str]:
    """部署方可以往 data/blocklist.txt 里加自己的词（一行一个）。"""
    from . import config
    path = config.DATA_DIR / "blocklist.txt"
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.startswith("#")]


def scrub(text: str) -> tuple[str, dict[str, int]]:
    """返回 (清洗后的文本, {规则: 命中次数})。没有命中就是原样返回。"""
    hits: dict[str, int] = {}
    out = text
    for pattern, replacement, tag in PATTERNS:
        out, n = pattern.subn(replacement, out)
        if n:
            hits[tag] = hits.get(tag, 0) + n

    # 姓氏 + 敬称：只处理「张先生」「李女士」这种明确指人的写法
    for h in HONORIFICS:
        pattern = re.compile(rf"[{SURNAMES}]{{1,2}}{h}")
        out, n = pattern.subn("[姓名]", out)
        if n:
            hits["name"] = hits.get("name", 0) + n

    for place in PLACES:
        if place in out:
            hits["place"] = hits.get("place", 0) + out.count(place)
            out = out.replace(place, "[地名]")

    for term in _extra_terms():
        if term in out:
            hits["blocklist"] = hits.get("blocklist", 0) + out.count(term)
            out = out.replace(term, "[已屏蔽]")

    return out, hits
