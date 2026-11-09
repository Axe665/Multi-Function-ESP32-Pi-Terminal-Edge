/* 边的场景：三束光流从三台终端汇入一个旋转的聚合环。
   粒子位置在顶点着色器里按 (seed, time) 解析求出，CPU 每帧只更新几个 uniform。 */

import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

const VERT = `
uniform float uTime;
uniform float uSpeed;
uniform float uCull;
uniform vec3 uOn;
attribute float aStream;
attribute float aSeed;
attribute float aCull;
varying float vAlpha;
varying float vWarm;

void main() {
  float ph = fract(aSeed + uTime * uSpeed * (0.55 + fract(aSeed * 7.31) * 0.7));
  float e = aStream;
  float y0 = (e - 1.0) * 1.15;
  float z0 = (fract(aSeed * 3.17) - 0.5) * 1.4;

  float x = mix(-7.4, 7.0, ph);
  float conv = smoothstep(-2.2, -0.05, x);
  float swirl = exp(-pow(x / 1.1, 2.0));
  float ang = ph * 26.0 + aSeed * 6.283;

  float y = y0 * (1.0 - conv) + sin(ang) * 0.34 * swirl;
  float z = z0 * (1.0 - conv) + cos(ang * 0.8) * 0.42 * swirl;

  // 汇聚到环上之后重新散开一点
  float post = smoothstep(1.4, 3.6, x);
  y += (fract(aSeed * 5.7) - 0.5) * 0.7 * post;
  z += (fract(aSeed * 9.1) - 0.5) * 0.5 * post;

  vec4 mv = modelViewMatrix * vec4(x, y, z, 1.0);
  gl_Position = projectionMatrix * mv;

  float dead = step(1.0 - uCull, aCull) * smoothstep(-1.6, 0.05, x);
  float on = uOn[int(clamp(e, 0.0, 2.0))];
  float depth = clamp(1.0 - (-mv.z - 4.0) / 14.0, 0.0, 1.0);

  gl_PointSize = (1.6 + 3.4 * depth) * on * (0.7 + 0.6 * swirl);
  vWarm = swirl;
  vAlpha = (1.0 - dead) * on * (0.10 + 0.75 * depth) * smoothstep(0.0, 0.06, ph);
}`;

const FRAG = `
varying float vAlpha;
varying float vWarm;
void main() {
  vec2 d = gl_PointCoord - 0.5;
  float r = length(d);
  if (r > 0.5) discard;
  float core = smoothstep(0.5, 0.0, r);
  vec3 cold = vec3(1.0, 0.62, 0.32);
  vec3 hot = vec3(1.0, 0.90, 0.72);
  gl_FragColor = vec4(mix(cold, hot, vWarm) * core, vAlpha * core);
}`;

