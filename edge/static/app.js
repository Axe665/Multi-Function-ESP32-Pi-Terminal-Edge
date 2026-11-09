/* 边节点前端：原生 ES 模块，无构建步骤，离线可用。 */

import { line, heatmap, wordcloud, barList, fmtNum, fmtTime } from "./charts.js";
import { createFlow } from "./flow.js";

const main = document.getElementById("main");
// 外壳换过一次：这些节点在新壳里可能不存在，全部做空值保护
const $ = (id) => document.getElementById(id);
let settingsCache = null;

/* ---------------------------------------------------------------- 工具 */

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, opts = {}) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = JSON.stringify((await r.json()).detail).slice(0, 200); } catch { /* 非 JSON 错误体 */ }
    throw new Error(`${r.status} ${detail}`);
  }
  return r.json();
}

function toast(msg) {
  document.querySelector(".toast")?.remove();
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  document.body.append(t);
  setTimeout(() => t.remove(), 2600);
}

function panel(title, meta, body) {
  return `<section class="panel">
    <div class="panel-head"><h2>${esc(title)}</h2>${meta ? `<span class="meta">${meta}</span>` : ""}</div>
    ${body}
  </section>`;
}

function errBox(msg, retry) {
  return `<div class="error-box"><span>${esc(msg)}</span>
    <button class="btn btn-sm" data-retry>重试</button></div>`;
}

function skeleton(lines = 3) {
  return `<div class="list">${Array.from({ length: lines }, (_, i) =>
    `<div class="list-row"><div class="grow"><span class="skeleton" style="width:${40 + i * 12}%"></span></div></div>`).join("")}</div>`;
}

const riskLabel = { info: "提示", watch: "关注", alert: "告警" };
const META_K = () => settingsCache?.k_min ?? 5;
const RISK_ORDER = { alert: 0, watch: 1, info: 2 };

/* ---------------------------------------------------------------- 总览 */

async function viewOverview() {
  main.innerHTML = `<div class="title-row"><div><h1>总览</h1><p class="sub">正在读取边节点状态…</p></div></div>
    <div class="kpis">${Array.from({ length: 4 }, () => `<div class="kpi"><div class="kpi-label">读取中</div><div class="kpi-value">—</div></div>`).join("")}</div>`;

  let o;
  try {
    o = await api("/api/v1/overview");
  } catch (e) {
    main.innerHTML = `<div class="title-row"><div><h1>总览</h1></div></div><div class="row">${errBox(`读不到边节点状态：${e.message}`)}</div>`;
    return;
  }

  const navOutbox = $("nav-outbox");
  if (navOutbox) {
    navOutbox.hidden = !o.pending_reports;
    navOutbox.textContent = o.pending_reports || "";
  }
  const scope = $("scope");
  if (scope) scope.textContent = o.edge_name;
  renderSideFoot(o);

  const findings = o.findings.length ? o.findings.map((f) => `
    <div class="list-row">
      <div class="grow">
        <div class="finding-metric">${esc(f.label || f.metric)}</div>
        <div class="finding-text">${esc(f.text)}</div>
        <div class="finding-delta">较基线
          <b class="${f.delta >= 0 ? "up" : "down"}">${f.delta >= 0 ? "+" : "−"}${fmtNum(Math.abs(f.delta), 1)}</b>
        </div>
      </div>
    </div>`).join("") : `<div class="empty">最近 24 h 三条链路都在基线附近，没有需要单独说明的变化。</div>`;

  const advice = await api("/api/v1/advice?limit=5").catch(() => []);
  const adviceRows = advice.length ? advice.map((a) => `
    <div class="list-row">
      <span class="pill pill-${a.risk}">${riskLabel[a.risk]}</span>
      <div class="grow">
        <div class="row-text" title="${esc(a.text)}">${esc(a.text)}</div>
        <div class="row-sub">${esc(a.device_id)} · ${a.source === "local" ? "本地模型" : esc(a.source)}</div>
      </div>
      <div class="row-time">${fmtTime(a.created_at)}</div>
    </div>`).join("") : `<div class="empty">这个窗口还没有生成建议。</div>`;

  main.innerHTML = `
    <div class="title-row">
      <div>
        <h1>总览</h1>
        <p class="sub">${esc(o.edge_name)} · ${o.devices_total} 台终端 · 5 分钟聚合窗口 · k≥5 才入库</p>
      </div>
      <div class="title-actions">
        <span class="stamp">更新于 ${fmtTime(o.generated_at)}</span>
        <button class="btn" id="refresh">刷新</button>
        <button class="btn btn-primary" id="push">立即上云</button>
      </div>
    </div>

    <div class="row">
      <section class="panel band">
        <div class="panel-head">
          <h2>数据流</h2>
          <span class="meta">三台终端 → 聚合环 → 云端</span>
        </div>
        <div class="band-labels">
          <span>端 · ${o.devices_total} 台终端</span>
          <span>边 · k≥${META_K()} 聚合环</span>
          <span>云 · ${o.pending_reports} 份待上传</span>
        </div>
        <div class="band-canvas"><canvas id="flow" aria-label="数据流示意：粒子从三台终端汇入聚合环"></canvas></div>
        <p class="hint" style="margin:10px 0 0">环前熄灭的粒子是被 k 抑制的桶——它们从未离开过终端。</p>
      </section>
    </div>

    <div class="kpis">
      <div class="kpi">
        <div class="kpi-label">在线终端</div>
        <div class="kpi-value">${o.devices_online}<small>/ ${o.devices_total}</small></div>
        <div class="kpi-note">最近 ${Math.round(3 * 5)} 分钟内有批次</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">24 h 批次</div>
        <div class="kpi-value">${fmtNum(o.batches_24h)}</div>
        <div class="kpi-note">按 (device, batch_id) 去重后</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">24 h 建议</div>
        <div class="kpi-value">${fmtNum(o.advice_24h)}</div>
        <div class="kpi-note">其中告警 ${fmtNum(o.alerts_24h)} 条</div>
      </div>
      <div class="kpi">
        <div class="kpi-label">被抑制的桶</div>
        <div class="kpi-value">${fmtNum(o.suppressed_buckets)}</div>
        <div class="kpi-note">k＜${settingsCache?.k_min ?? 5}，只在端内使用</div>
      </div>
    </div>

    <div class="row">
      <div class="panel" style="padding-bottom:16px">
        <div class="panel-head">
          <h2>链路</h2>
          <span class="meta">最近 24 个 5 分钟窗口 · 实心格为已收到</span>
        </div>
        <div class="lanes" style="border:0;background:transparent">
          ${o.lanes.map((l) => `
            <div class="lane">
              <div class="lane-top">
                <span class="lane-name">${esc(l.name)}</span>
                <span class="lane-scene">${esc(l.scene)}</span>
                <span class="lane-id">${esc(l.device_id)}</span>
              </div>
              <div class="ticks" role="img" aria-label="${esc(l.device_id)} 最近 24 个窗口的到达情况">
                ${l.ticks.map((t, i) => `<span class="tick ${t ? "got" : "miss"} ${i === l.ticks.length - 1 ? "now" : ""}"></span>`).join("")}
              </div>
              <div class="ticks-legend"><span>−2 h</span><span>现在</span></div>
              <div class="lane-metrics">
                ${l.metrics.map((m) => `<span class="lane-metric">${esc(m.label)}
                  <b>${fmtNum(m.mean, m.decimals)}</b><span>${esc(m.unit)}</span></span>`).join("")}
              </div>
              <div class="lane-foot">
                <span class="lane-k">最小 k <b>${l.k || "—"}</b></span>
                <span class="lane-fill">${l.fill}% 到达</span>
              </div>
            </div>`).join("")}
        </div>
      </div>
    </div>

    <div class="row split" style="align-items:start">
      <section class="panel fill">
        <div class="panel-head"><h2>24 h 里最值得说的三件事</h2><span class="meta">相对 7 天同段基线</span></div>
        <div class="list findings">${findings}</div>
        <p class="hint grow-block" style="margin:16px 0 0">比较口径：每个指标取最近 24 h 均值，对照同设备前 7 天同一时段的均值。</p>
      </section>
      ${panel("建议流", `最近 5 条 · 共 ${o.advice_24h}`, `<div class="list">${adviceRows}</div>`)}
    </div>`;

  const flow = createFlow(document.getElementById("flow"));
  flow.setData({
    batches: o.batches_24h, suppressed: o.suppressed_buckets, alerts: o.alerts_24h,
    online: o.lanes.map((l) => l.online),
  });

  $("refresh").onclick = () => route(true);
  $("push").onclick = (e) => pushCloud(e.currentTarget);
}

