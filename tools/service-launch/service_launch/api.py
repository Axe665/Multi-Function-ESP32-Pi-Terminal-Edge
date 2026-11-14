"""控制台的 HTTP 层：状态、动作、日志，外加把网页端的 m3.css 和图标字体借过来。

只绑 127.0.0.1。改状态的请求要带启动时生成的令牌，并且只认本机 Origin，
免得浏览器里别的标签页顺手把服务停了。
"""
from __future__ import annotations

import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from . import config, stack

STATIC = Path(__file__).parent / "static"
WEB = config.ROOT / "web"
TOKEN = secrets.token_urlsafe(18)

app = FastAPI(title="service launch", docs_url=None, openapi_url=None, redoc_url=None)


def _file(path: Path, media: str) -> FileResponse:
    if not path.exists():
        raise HTTPException(404, f"缺文件：{path.name}")
    return FileResponse(path, media_type=media)


def _mode(raw: str, cfg: config.Config) -> str:
    return raw if raw in ("docker", "native") else stack.detect_mode(cfg)


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(html.replace("__TOKEN__", TOKEN))


@app.get("/console.css")
def console_css() -> FileResponse:
    return _file(STATIC / "console.css", "text/css")


@app.get("/app.js")
def console_js() -> FileResponse:
    return _file(STATIC / "app.js", "text/javascript")


@app.get("/m3.css")
def m3_css() -> FileResponse:
    # 直接用网页端那一份，两处视觉不会漂
    return _file(WEB / "src/styles/m3.css", "text/css")


@app.get("/fonts/material-symbols.woff2")
def icons() -> FileResponse:
    return _file(WEB / "public/fonts/material-symbols.woff2", "font/woff2")


@app.get("/api/state")
def state(mode: str = "") -> JSONResponse:
    cfg = config.load()
    picked = _mode(mode, cfg)
    data = stack.snapshot(cfg, picked)
    data.update(
        title=cfg.title,
        web_url=cfg.web_url,
        auto=mode not in ("docker", "native"),
    )
    return JSONResponse(data, headers={"cache-control": "no-store"})


@app.get("/api/logs")
def logs(service: str, mode: str = "", lines: int = 200) -> JSONResponse:
    cfg = config.load()
    text = stack.logs(cfg, _mode(mode, cfg), service, max(20, min(lines, 1000)))
    return JSONResponse({"text": text}, headers={"cache-control": "no-store"})


def _guard(request: Request) -> None:
    if request.headers.get("x-console-token") != TOKEN:
        raise HTTPException(403, "令牌不对，刷新页面")
    origin = request.headers.get("origin")
    if origin:
        port = config.load().port
        if origin not in (f"http://127.0.0.1:{port}", f"http://localhost:{port}"):
            raise HTTPException(403, "只接受本机控制台发来的请求")


@app.post("/api/action")
async def action(request: Request) -> JSONResponse:
    _guard(request)
    body = await request.json()
    cfg = config.load()
    name = str(body.get("action", ""))
    service = str(body.get("service", ""))
    ok, message = stack.act(cfg, _mode(str(body.get("mode", "")), cfg), name, service)
    return JSONResponse(
        {"ok": ok, "message": message}, status_code=200 if ok else 409
    )