export function createScene(host) {
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setClearColor(0x05060a, 0);
  host.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 60);
  camera.position.set(0, 1.4, 8.6);

  const COUNT = 26000;
  const geo = new THREE.BufferGeometry();
  const stream = new Float32Array(COUNT);
  const seed = new Float32Array(COUNT);
  const cull = new Float32Array(COUNT);
  const pos = new Float32Array(COUNT * 3);
  for (let i = 0; i < COUNT; i++) {
    stream[i] = i % 3;
    seed[i] = Math.random();
    cull[i] = Math.random();
  }
  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  geo.setAttribute("aStream", new THREE.BufferAttribute(stream, 1));
  geo.setAttribute("aSeed", new THREE.BufferAttribute(seed, 1));
  geo.setAttribute("aCull", new THREE.BufferAttribute(cull, 1));

  const mat = new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uSpeed: { value: 0.055 },
      uCull: { value: 0.12 },
      uOn: { value: new THREE.Vector3(1, 1, 1) },
    },
    vertexShader: VERT,
    fragmentShader: FRAG,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  });
  const points = new THREE.Points(geo, mat);
  scene.add(points);

  // 聚合环
  const ringGeo = new THREE.TorusGeometry(1.15, 0.012, 8, 220);
  const ringMat = new THREE.MeshBasicMaterial({ color: 0xffb45c, transparent: true, opacity: 0.9 });
  const ring = new THREE.Mesh(ringGeo, ringMat);
  ring.rotation.y = Math.PI / 2.6;
  ring.rotation.z = 0.24;
  scene.add(ring);

  const ring2 = ring.clone();
  ring2.scale.setScalar(1.22);
  ring2.material = new THREE.MeshBasicMaterial({ color: 0xff8a4c, transparent: true, opacity: 0.35 });
  scene.add(ring2);

  // 极淡的坐标网格：给空间一个尺度感
  const grid = new THREE.GridHelper(26, 26, 0x1b1f26, 0x11141a);
  grid.position.y = -3.4;
  grid.material.transparent = true;
  grid.material.opacity = 0.5;
  scene.add(grid);

  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(1, 1), 0.85, 0.7, 0.22);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());

  const state = { speed: 0.055, cull: 0.12, on: [1, 1, 1], glow: 0.85 };
  const pointer = { x: 0, y: 0, tx: 0, ty: 0 };

  window.addEventListener("pointermove", (e) => {
    pointer.tx = (e.clientX / window.innerWidth - 0.5) * 2;
    pointer.ty = (e.clientY / window.innerHeight - 0.5) * 2;
  });

  function resize() {
    const w = host.clientWidth || window.innerWidth;
    const h = host.clientHeight || window.innerHeight;
    renderer.setSize(w, h, false);
    composer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  const ro = new ResizeObserver(resize);
  ro.observe(host);
  resize();

  let raf = 0;
  let start = 0;
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function frame(now) {
    if (!start) start = now;
    const t = (now - start) / 1000;

    pointer.x += (pointer.tx - pointer.x) * 0.04;
    pointer.y += (pointer.ty - pointer.y) * 0.04;

    mat.uniforms.uTime.value = t;
    mat.uniforms.uSpeed.value = state.speed;
    mat.uniforms.uCull.value = state.cull;
    mat.uniforms.uOn.value.set(...state.on);

    ring.rotation.z = 0.24 + Math.sin(t * 0.35) * 0.12;
    ring2.rotation.z = -0.1 - Math.sin(t * 0.28) * 0.16;
    const pulse = 1 + Math.sin(t * 1.1) * 0.03 * (1 + state.glow);
    ring.scale.setScalar(pulse);
    ringMat.opacity = 0.55 + 0.35 * state.glow;

    camera.position.x = pointer.x * 0.9;
    camera.position.y = 1.4 - pointer.y * 0.5;
    camera.lookAt(0, 0, 0);

    composer.render();
    raf = requestAnimationFrame(frame);
  }

  if (reduced) {
    mat.uniforms.uTime.value = 2.4;
    composer.render();
  } else {
    raf = requestAnimationFrame(frame);
  }

  document.addEventListener("visibilitychange", () => {
    cancelAnimationFrame(raf);
    if (!document.hidden && !reduced) raf = requestAnimationFrame(frame);
  });

  return {
    setData(d) {
      state.speed = 0.035 + Math.min(0.08, (d.batches || 0) / 12000);
      state.cull = Math.min(0.55, (d.suppressed || 0) / Math.max(1, (d.batches || 1) * 3));
      state.on = [0, 1, 2].map((i) => (d.online && d.online[i] ? 1 : 0.08));
      state.glow = Math.min(1, (d.alerts || 0) / 18);
      bloom.strength = 0.55 + state.glow * 0.6;
    },
    focus(mode) {
      // 切换页面时给场景一个不同的姿态
      const poses = {
        overview: { y: 1.4, z: 8.6 },
        devices: { y: 2.6, z: 7.4 },
        analysis: { y: 0.6, z: 9.6 },
        cloud: { y: 1.9, z: 7.8 },
        settings: { y: 3.2, z: 8.0 },
      };
      const p = poses[mode] || poses.overview;
      animePose(p);
    },
    destroy() { cancelAnimationFrame(raf); ro.disconnect(); renderer.dispose(); },
  };

  function animePose(target) {
    const from = { y: camera.position.y, z: camera.position.z };
    const t0 = performance.now();
    const step = (now) => {
      const k = Math.min(1, (now - t0) / 900);
      const e = 1 - Math.pow(1 - k, 3);
      camera.position.y = from.y + (target.y - from.y) * e;
      camera.position.z = from.z + (target.z - from.z) * e;
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
}
