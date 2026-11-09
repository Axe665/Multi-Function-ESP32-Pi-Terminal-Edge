/* SVG 图表：折线、热力、词云。不引图表库，样式与 token 一致。 */

const NS = "http://www.w3.org/2000/svg";

export function fmtTime(ts, withDate = false) {
  const d = new Date(ts);
  const hm = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  return withDate ? `${d.getMonth() + 1}/${d.getDate()} ${hm}` : hm;
}

export function fmtNum(v, decimals = 0) {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return v.toLocaleString("zh-CN", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

function niceTicks(min, max, count = 4) {
  if (min === max) { min -= 1; max += 1; }
  const span = max - min;
  const mag = Math.pow(10, Math.floor(Math.log10(span / count)));
  let step = mag;
  for (const m of [1, 2, 2.5, 5, 10]) {
    step = m * mag;
    if (span / step <= count + 1) break;
  }
  const lo = Math.floor(min / step) * step;
  const hi = Math.ceil(max / step) * step;
  const ticks = [];
  for (let v = lo; v <= hi + step / 2; v += step) ticks.push(+v.toFixed(10));
  return ticks;
}

function el(tag, attrs = {}, text) {
  const n = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text !== undefined) n.textContent = text;
  return n;
}

/* 让图表在容器宽度变化时重画（行内 SVG 用 CSS 像素，文字不会被拉变形） */
export function mount(host, draw) {
  let last = 0;
  const run = () => {
    const w = host.clientWidth;
    if (!w || Math.abs(w - last) < 2) return;
    last = w;
    host.replaceChildren(draw(w));
  };
  const ro = new ResizeObserver(() => run());
  ro.observe(host);
  run();
  return () => ro.disconnect();
}

/* ---------------------------------------------------------------- 折线 */

export function line(host, opts) {
  const {
    points = [], unit = "", decimals = 1, height = 300,
    baseline = null, anomalies = [], label = "",
  } = opts;

  if (!points.length) {
    host.replaceChildren(Object.assign(document.createElement("div"), {
      className: "empty", textContent: "这个时间窗内没有聚合数据。",
    }));
    return;
  }

  mount(host, (W) => {
    const padL = 46, padR = 18, padT = 16, padB = 28;
    const H = height;
    const iw = Math.max(40, W - padL - padR);
    const ih = H - padT - padB;

    const vals = points.map((p) => p.mean);
    if (baseline !== null) vals.push(baseline);
    const min = Math.min(...vals), max = Math.max(...vals);
    const ticks = niceTicks(min, max, 4);
    const y0 = ticks[0], y1 = ticks[ticks.length - 1];
    const X = (i) => padL + (points.length === 1 ? iw / 2 : (i / (points.length - 1)) * iw);
    const Y = (v) => padT + ih - ((v - y0) / (y1 - y0)) * ih;

    const svg = el("svg", {
      class: "chart", viewBox: `0 0 ${W} ${H}`, width: W, height: H,
      role: "img", "aria-label": label || "趋势折线",
    });

    for (const t of ticks) {
      svg.append(el("line", { class: "grid-line", x1: padL, x2: W - padR, y1: Y(t), y2: Y(t) }));
      svg.append(el("text", { class: "axis", x: padL - 10, y: Y(t) + 4, "text-anchor": "end" },
        fmtNum(t, decimals > 1 ? 1 : decimals)));
    }

    const n = points.length;
    const xLabelCount = Math.min(6, n);
    for (let i = 0; i < xLabelCount; i++) {
      const idx = Math.round((i / Math.max(1, xLabelCount - 1)) * (n - 1));
      const p = points[idx];
      const anchor = i === 0 ? "start" : i === xLabelCount - 1 ? "end" : "middle";
      svg.append(el("text", { class: "axis", x: X(idx), y: H - 8, "text-anchor": anchor },
        fmtTime(p.ts)));
    }

    if (baseline !== null) {
      const by = Y(baseline);
      svg.append(el("line", { class: "baseline", x1: padL, x2: W - padR, y1: by, y2: by }));
    }

    const d = points.map((p, i) => `${i ? "L" : "M"}${X(i).toFixed(1)} ${Y(p.mean).toFixed(1)}`).join(" ");
    svg.append(el("path", { class: "series", d }));

    const flagged = new Set(anomalies.map((a) => a.ts));
    points.forEach((p, i) => {
      if (!flagged.has(p.ts)) return;
      svg.append(el("circle", { class: "dot-alert", cx: X(i), cy: Y(p.mean), r: 2.6 }));
    });

    const hover = el("rect", { class: "hit", x: padL, y: padT, width: iw, height: ih });
    svg.append(hover);
    const cursor = el("circle", { class: "dot", r: 3, opacity: 0 });
    svg.append(cursor);

    let tip = document.getElementById("tip");
    if (!tip) {
      tip = document.createElement("div");
      tip.id = "tip";
      tip.className = "tip";
      tip.hidden = true;
      document.body.append(tip);
    }

    hover.addEventListener("mousemove", (ev) => {
      const box = svg.getBoundingClientRect();
      const rel = (ev.clientX - box.left - padL) / iw;
      const i = Math.max(0, Math.min(n - 1, Math.round(rel * (n - 1))));
      const p = points[i];
      cursor.setAttribute("cx", X(i));
      cursor.setAttribute("cy", Y(p.mean));
      cursor.setAttribute("opacity", 1);
      tip.hidden = false;
      tip.textContent = `${fmtTime(p.ts, true)} · ${fmtNum(p.mean, decimals)} ${unit} · k=${p.k}`;
      tip.style.left = `${Math.min(ev.clientX + 14, window.innerWidth - tip.offsetWidth - 8)}px`;
      tip.style.top = `${ev.clientY - 34}px`;
    });
    hover.addEventListener("mouseleave", () => {
      cursor.setAttribute("opacity", 0);
      tip.hidden = true;
    });

    return svg;
  });
}

/* ---------------------------------------------------------------- 热力矩阵 */

const WEEK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];

