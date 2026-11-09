/* 三个 3D 概念共用的渲染底座：渲染器、相机、泛光、尺寸与帧循环。
   每个概念只需要提供 build(ctx) → 返回一个 update(t) 函数。 */

import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

export function boot({ canvas, build, bloom = 0.85, radius = 0.6, threshold = 0.2, fov = 45 }) {
  const renderer = new THREE.WebGLRenderer({
    canvas, antialias: true, alpha: true, powerPreference: "high-performance",
  });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.setClearColor(0x000000, 0);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(fov, 1, 0.1, 200);

  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloomPass = new UnrealBloomPass(new THREE.Vector2(1, 1), bloom, radius, threshold);
  composer.addPass(bloomPass);
  composer.addPass(new OutputPass());

  const ctx = { renderer, scene, camera, composer, bloomPass, THREE };

  function resize() {
    // clientWidth 在布局完成前可能是 0，退到 bounding rect 再退到视口
    const rect = canvas.getBoundingClientRect();
    const w = Math.round(canvas.clientWidth || rect.width || window.innerWidth || 1);
    const h = Math.round(canvas.clientHeight || rect.height || window.innerHeight || 1);
    // 绘制缓冲封顶：软件渲染、树莓派、集显都撑不住全分辨率 + 泛光
    const MAX_PIXELS = 460000;
    const scale = Math.min(1, Math.sqrt(MAX_PIXELS / Math.max(1, w * h)));
    const bw = Math.max(1, Math.round(w * scale));
    const bh = Math.max(1, Math.round(h * scale));
    renderer.setSize(bw, bh, false);
    composer.setSize(bw, bh);
    bloomPass.resolution.set(bw, bh);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }
  const ro = new ResizeObserver(resize);
  ro.observe(canvas);
  resize();

  const update = build(ctx) || (() => {});
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  // ?still=1：只画几帧就停。截图与水印用，也给缩略图省 GPU
  const still = new URLSearchParams(location.search).has("still");

  let raf = 0;
  let t0 = performance.now();
  if (still) {
    // 同步渲染几帧：截图工具在 rAF 之前就抓帧，异步会抓到空画布
    resize();
    for (let i = 0; i < 3; i++) {
      update(0.6 + i * 0.35, ctx);
      composer.render();
    }
    return { ctx, stop: () => ro.disconnect() };
  }

  const loop = (now) => {
    update((now - t0) / 1000, ctx);
    composer.render();
    raf = requestAnimationFrame(loop);
  };
  const kick = () => {
    cancelAnimationFrame(raf);
    if (document.hidden) return;
    if (reduce) { update(1.2, ctx); composer.render(); return; }
    raf = requestAnimationFrame(loop);
  };
  document.addEventListener("visibilitychange", kick);
  kick();

  return { ctx, stop: () => { cancelAnimationFrame(raf); ro.disconnect(); } };
}

/* 程序化环境贴图：不给玻璃一个假 HDR 也能折射出层次 */
export function studioEnv(renderer, THREE_) {
  const pmrem = new THREE_.PMREMGenerator(renderer);
  const s = new THREE_.Scene();
  s.background = new THREE_.Color(0x0b1016);
  const geo = new THREE_.SphereGeometry(12, 32, 32);
  const mat = new THREE_.MeshBasicMaterial({ side: THREE_.BackSide, color: 0x0a1016 });
  s.add(new THREE_.Mesh(geo, mat));

  const lights = [
    [0xffb35c, 9, -4, 3, 5, 2.2],
    [0x4fd1c5, 8, 4, -3, 4, 2.0],
    [0xffffff, 6, 0, 7, 6, 2.6],
    [0x7be0b0, 4, 0, -6, -3, 1.6],
  ];
  for (const [c, i, x, y, z, r] of lights) {
    const m = new THREE_.Mesh(
      new THREE_.SphereGeometry(r || 1.6, 16, 16),
      new THREE_.MeshBasicMaterial({ color: c })
    );
    m.material.color.multiplyScalar(i);
    m.position.set(x, y, z);
    s.add(m);
  }
  const tex = pmrem.fromScene(s, 0.04).texture;
  pmrem.dispose();
  return tex;
}
