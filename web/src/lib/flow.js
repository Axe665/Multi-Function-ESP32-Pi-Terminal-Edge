/* 边的核心视觉：粒子从三台终端汇入环形聚合点，被 k 抑制的那部分在中途熄灭。

   位置不是逐帧积分的：每个粒子的位置是 (seed, time) 的解析函数，
   所以整条流场只占一个 draw call，树莓派上也跑得动。 */

import { VERT, program, buffer, perspective, lookAt, multiply, rotationY, animate } from "./glcore.js";

const FS = `#version 300 es
precision highp float;
in float vAlpha;
in float vWarm;
uniform float uDark;
out vec4 outColor;
void main() {
  vec2 d = gl_PointCoord - 0.5;
  float r = length(d);
  if (r > 0.5) discard;
  float edge = smoothstep(0.5, 0.10, r);
  // 白底用深琥珀，暗底用亮琥珀；同一套粒子，两套主题都看得见
  vec3 cold = mix(vec3(0.24, 0.15, 0.03), vec3(0.62, 0.55, 0.40), uDark);
  vec3 warm = mix(vec3(0.56, 0.25, 0.00), vec3(1.0, 0.86, 0.55), uDark);
  vec3 c = mix(cold, warm, vWarm);
  outColor = vec4(c * edge, vAlpha * edge);
}`;

const VS = `#version 300 es
precision highp float;
in vec4 aSeed;          // x: 发射器 0..2, y: 相位, z: 速度抖动, w: 是否被抑制
uniform mat4 uProj;
uniform mat4 uView;
uniform float uTime;
uniform float uSpeed;
uniform float uCull;
uniform vec3 uEmitters;  // 每台终端是否在线
uniform float uAlerts;
uniform float uDark;
out float vAlpha;
out float vWarm;

void main() {
  float e = aSeed.x;
  float ph = fract(aSeed.y + uTime * uSpeed * (0.6 + aSeed.z * 0.8));
  float y0 = (e - 1.0) * 0.62;
  float z0 = (fract(aSeed.z * 7.13) - 0.5) * 0.55;

  // x 从 -5.6 走到 5.8；接近环（x≈0）时纵向收敛并涡旋
  float x = mix(-5.6, 5.8, ph);
  float conv = smoothstep(-1.7, -0.05, x);
  float swirl = exp(-pow(x / 0.72, 2.0));
  float y = y0 * (1.0 - conv) + sin(ph * 34.0 + aSeed.z * 6.28) * 0.16 * swirl;
  float z = z0 * (1.0 - conv) + cos(ph * 27.0 + aSeed.y * 6.28) * 0.16 * swirl;

  // 越过聚合环后重新散开一点，出口才不是一根发丝
  float post = smoothstep(0.7, 1.6, x);
  y += (aSeed.y - 0.5) * 0.22 * post;
  z += (fract(aSeed.z * 3.7) - 0.5) * 0.16 * post;
  vec3 pos = vec3(x, y, z);

  // 被抑制的粒子在进入聚合环之前熄灭，不参与后续流动
  float dead = step(1.0 - uCull, aSeed.w) * smoothstep(-1.1, 0.05, x);
  float em = mix(0.12, 1.0, uEmitters[int(clamp(e, 0.0, 2.0))]);

  vec4 view = uView * vec4(pos, 1.0);
  gl_Position = uProj * view;

  float depth = clamp(1.0 - (-view.z - 1.6) / 4.5, 0.0, 1.0);
  gl_PointSize = (3.0 + 5.4 * depth) * uEmitters[int(clamp(e, 0.0, 2.0))];
  vWarm = swirl * (0.55 + 0.45 * uAlerts);
  vAlpha = (1.0 - dead) * em * (0.30 + 0.70 * depth) * smoothstep(0.0, 0.06, ph) * (1.0 - smoothstep(0.94, 1.0, ph));
  vAlpha = min(1.0, vAlpha * mix(1.35, 1.0, uDark));
}`;