/* 5 级离散色阶：#e8b45c 按 8–64% 叠在深色地面上。
   连续渐变在 7×24 的矩阵里会糊成一片，离散后时段边界才读得出来。 */
const HEAT_LEVELS = [0.08, 0.22, 0.36, 0.5, 0.64];

function levelColor(t) {
  const i = Math.min(HEAT_LEVELS.length - 1, Math.max(0, Math.floor(t * HEAT_LEVELS.length)));
  return mix("#16181b", "#e8b45c", HEAT_LEVELS[i] + (i === 0 ? 0 : 0));
}

function mix(a, b, t) {
  const pa = [1, 3, 5].map((i) => parseInt(a.slice(i, i + 2), 16));
  const pb = [1, 3, 5].map((i) => parseInt(b.slice(i, i + 2), 16));
  const p = pa.map((v, i) => Math.round(v + (pb[i] - v) * t));
  return `rgb(${p[0]},${p[1]},${p[2]})`;
}

export function heatmap(host, cells, opts = {}) {
  const { decimals = 1, unit = "" } = opts;
  const h = (tag, attrs = {}, text) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
    if (text !== undefined) n.textContent = text;
    return n;
  };
  const byKey = new Map(cells.map((c) => [`${c.dow}-${c.hour}`, c]));
  const values = cells.map((c) => c.mean);
  const max = values.length ? Math.max(...values) : 1;
  const min = values.length ? Math.min(...values) : 0;
  const span = max - min || 1;

  const wrap = document.createElement("div");
  const head = document.createElement("div");
  head.className = "heat";
  head.style.gridTemplateColumns = `34px repeat(24, minmax(0, 1fr))`;

  head.append(h("span", { class: "axis" }, ""));
  for (let hr = 0; hr < 24; hr++) {
    head.append(h("span", { class: "axis", style: "font-size:10px;color:var(--faint)" },
      hr % 6 === 0 ? String(hr).padStart(2, "0") : ""));
  }

  for (let dow = 0; dow < 7; dow++) {
    head.append(h("span", { class: "axis", style: "font-size:11px;color:var(--faint);line-height:22px" }, WEEK[dow]));
    for (let hr = 0; hr < 24; hr++) {
      const c = byKey.get(`${dow}-${hr}`);
      const cell = document.createElement("div");
      cell.className = "heat-cell";
      if (!c) {
        cell.style.background = "#101214";
        cell.title = `${WEEK[dow]} ${hr}:00 无数据`;
      } else {
        const t = Math.max(0, Math.min(1, (c.mean - min) / span));
        cell.style.background = levelColor(t);
        cell.title = `${WEEK[dow]} ${hr}:00 · ${fmtNum(c.mean, decimals)} ${unit} · ${c.n} 个窗口`;
      }
      head.append(cell);
    }
  }
  wrap.append(head);

  const scale = document.createElement("div");
  scale.className = "legend";
  scale.style.marginTop = "12px";
  scale.innerHTML = HEAT_LEVELS.map((a) => `<span><i style="background:${mix("#16181b", "#e8b45c", a)}"></i></span>`).join("")
    + `<span>${fmtNum(min, decimals)} → ${fmtNum(max, decimals)} ${unit}</span>
       <span><i style="background:#101214;border:1px solid #262b31"></i>该时段没有窗口</span>`;
  wrap.append(scale);
  host.replaceChildren(wrap);
}

/* ---------------------------------------------------------------- 词云 */

export function wordcloud(host, words) {
  if (!words.length) {
    host.replaceChildren(Object.assign(document.createElement("div"), {
      className: "empty", textContent: "最近没有生成建议文本。",
    }));
    return;
  }
  const max = Math.max(...words.map((w) => w.count));
  const cloud = document.createElement("div");
  cloud.className = "cloud";
  words.slice(0, 26).forEach((w, i) => {
    const t = w.count / max;
    const s = document.createElement("span");
    s.textContent = w.word;
    s.style.fontSize = `${11 + Math.round(t * 17)}px`;
    if (i < 6) s.classList.add("top");
    s.title = `${w.word} · ${w.count} 次`;
    cloud.append(s);
  });
  host.replaceChildren(cloud);
}

/* ---------------------------------------------------------------- 条形清单 */

export function barList(host, rows, opts = {}) {
  const { unit = "", decimals = 0, max = null } = opts;
  if (!rows.length) {
    host.replaceChildren(Object.assign(document.createElement("div"), {
      className: "empty", textContent: "没有可比较的数据。",
    }));
    return;
  }
  const top = max ?? Math.max(...rows.map((r) => r.value)) ?? 1;
  const wrap = document.createElement("div");
  wrap.className = "list";
  rows.forEach((r) => {
    const row = document.createElement("div");
    row.className = "list-row";
    row.innerHTML = `<div class="grow">
        <div class="row-text">${r.label}</div>
        <div class="row-sub">${fmtNum(r.value, decimals)} ${unit}${r.note ? ` · ${r.note}` : ""}</div>
      </div>
      <div style="width:96px;height:4px;background:#22262c;border-radius:2px;overflow:hidden;flex:none">
        <div style="width:${Math.round((r.value / top) * 100)}%;height:100%;background:var(--accent)"></div>
      </div>`;
    wrap.append(row);
  });
  host.replaceChildren(wrap);
}
