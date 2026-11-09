"""边 → 云的投递：手动触发和定时任务共用这一条路径。"""
from __future__ import annotations

import ssl

import httpx

from . import config, models, store


def send(payload: dict) -> dict:
    """返回 {ok, status, detail}。失败不抛异常，交给发件箱退避。"""
    if not config.CLOUD_URL:
        return {"ok": False, "status": "not_configured",
                "detail": "未配置 EDGE_CLOUD_URL，报表留在发件箱"}
    models.EdgeReport.model_validate(payload)  # 出站前用同一份契约再验一次

    headers = {"Authorization": f"Bearer {config.CLOUD_TOKEN}"} if config.CLOUD_TOKEN else {}
    # trust_env=False：边→云是内网调用，不能踩到宿主机上的 HTTP_PROXY
    client_kwargs: dict = {"timeout": 8, "trust_env": False}
    if config.CLOUD_CA and config.CLOUD_CERT and config.CLOUD_KEY:
        # httpx 0.28 的 cert=(cert,key) 在这个组合下不会真的发出客户端证书，
        # 直接构造 SSLContext 最稳（文档 §5.8 的 mTLS 就靠它）
        ctx = ssl.create_default_context(cafile=config.CLOUD_CA)
        ctx.load_cert_chain(config.CLOUD_CERT, config.CLOUD_KEY)
        client_kwargs["verify"] = ctx

    try:
        with httpx.Client(**client_kwargs) as c:
            r = c.post(f"{config.CLOUD_URL}/api/v1/ingest/edge-report",
                       json=payload, headers=headers)
    except (httpx.HTTPError, ValueError) as e:
        return {"ok": False, "status": "unreachable", "detail": str(e)[:200]}

    if r.status_code >= 400:
        return {"ok": False, "status": f"http_{r.status_code}", "detail": r.text[:200]}
    return {"ok": True, "status": "ok", "detail": r.text[:200],
            "bytes": len(r.content)}


def push_now() -> dict:
    """手动：生成一份新报表并入发件箱，然后尝试投递。"""
    from . import analysis
    payload = analysis.build_report()
    store.enqueue_report(payload["report_id"], payload)
    result = send(payload)
    if result["ok"]:
        store.mark_sent(payload["report_id"], None)
    else:
        store.schedule_retry(payload["report_id"], result["detail"])
    return {"report_id": payload["report_id"], "queued": not result["ok"], **result}


def drain(limit: int = 5) -> dict:
    """把到期的报表依次投出去；成功的不再重试。"""
    sent = 0
    failed = 0
    for entry in store.due_reports(limit):
        import json
        payload = json.loads(entry["payload"])
        result = send(payload)
        if result["ok"]:
            store.mark_sent(entry["report_id"], None)
            sent += 1
        else:
            store.schedule_retry(entry["report_id"], result["detail"])
            failed += 1
            if result["status"] in ("unreachable", "not_configured"):
                break  # 云不可达时不要空转剩下的队列
    return {"sent": sent, "failed": failed}