const RING_VS = `#version 300 es
precision highp float;
in vec2 aPos;
uniform mat4 uProj;
uniform mat4 uView;
uniform float uPulse;
out float vA;
void main() {
  vec3 p = vec3(aPos.x * (0.5 + 0.02 * uPulse), aPos.y * (0.5 + 0.02 * uPulse), 0.0);
  gl_Position = uProj * uView * vec4(p, 1.0);
  vA = 0.75 + 0.25 * uPulse;
}`;

const RING_FS = `#version 300 es
precision highp float;
in float vA;
uniform float uDark;
out vec4 outColor;
void main() {
  outColor = vec4(mix(vec3(0.52, 0.28, 0.02), vec3(1.0, 0.82, 0.46), uDark), vA);
}`;

const COUNT = 16000;

export function createFlow(canvas, opts = {}) {
  const gl = canvas.getContext("webgl2", {
    antialias: false, alpha: true, premultipliedAlpha: true, powerPreference: "low-power",
  });
  if (!gl) return fallback(canvas, opts);

  const prog = program(gl, VS, FS);
  const ringProg = program(gl, RING_VS, RING_FS);

  const seeds = new Float32Array(COUNT * 4);
  for (let i = 0; i < COUNT; i++) {
    seeds[i * 4] = i % 3;                       // 三台终端轮转
    seeds[i * 4 + 1] = Math.random();
    seeds[i * 4 + 2] = Math.random();
    seeds[i * 4 + 3] = Math.random();
  }
  const seedBuf = buffer(gl, seeds);
  const loc = {
    seed: gl.getAttribLocation(prog, "aSeed"),
    proj: gl.getUniformLocation(prog, "uProj"),
    view: gl.getUniformLocation(prog, "uView"),
    time: gl.getUniformLocation(prog, "uTime"),
    speed: gl.getUniformLocation(prog, "uSpeed"),
    cull: gl.getUniformLocation(prog, "uCull"),
    emitters: gl.getUniformLocation(prog, "uEmitters"),
    alerts: gl.getUniformLocation(prog, "uAlerts"),
    dark: gl.getUniformLocation(prog, "uDark"),
  };
  const rloc = {
    pos: gl.getAttribLocation(ringProg, "aPos"),
    proj: gl.getUniformLocation(ringProg, "uProj"),
    view: gl.getUniformLocation(ringProg, "uView"),
    pulse: gl.getUniformLocation(ringProg, "uPulse"),
    dark: gl.getUniformLocation(ringProg, "uDark"),
  };

  const ring = new Float32Array(97 * 2);
  for (let i = 0; i <= 96; i++) {
    const a = (i / 96) * Math.PI * 2;
    ring[i * 2] = Math.cos(a);
    ring[i * 2 + 1] = Math.sin(a);
  }
  const ringBuf = buffer(gl, ring);

  const state = {
    speed: 0.12, cull: 0.12, alerts: 0.2,
    emitters: [1, 1, 1],
  };

  function resize() {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const w = Math.max(1, Math.round(canvas.clientWidth * dpr));
    const h = Math.max(1, Math.round(canvas.clientHeight * dpr));
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    gl.viewport(0, 0, w, h);
    return w / h;
  }

  let aspect = 2.2;
  const ro = new ResizeObserver(() => { aspect = resize(); });
  ro.observe(canvas);
  aspect = resize();

  const view = lookAt([0, 0.5, 4.6], [0, 0, 0], [0, 1, 0]);
  // 世界范围 11.8 × 2.4：按画布比例算 fov，宽画布里流场铺满整条带子
  const fitProj = (a) => {
    const d = 4.6, W = 11.8;
    const visH = Math.max(1.2, Math.min(4.0, W / a));
    return perspective(2 * Math.atan(visH / 2 / d), a, 0.1, 20);
  };
  let proj = fitProj(aspect);

  gl.clearColor(0, 0, 0, 0);
  gl.enable(gl.BLEND);
  gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

  const stop = animate((t) => {
    const a = resize();
    if (a !== aspect || !proj) { aspect = a; proj = fitProj(a); }
    gl.clear(gl.COLOR_BUFFER_BIT);
    const mvp = multiply(proj, multiply(view, rotationY(Math.sin(t * 0.08) * 0.10)));

    gl.useProgram(prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, seedBuf);
    gl.enableVertexAttribArray(loc.seed);
    gl.vertexAttribPointer(loc.seed, 4, gl.FLOAT, false, 0, 0);
    gl.uniformMatrix4fv(loc.proj, false, mvp);
    gl.uniformMatrix4fv(loc.view, false, view);
    gl.uniform1f(loc.time, t);
    gl.uniform1f(loc.speed, state.speed);
    gl.uniform1f(loc.cull, state.cull);
    gl.uniform1f(loc.alerts, state.alerts);
    gl.uniform3f(loc.emitters, ...state.emitters);
    const dark = document.documentElement.dataset.theme === "dark" ? 1 : 0;
    gl.uniform1f(loc.dark, dark);
    gl.drawArrays(gl.POINTS, 0, COUNT);

    gl.useProgram(ringProg);
    gl.bindBuffer(gl.ARRAY_BUFFER, ringBuf);
    gl.enableVertexAttribArray(rloc.pos);
    gl.vertexAttribPointer(rloc.pos, 2, gl.FLOAT, false, 0, 0);
    gl.uniformMatrix4fv(rloc.proj, false, mvp);
    gl.uniformMatrix4fv(rloc.view, false, view);
    gl.uniform1f(rloc.pulse, 0.5 + 0.5 * Math.sin(t * 1.4) * (0.4 + state.alerts));
    gl.uniform1f(rloc.dark, dark);
    gl.drawArrays(gl.LINE_STRIP, 0, 97);
    // 再画一圈稍大的同心环，模拟环的厚度（WebGL 的 lineWidth 不可靠）
    gl.uniform1f(rloc.pulse, 0.25 + 0.25 * Math.sin(t * 1.4));
    gl.drawArrays(gl.LINE_STRIP, 0, 97);
  });

  return {
    setData(d) {
      const batches = Math.max(1, d.batches || 1);
      state.speed = 0.10 + Math.min(0.10, batches / 9000);
      state.cull = Math.min(0.6, (d.suppressed || 0) / (batches * 3));
      state.alerts = Math.min(1, (d.alerts || 0) / 20);
      state.emitters = [0, 1, 2].map((i) => (d.online && d.online[i] ? 1 : 0.12));
    },
    destroy() { stop(); ro.disconnect(); },
  };
}

/* 没有 WebGL2：画一张静态图，信息不缺 */
function fallback(canvas, opts) {
  const ctx = canvas.getContext("2d");
  const draw = () => {
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = canvas.clientWidth * dpr;
    canvas.height = canvas.clientHeight * dpr;
    ctx.scale(dpr, dpr);
    const w = canvas.clientWidth, h = canvas.clientHeight;
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = "rgba(232,180,92,0.5)";
    ctx.lineWidth = 1;
    for (let i = 0; i < 3; i++) {
      const y = h * (0.25 + i * 0.25);
      ctx.beginPath();
      ctx.moveTo(w * 0.08, y);
      ctx.bezierCurveTo(w * 0.35, y, w * 0.4, h / 2, w * 0.5, h / 2);
      ctx.stroke();
    }
    ctx.beginPath();
    ctx.arc(w / 2, h / 2, Math.min(w, h) * 0.16, 0, Math.PI * 2);
    ctx.strokeStyle = "rgba(232,180,92,0.8)";
    ctx.stroke();
  };
  const ro = new ResizeObserver(draw);
  ro.observe(canvas);
  draw();
  return { setData() {}, destroy() { ro.disconnect(); } };
}