function renderSideFoot(o) {
  const foot = $("side-foot");
  if (!foot) return;   // 新外壳把侧栏换成顶栏了
  foot.innerHTML = `
    <dl>
      <dt>边 ID</dt><dd>${esc(o.edge_id)}</dd>
      <dt>云端</dt><dd>${o.cloud_ok ? "已配置" : "未配置"}</dd>
      <dt>待上云</dt><dd>${o.pending_reports}</dd>
    </dl>`;
}

async function pushCloud(btn) {
  btn.disabled = true;
  const old = btn.textContent;
  btn.textContent = "正在打包…";
  try {
    const r = await api("/api/v1/report/cloud", { method: "POST" });
    toast(r.cloud === "ok" ? `已上报 ${r.report_id}` : `已入发件箱（${r.cloud}）`);
  } catch (e) {
    toast(`上报失败：${e.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = old;
    route(true);
  }
}

/* ---------------------------------------------------------------- 设备列表 */

async function viewDevices() {
  main.innerHTML = `<div class="title-row"><div><h1>设备</h1><p class="sub">三台终端，一台带屏、两台无头。</p></div></div>
    <div class="row"><section class="panel">${skeleton(3)}</section></div>`;

  let devs;
  let batches = [];
  try {
    devs = await api("/api/v1/devices");
    batches = await api("/api/v1/batches?limit=8").catch(() => []);
  } catch (e) {
    main.querySelector(".panel").innerHTML = errBox(`读不到设备列表：${e.message}`);
    return;
  }

  const rows = devs.map((d) => `
    <tr>
      <td><a href="#/devices/${esc(d.device_id)}"><strong>${esc(d.name)}</strong></a>
        <div class="mono">${esc(d.device_id)}</div></td>
      <td>${esc(d.scene)}</td>
      <td>${d.online ? `<span class="pill pill-ok">在线</span>` : `<span class="pill pill-info">离线</span>`}</td>
      <td class="num">${d.last_seen ? fmtTime(d.last_seen) : "—"}</td>
      <td>${d.metrics.map((m) => `<span class="muted">${esc(m.label)}</span>
        <span style="font-variant-numeric:tabular-nums">${fmtNum(m.mean, m.decimals)}</span>
        <span class="faint">${esc(m.unit)}</span>`).join("<br>")}</td>
      <td class="num"><a class="btn btn-sm" href="#/devices/${esc(d.device_id)}">查看</a></td>
    </tr>`).join("");

  main.innerHTML = `
    <div class="title-row">
      <div><h1>设备</h1><p class="sub">三台终端：一台带屏跑完整 QML，两台无头只上报数据。</p></div>
      <div class="title-actions"><span class="stamp">${devs.filter((d) => d.online).length} / ${devs.length} 在线</span></div>
    </div>
    <div class="row split" style="align-items:start">
      <section class="panel fill">
        <div class="panel-head"><h2>已接入</h2><span class="meta">${devs.length} 台</span></div>
        <table class="table responsive">
          <thead><tr><th>设备</th><th>场景</th><th>状态</th><th class="num">最近上报</th><th>最新聚合</th><th></th></tr></thead>
          <tbody>${rows}</tbody>
        </table>
        <p class="hint grow-block" style="margin:16px 0 0">
          ${devs.filter((d) => d.online).length} 台在线，最近一次上报
          ${devs.map((d) => d.last_seen).filter(Boolean).sort((a, b) => b - a)[0] ? fmtTime(Math.max(...devs.map((d) => d.last_seen || 0)), true) : "—"}。
          边只保留聚合，不接收逐条原始记录。</p>
      </section>

      <section class="panel">
        <div class="panel-head"><h2>模块</h2><span class="meta">端侧上报</span></div>
        <div class="list">
          ${devs.flatMap((d) => (d.module_list || []).map((m) => `<div class="list-row">
            <div class="grow"><div class="row-text">${esc(m.package_id || "未知模块")}</div>
              <div class="row-sub">${esc(d.device_id)}</div></div>
            <span class="mono">${m.module_id}</span>
          </div>`)).join("") || `<div class="empty">还没有设备上报模块清单。</div>`}
        </div>
        <p class="hint" style="margin:14px 0 0">
          模块清单来自终端的 status 主题；新模块第一次上报时自动登记，不需要改边。</p>
        <a class="btn btn-sm" href="#/access" style="margin-top:16px">去接入页配对</a>
      </section>
    </div>

    <div class="row">
      <section class="panel">
        <div class="panel-head"><h2>最近批次</h2>
          <span class="meta">聚合窗口 · 不含逐条明细</span></div>
        <table class="table responsive">
          <thead><tr><th>设备</th><th>窗口</th><th class="num">指标</th><th class="num">最小 k</th>
            <th class="num">建议</th><th class="num">收到</th></tr></thead>
          <tbody>${batches.map((b) => `<tr>
            <td class="mono">${esc(b.device_id)}</td>
            <td>${fmtTime(b.ts_from)} – ${fmtTime(b.ts_to)}</td>
            <td class="num">${b.metrics}</td>
            <td class="num">${b.k_min}</td>
            <td class="num">${b.advice || "—"}</td>
            <td class="num">${fmtTime(b.received_at)}</td>
          </tr>`).join("") || `<tr><td colspan="6" class="dash">还没有收到批次。</td></tr>`}</tbody>
        </table>
      </section>
    </div>`;
}

/* ---------------------------------------------------------------- 设备详情 */

async function viewDevice(id) {
  main.innerHTML = `<div class="title-row"><div><h1>设备</h1><p class="sub">读取中…</p></div></div>`;

  let d;
  try {
    d = await api(`/api/v1/devices/${encodeURIComponent(id)}`);
  } catch (e) {
    main.innerHTML = `<div class="title-row"><div><h1>设备</h1></div></div><div class="row">${errBox(`读不到设备：${e.message}`)}</div>`;
    return;
  }

  const dev = d.device;
  let current = d.metrics[0]?.key;

  main.innerHTML = `
    <div class="title-row">
      <div>
        <p class="faint" style="margin:0 0 6px"><a href="#/devices">← 设备</a></p>
        <h1>${esc(dev.name)}</h1>
        <p class="sub"><span class="mono">${esc(dev.device_id)}</span> · ${esc(dev.scene)} · ${esc(dev.fw)}
          ${dev.online ? `· <span class="pill pill-ok">在线</span>` : `· <span class="pill pill-info">离线</span>`}</p>
        <p class="sub" style="margin-top:4px">模块：
          ${(d.modules || []).map((m) => `<span class="mono">${m.module_id}</span> ${esc(m.package_id)}
            <span class="faint">${esc(m.name)}</span>`).join(" · ")}</p>
      </div>
      <div class="title-actions">
        <button class="btn" id="report-now">让终端立即上报</button>
      </div>
    </div>

    <div class="row">
      <section class="panel">
        <div class="panel-head">
          <h2 id="trend-title">趋势</h2>
          <div class="seg" id="metric-tabs" role="group" aria-label="切换指标">
            ${d.metrics.map((m, i) => `<button data-metric="${esc(m.key)}" aria-pressed="${i === 0}">${esc(m.label)}</button>`).join("")}
          </div>
        </div>
        <div id="chart"></div>
        <div class="legend" style="margin-top:10px">
          <span><i style="background:var(--accent);width:14px;height:2px;border-radius:1px"></i>15 分钟聚合均值</span>
          <span><i style="background:var(--negative);border-radius:50%;width:6px;height:6px"></i>|z| ≥ 2.5</span>
          <span>虚线为 7 天同段基线</span>
        </div>
      </section>
    </div>

    <div class="row split">
      <section class="panel">
        <div class="panel-head"><h2>最近批次</h2><span class="meta">只存聚合，不存逐条原始记录</span></div>
        <table class="table responsive">
          <thead><tr><th>窗口</th><th>批次</th><th class="num">指标</th><th class="num">k</th><th class="num">建议</th><th class="num">收到</th></tr></thead>
          <tbody>
            ${d.batches.map((b) => `<tr>
              <td>${fmtTime(b.ts_from)}</td>
              <td class="mono">${esc(b.batch_id.slice(0, 8))}…</td>
              <td class="num">${b.metrics}</td>
              <td class="num">${b.k_min}</td>
              <td class="num">${b.advice}</td>
              <td class="num muted">${fmtTime(b.received_at)}</td>
            </tr>`).join("") || `<tr><td colspan="6" class="dash">还没有批次。</td></tr>`}
          </tbody>
        </table>
      </section>
      ${panel("这台设备最近的建议", `${d.advice.length} 条`, `<div class="list">
        ${d.advice.map((a) => `<div class="list-row">
          <span class="pill pill-${a.risk}">${riskLabel[a.risk]}</span>
          <div class="grow"><div class="row-text">${esc(a.text)}</div>
          <div class="row-sub">置信度 ${a.confidence.toFixed(2)} · ${esc(a.source)}</div></div>
          <div class="row-time">${fmtTime(a.created_at)}</div>
        </div>`).join("") || `<div class="empty">这台设备最近没有生成建议。</div>`}
      </div>`)}
    </div>

    <div class="row split">
      ${panel("这台设备的一句话结论", "近 24 h", d.finding
        ? `<p style="margin:0;font-size:15px;line-height:1.6">${esc(d.finding.text)}</p>
           <p class="hint" style="margin:10px 0 0">指标 ${esc(d.finding.metric)} · 变化 ${d.finding.delta >= 0 ? "+" : "−"}${fmtNum(Math.abs(d.finding.delta), 1)}</p>`
        : `<div class="empty">这个窗口没有足够数据做对比。</div>`)}
      ${panel("指标与时序", "口径", `<dl class="list" style="margin:0;font-size:13px">
        ${d.metrics.map((m) => `<div class="list-row"><div class="grow">${esc(m.label)}</div>
          <span class="mono">${esc(m.key)}</span><span class="faint">module ${m.module_id}</span></div>`).join("")}
      </dl>`)}
    </div>`;

  const chartHost = document.getElementById("chart");
  const title = document.getElementById("trend-title");

  async function drawTrend(metric) {
    const m = d.metrics.find((x) => x.key === metric);
    title.textContent = `${m.label}（${m.unit}）· 24 h`;
    chartHost.innerHTML = `<div class="empty" style="height:120px">读取中…</div>`;
    try {
      const t = await api(`/api/v1/devices/${encodeURIComponent(id)}/series?metric=${encodeURIComponent(metric)}&hours=24`);
      line(chartHost, {
        points: t.points, unit: t.unit, decimals: t.decimals, baseline: t.baseline,
        anomalies: t.anomalies, label: `${m.label} 最近 24 小时趋势`,
      });
    } catch (e) {
      chartHost.innerHTML = errBox(`读不到趋势：${e.message}`);
    }
  }

  document.getElementById("metric-tabs").addEventListener("click", (ev) => {
    const b = ev.target.closest("button[data-metric]");
    if (!b) return;
    current = b.dataset.metric;
    document.querySelectorAll("#metric-tabs button").forEach((x) =>
      x.setAttribute("aria-pressed", String(x === b)));
    drawTrend(current);
  });

  document.getElementById("report-now").onclick = async (ev) => {
    ev.currentTarget.disabled = true;
    try {
      await api(`/api/v1/devices/${encodeURIComponent(id)}/cmd`, {
        method: "POST", body: JSON.stringify({ cmd: "report_now" }),
      });
      toast("已触发一次上报");
      setTimeout(() => route(true), 300);
    } catch (e) {
      toast(`指令失败：${e.message}`);
      ev.currentTarget.disabled = false;
    }
  };

  drawTrend(current);
}

/* ---------------------------------------------------------------- 分析 */

let analysisState = { device: null, metric: null };

async function viewAnalysis() {
  main.innerHTML = `<div class="title-row"><div><h1>分析</h1><p class="sub">读取中…</p></div></div>`;

  let devs;
  let batches = [];
  try {
    devs = await api("/api/v1/devices");
    batches = await api("/api/v1/batches?limit=8").catch(() => []);
  } catch (e) {
    main.innerHTML = `<div class="title-row"><div><h1>分析</h1></div></div><div class="row">${errBox(`读不到设备：${e.message}`)}</div>`;
    return;
  }

  if (!analysisState.device) analysisState.device = devs[0].device_id;
  const dev = devs.find((d) => d.device_id === analysisState.device) || devs[0];
  const metricKeys = dev.metrics.map((m) => m.metric);
  if (!analysisState.metric || !metricKeys.includes(analysisState.metric)) {
    analysisState.metric = metricKeys[0];
  }

  main.innerHTML = `
    <div class="title-row">
      <div><h1>分析</h1>
        <p class="sub">24 h × 7 天的时段矩阵、建议词云和异常窗口。全部数字来自聚合表重算。</p></div>
      <div class="title-actions">
        <select class="control" id="sel-device" aria-label="设备">
          ${devs.map((d) => `<option value="${esc(d.device_id)}" ${d.device_id === dev.device_id ? "selected" : ""}>${esc(d.name)}</option>`).join("")}
        </select>
        <select class="control" id="sel-metric" aria-label="指标">
          ${dev.metrics.map((m) => `<option value="${esc(m.metric)}" ${m.metric === analysisState.metric ? "selected" : ""}>${esc(m.label)}</option>`).join("")}
        </select>
      </div>
    </div>

    <div class="row">
      <section class="panel">
        <div class="panel-head"><h2>时段热力图</h2><span class="meta" id="heat-meta"></span></div>
        <div id="heat"></div>
      </section>
    </div>

    <div class="row duo" style="align-items:stretch">
      <section class="panel">
        <div class="panel-head"><h2>词云</h2><span class="meta">最近 7 天建议文本 · 词典分词</span></div>
        <div id="cloud"></div>
        <div id="cloud-top" style="margin-top:16px"></div>
      </section>
      <section class="panel">
        <div class="panel-head"><h2>异常窗口</h2><span class="meta">|z| ≥ 2.5 · 最近 6 条</span></div>
        <div id="anomalies"></div>
      </section>
    </div>`;

  const heatHost = document.getElementById("heat");
  const cloudHost = document.getElementById("cloud");
  const anomHost = document.getElementById("anomalies");

  async function drawHeat() {
    const m = dev.metrics.find((x) => x.metric === analysisState.metric);
    document.getElementById("heat-meta").textContent =
      `${m.label}（${m.unit}） · 色深 = 该时段均值`;
    heatHost.innerHTML = `<div class="empty">读取中…</div>`;
    try {
      const h = await api(`/api/v1/heatmap?device=${encodeURIComponent(analysisState.device)}&metric=${encodeURIComponent(analysisState.metric)}&days=7`);
      heatmap(heatHost, h.cells, { decimals: m.decimals, unit: m.unit });
    } catch (e) {
      heatHost.innerHTML = errBox(`读不到热力图：${e.message}`);
    }
  }

  async function drawWords() {
    try {
      const w = await api("/api/v1/wordcloud?days=7");
      wordcloud(cloudHost, w.words);
      const total = w.words.reduce((n, x) => n + x.count, 0) || 1;
      document.getElementById("cloud-top").innerHTML = `<table class="table">
        <thead><tr><th>词</th><th class="num">出现</th><th class="num">占比</th></tr></thead>
        <tbody>${w.words.slice(0, 6).map((x) => `<tr>
          <td>${esc(x.word)}</td>
          <td class="num">${fmtNum(x.count)}</td>
          <td class="num muted">${((x.count / total) * 100).toFixed(1)}%</td>
        </tr>`).join("")}</tbody>
      </table>`;
    } catch (e) {
      cloudHost.innerHTML = errBox(`读不到词频：${e.message}`);
    }
  }

  async function drawAnomalies() {
    try {
      const rows = await api("/api/v1/anomalies?days=7");
      const picked = rows.filter((r) => r.device_id === analysisState.device).slice(0, 6);
      if (!picked.length) {
        anomHost.innerHTML = `<div class="empty">这台设备最近 7 天没有超过 2.5σ 的窗口。</div>`;
        return;
      }
      anomHost.innerHTML = `<div class="list">${picked.map((a) => `
        <div class="list-row">
          <div class="grow">
            <div class="row-text">${esc(a.label)}</div>
            <div class="row-sub">z = ${a.z.toFixed(2)} · 均值 ${fmtNum(a.mean, 1)}</div>
          </div>
          <div class="row-time">${fmtTime(a.ts_from, true)}</div>
        </div>`).join("")}</div>`;
    } catch (e) {
      anomHost.innerHTML = errBox(`读不到异常：${e.message}`);
    }
  }

  document.getElementById("sel-device").onchange = (ev) => {
    analysisState.device = ev.target.value;
    analysisState.metric = null;
    route(true);
  };
  document.getElementById("sel-metric").onchange = (ev) => {
    analysisState.metric = ev.target.value;
    drawHeat();
  };

  drawHeat();
  drawWords();
  drawAnomalies();
}

/* ---------------------------------------------------------------- 接入 */

async function viewAccess() {
  main.innerHTML = `<div class="title-row"><div><h1>接入</h1><p class="sub">读取中…</p></div></div>`;

  const [disc, certs, codes] = await Promise.all([
    api("/api/v1/discovery").catch(() => null),
    api("/api/v1/certs").catch(() => []),
    api("/api/v1/pair-codes").catch(() => []),
  ]);
  const devices = disc?.devices || [];
  const paired = devices.filter((d) => d.paired).length;
  const pending = devices.length - paired;
  const expiring = certs.filter((c) => c.expiring).length;

  const linkLabel = { wifi: "Wi-Fi", ethernet: "有线", offline: "离线", unknown: "未知" };

  main.innerHTML = `
    <div class="title-row">
      <div><h1>接入</h1>
        <p class="sub">mDNS 发现、一次性配对码、证书与吊销；组播不可用时退化为登记清单。</p></div>
      <div class="title-actions"><span class="stamp">CA ${esc(disc?.edge?.ca_fp || "—")}</span></div>
    </div>

    <div class="kpis">
      <div class="kpi"><div class="kpi-label">已接入</div><div class="kpi-value">${paired}</div>
        <div class="kpi-note">${pending} 台待配对</div></div>
      <div class="kpi"><div class="kpi-label">证书</div><div class="kpi-value">${certs.length}</div>
        <div class="kpi-note">365 天有效期</div></div>
      <div class="kpi"><div class="kpi-label">30 天内到期</div>
        <div class="kpi-value">${expiring}</div>
        <div class="kpi-note">到期前 30 天该续期</div></div>
      <div class="kpi"><div class="kpi-label">吊销</div>
        <div class="kpi-value">${certs.filter((c) => c.revoked).length}</div>
        <div class="kpi-note">CRL 可下载</div></div>
    </div>

    <div class="row split" style="align-items:start">
      <section class="panel fill">
        <div class="panel-head"><h2>发现的设备</h2><span class="meta">${devices.length} 台</span></div>
        <table class="table responsive">
          <thead><tr><th>设备</th><th>型号</th><th>版本</th><th>链路</th><th>状态</th><th></th></tr></thead>
          <tbody>${devices.map((d) => `<tr>
            <td><strong>${esc(d.device_id)}</strong>
              <div class="row-sub">${esc(d.scene || "—")} · ${d.source === "mdns" ? "mDNS" : "已登记"}</div></td>
            <td>${esc(d.model || "—")}</td>
            <td class="mono">${esc(d.fw || "—")}</td>
            <td>${esc(linkLabel[d.link] || "未知")}</td>
            <td>${d.paired ? `<span class="pill pill-ok">已配对</span>` : `<span class="pill pill-watch">待配对</span>`}</td>
            <td class="num">${d.paired ? "" : `<button class="btn btn-sm" data-pair="${esc(d.device_id)}">生成配对码</button>`}</td>
          </tr>`).join("") || `<tr><td colspan="6" class="dash">没有发现任何终端。</td></tr>`}</tbody>
        </table>
        <div style="display:flex;gap:8px;margin-top:16px;flex-wrap:wrap">
          <select class="control" id="pair-device" aria-label="选择要配对的设备" style="flex:1;min-width:160px">
            ${devices.map((d) => `<option value="${esc(d.device_id)}">${esc(d.device_id)}${d.paired ? "（已配对，将签发新码）" : ""}</option>`).join("") || `<option>没有设备</option>`}
          </select>
          <button class="btn" id="pair-btn">生成配对码</button>
        </div>
        <p class="hint grow-block" style="margin:14px 0 0" id="pair-hint">
          配对码 6 位、10 分钟有效，绑定设备公钥指纹，一次性使用；同一设备 5 次失败锁 10 分钟。
          终端广播 <span class="mono">_orpi-device._tcp</span>，边广播 <span class="mono">_orpi-edge._tcp</span>。</p>
      </section>

      ${panel("证书", `${certs.length} 张`, `<table class="table">
        <thead><tr><th>设备</th><th class="num">剩余</th><th class="num">序列号</th></tr></thead>
        <tbody>${certs.slice(0, 8).map((c) => `<tr>
          <td>${esc(c.device_id)}<div class="row-sub">${new Date(c.issued_at).toLocaleDateString("zh-CN")} 签发</div></td>
          <td class="num">${c.expiring ? `<span class="pill pill-watch">${c.days_left} 天</span>` : `${c.days_left} 天`}</td>
          <td class="num mono">${esc(String(c.serial).slice(0, 10))}</td>
        </tr>`).join("") || `<tr><td colspan="3" class="dash">还没有签发过证书。生成配对码后终端用 CSR 来换。</td></tr>`}</tbody>
      </table>
      <div style="display:flex;gap:8px;margin-top:16px;flex-wrap:wrap">
        <a class="btn btn-sm" href="/api/v1/ca.crt" target="_blank" rel="noopener">下载 CA</a>
        <a class="btn btn-sm" href="/api/v1/crl.pem" target="_blank" rel="noopener">下载 CRL</a>
      </div>
      <p class="hint" style="margin:14px 0 0">
        证书 365 天有效，到期前 30 天在列表标红。续期由终端提交 CSR 调
        <span class="mono">/devices/{id}/renew</span>，边不代签。</p>`)}
    </div>

    <div class="row">
      ${panel("最近的配对码", `${codes.length} 个`, `<div class="list">
        ${codes.slice(0, 5).map((c) => `<div class="list-row">
          <div class="grow"><div class="row-text mono" style="font-size:15px">${esc(c.code)}</div>
            <div class="row-sub">${esc(c.device_id || "—")} · ${c.attempts} 次尝试</div></div>
          <span class="pill ${c.used_at ? "pill-ok" : c.locked_until ? "pill-alert" : "pill-watch"}">
            ${c.used_at ? "已使用" : c.locked_until ? "已锁定" : "待使用"}</span>
        </div>`).join("") || `<div class="empty">还没有生成过配对码。</div>`}
      </div>`)}
    </div>`;

  $("pair-btn")?.addEventListener("click", async (ev) => {
    const id = $("pair-device").value;
    ev.currentTarget.disabled = true;
    try {
      const r = await api(`/api/v1/devices/${encodeURIComponent(id)}/pair`, { method: "POST" });
      $("pair-hint").textContent = `配对码 ${r.code}，${r.ttl_s / 60} 分钟内有效，已绑定该设备的公钥指纹。`;
      route(true);
    } catch (e) {
      toast(`生成失败：${e.message}`);
      ev.currentTarget.disabled = false;
    }
  });

  main.querySelectorAll("[data-pair]").forEach((btn) =>
    btn.addEventListener("click", async () => {
      try {
        const r = await api(`/api/v1/devices/${encodeURIComponent(btn.dataset.pair)}/pair`, { method: "POST" });
        $("pair-hint").textContent = `配对码 ${r.code}，${r.ttl_s / 60} 分钟内有效，绑定该设备的公钥指纹。`;
        btn.disabled = true;
      } catch (e) {
        toast(`生成失败：${e.message}`);
      }
    }));
}

/* ---------------------------------------------------------------- 上云 */

async function viewCloud() {
  main.innerHTML = `<div class="title-row"><div><h1>上云</h1><p class="sub">读取中…</p></div></div>`;

  const [o, outbox, preview] = await Promise.all([
    api("/api/v1/overview").catch(() => null),
    api("/api/v1/outbox").catch(() => []),
    api("/api/v1/report/preview").catch(() => null),
  ]);

  const pending = outbox.filter((x) => !x.sent_at);
  const sent = outbox.filter((x) => x.sent_at);

  main.innerHTML = `
    <div class="title-row">
      <div><h1>上云</h1>
        <p class="sub">每小时把日聚合、建议和词频打包成 <span class="mono">orpi.edge.report.v1</span>。
        发送失败进发件箱，按 1 / 5 / 30 分钟、2 小时退避，最多保留 7 天。</p></div>
      <div class="title-actions"><button class="btn btn-primary" id="push-now">立即上报</button></div>
    </div>

    <div class="kpis" style="grid-template-columns:repeat(3,minmax(0,1fr))">
      <div class="kpi"><div class="kpi-label">云地址</div>
        <div class="kpi-value" style="font-size:14px;font-family:var(--mono);word-break:break-all">${esc(o?.cloud_url || "未配置")}</div>
        <div class="kpi-note">${o?.cloud_ok ? "自动上报已开启" : "报表只留在本机发件箱"}</div></div>
      <div class="kpi"><div class="kpi-label">待发送</div>
        <div class="kpi-value">${pending.length}</div>
        <div class="kpi-note">按 report_id 幂等</div></div>
      <div class="kpi"><div class="kpi-label">已发送</div>
        <div class="kpi-value">${sent.length}</div>
        <div class="kpi-note">最近一次 ${sent[0] ? fmtTime(sent[0].sent_at, true) : "—"}</div></div>
    </div>

    <div class="kpis five">
      <div class="kpi"><div class="kpi-label">设备清单</div>
        <div class="kpi-value">${preview ? preview.counts.devices : "—"}</div>
        <div class="kpi-note">台</div></div>
      <div class="kpi"><div class="kpi-label">日聚合</div>
        <div class="kpi-value">${preview ? preview.counts.telemetry_daily : "—"}</div>
        <div class="kpi-note">行 · 只含 mean/slope/z</div></div>
      <div class="kpi"><div class="kpi-label">建议文本</div>
        <div class="kpi-value">${preview ? preview.counts.advice : "—"}</div>
        <div class="kpi-note">条 · 已过脱敏</div></div>
      <div class="kpi"><div class="kpi-label">词频</div>
        <div class="kpi-value">${preview ? preview.counts.word_freq : "—"}</div>
        <div class="kpi-note">行</div></div>
      <div class="kpi"><div class="kpi-label">隐私计数</div>
        <div class="kpi-value" style="font-size:16px">抑制 ${preview ? preview.privacy.suppressed_buckets : "—"}
          · 拦截 ${preview ? preview.privacy.raw_rejected : "—"}</div>
        <div class="kpi-note">k&lt;5 与原始字段</div></div>
    </div>
    <p class="hint" style="margin:12px 0 0">报表结构在出端前做二次脱敏：min/max、subject 与 userId 在端侧已剥离，
      载荷里出现原始字段会被云侧拒收并告警。</p>

    <div class="row">
      <section class="panel">
        <div class="panel-head"><h2>发件箱</h2><span class="meta">${outbox.length} 份报表</span></div>
        <table class="table responsive">
          <thead><tr><th>报告</th><th>生成</th><th>状态</th><th class="num">次数</th><th>最后一次错误</th></tr></thead>
          <tbody>
            ${outbox.map((x) => `<tr>
              <td class="mono">${esc(x.report_id)}</td>
              <td>${fmtTime(x.created_at, true)}</td>
              <td>${x.sent_at ? `<span class="pill pill-ok">已送达</span>` : `<span class="pill pill-watch">等待</span>`}</td>
              <td class="num">${x.attempts}</td>
              <td class="faint" style="white-space:normal;min-width:120px">${esc(x.last_error || "—")}</td>
            </tr>`).join("") || `<tr><td colspan="5" class="dash">还没有报表。点“立即上报”生成第一份。</td></tr>`}
          </tbody>
        </table>
      </section>

    </div>

    <div class="row">
      <section class="panel">
        <div class="panel-head"><h2>这份报表会发什么</h2>
          <span class="meta">${preview ? `report_id ${esc(preview.report_id)} · 前 8 行` : "预览不可用"}</span></div>
        ${preview && preview.sample.length ? `<table class="table responsive">
          <thead><tr><th>设备</th><th>日期</th><th>指标</th><th class="num">均值</th><th class="num">斜率</th><th class="num">z</th><th class="num">k</th><th class="num">样本</th></tr></thead>
          <tbody>${preview.sample.map((r) => `<tr>
            <td class="mono">${esc(r.device_id)}</td>
            <td>${esc(r.day)}</td>
            <td>${esc(r.metric)}</td>
            <td class="num">${fmtNum(r.mean, 2)}</td>
            <td class="num">${fmtNum(r.slope, 3)}</td>
            <td class="num">${fmtNum(r.z, 2)}</td>
            <td class="num">${r.k}</td>
            <td class="num">${fmtNum(r.n_samples)}</td>
          </tr>`).join("")}</tbody>
        </table>` : `<div class="empty">暂时没有可上报的日聚合。</div>`}
      </section>
    </div>`;

  document.getElementById("push-now").onclick = (e) => pushCloud(e.currentTarget);
}

/* ---------------------------------------------------------------- 设置 */

async function viewSettings() {
  let s;
  try {
    s = await api("/api/v1/settings");
    settingsCache = s;
  } catch (e) {
    main.innerHTML = `<div class="title-row"><div><h1>设置</h1></div></div><div class="row">${errBox(`读不到设置：${e.message}`)}</div>`;
    return;
  }

  main.innerHTML = `
    <div class="title-row"><div><h1>设置</h1>
      <p class="sub">改动即时生效并写回本机数据库，没有“保存”按钮。</p></div>
      <div class="title-actions"><span class="stamp">改动会立即写入</span></div>
    </div>

    <div class="row">
      <section class="panel">
        <div class="settings-row">
          <div class="settings-label"><h3>上报节奏</h3><p>端侧每窗口上报一次；边按这个节奏打包上云。</p></div>
          <div class="field">
            <label for="cadence">上云间隔（分钟）</label>
            <select class="control" id="cadence">
              ${[15, 30, 60, 120, 240].map((v) => `<option value="${v}" ${s.report_cadence_min === v ? "selected" : ""}>${v} 分钟</option>`).join("")}
            </select>
            <span class="hint">当前 ${s.report_cadence_min} 分钟一次。</span>
          </div>
        </div>

        <div class="settings-row">
          <div class="settings-label"><h3>云连接</h3><p>关掉后报表只留在发件箱，不影响本地分析。</p></div>
          <div class="field">
            <label class="switch"><input type="checkbox" id="cloud-enabled" ${s.cloud_enabled ? "checked" : ""}>
              <span class="track" aria-hidden="true"></span><span>允许自动上云</span></label>
            <span class="hint">云地址由 EDGE_CLOUD_URL 提供，页面不写死。</span>
          </div>
        </div>

        <div class="settings-row">
          <div class="settings-label"><h3>隐私</h3><p>个性化分析默认开，群体分析默认关。</p></div>
          <div class="field" style="gap:14px">
            <label class="switch"><input type="checkbox" id="personalization" ${s.personalization ? "checked" : ""}>
              <span class="track" aria-hidden="true"></span><span>个性化分析</span></label>
            <label class="switch"><input type="checkbox" id="group-analysis" ${s.group_analysis ? "checked" : ""}>
              <span class="track" aria-hidden="true"></span><span>群体分析（需 k≥5）</span></label>
            <div>
              <label for="kmin" style="display:block;margin-bottom:6px">最小 k</label>
              <select class="control" id="kmin">
                ${[5, 6, 8, 10].map((v) => `<option value="${v}" ${s.k_min === v ? "selected" : ""}>${v}</option>`).join("")}
              </select>
              <div class="hint">小于 k 的桶只留在端内，不出端。</div>
            </div>
          </div>
        </div>

        <div class="settings-row">
          <div class="settings-label"><h3>保留期</h3><p>边上的聚合数据保留天数，按天清理。</p></div>
          <div class="field">
            <label for="retention">保留天数</label>
            <select class="control" id="retention">
              ${[90, 180, 365].map((v) => `<option value="${v}" ${s.retention_days === v ? "selected" : ""}>${v} 天</option>`).join("")}
            </select>
          </div>
        </div>
      </section>
    </div>

    ${panel("自检", "GET /api/v1/health", `<div id="health" class="list">${skeleton(3)}</div>`)}`;

  const save = async (patch) => {
    try {
      settingsCache = await api("/api/v1/settings", { method: "PUT", body: JSON.stringify(patch) });
      toast("已保存");
    } catch (e) {
      toast(`保存失败：${e.message}`);
    }
  };

  document.getElementById("cadence").onchange = (e) => save({ report_cadence_min: Number(e.target.value) });
  document.getElementById("cloud-enabled").onchange = (e) => save({ cloud_enabled: e.target.checked });
  document.getElementById("personalization").onchange = (e) => save({ personalization: e.target.checked });
  document.getElementById("group-analysis").onchange = (e) => save({ group_analysis: e.target.checked });
  document.getElementById("kmin").onchange = (e) => save({ k_min: Number(e.target.value) });
  document.getElementById("retention").onchange = (e) => save({ retention_days: Number(e.target.value) });

  try {
    const h = await api("/api/v1/health");
    document.getElementById("health").innerHTML = `
      ${[["数据库", h.db], ["设备摄取鉴权", h.ingest_token === "set" ? "已启用" : "未启用（仅本机）"],
         ["管理鉴权", h.admin_token === "set" ? "已启用" : "未启用（仅本机）"],
         ["边 ID", h.edge_id],
         ["MQTT 主通道", h.mqtt?.enabled ? (h.mqtt.connected ? "已连接" : "未连接") : "未启用（走 HTTPS）"],
         ["mDNS", h.mdns?.enabled ? `广播中 ${h.mdns.service}` : "未启用"],
         ["定时上云", h.scheduler?.ticks ? `已执行 ${h.scheduler.ticks} 次` : "等待第一次"],
         ["磁盘加密", h.db_cipher === "sqlcipher" ? "SQLCipher" : "明文（部署到磁盘请用 LUKS）"]].map(([k, v]) => `
        <div class="list-row"><div class="grow">${esc(k)}</div><span class="muted">${esc(v)}</span></div>`).join("")}`;
  } catch (e) {
    document.getElementById("health").innerHTML = errBox(`自检失败：${e.message}`);
  }
}

/* ---------------------------------------------------------------- 路由 */

const routes = [
  [/^#\/$/, viewOverview, "overview"],
  [/^#\/overview$/, viewOverview, "overview"],
  [/^#\/devices$/, viewDevices, "devices"],
  [/^#\/devices\/(.+)$/, (m) => viewDevice(decodeURIComponent(m[1])), "devices"],
  [/^#\/analysis$/, viewAnalysis, "analysis"],
  [/^#\/access$/, viewAccess, "access"],
  [/^#\/cloud$/, viewCloud, "cloud"],
  [/^#\/settings$/, viewSettings, "settings"],
];

let routing = false;

async function route(quiet = false) {
  if (routing) return;
  routing = true;
  const hash = location.hash || "#/";
  const hit = routes.find(([re]) => re.test(hash));
  document.querySelectorAll(".nav a").forEach((a) =>
    a.removeAttribute("aria-current"));
  const nav = hit?.[2];
  if (nav) document.querySelector(`.nav a[data-nav="${nav}"]`)?.setAttribute("aria-current", "page");
  if (!quiet) main.scrollTop = 0;
  try {
    if (hit) await hit[1](hash.match(hit[0]));
    else main.innerHTML = `<div class="title-row"><h1>页面不存在</h1></div>`;
  } catch (e) {
    main.innerHTML = `<div class="title-row"><h1>出错了</h1></div><div class="row">${errBox(e.message)}</div>`;
    document.querySelector("[data-retry]")?.addEventListener("click", () => route(true));
  } finally {
    routing = false;
    document.querySelectorAll("[data-retry]").forEach((b) =>
      b.addEventListener("click", () => route(true)));
  }
}

window.addEventListener("hashchange", () => route());
route();
