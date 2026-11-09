/* 入场与数字：把 anime.js 收在一处，视图里只写 data-* 标记。 */

const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export function observe(root = document) {
  const items = root.querySelectorAll("[data-reveal]");
  if (reduced()) {
    items.forEach((el) => el.classList.add("in"));
    root.querySelectorAll("[data-count]").forEach((el) => {
      el.textContent = format(el, Number(el.dataset.count));
    });
    return () => {};
  }

  const io = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      const el = entry.target;
      const delay = Number(el.dataset.delay || 0);
      io.unobserve(el);
      window.anime({
        targets: el,
        opacity: [0, 1],
        translateY: [26, 0],
        duration: 820,
        delay,
        easing: "cubicBezier(0.16, 1, 0.3, 1)",
        begin: () => el.classList.add("in"),
      });
      el.querySelectorAll("[data-count]").forEach((n, i) => {
        window.anime({
          targets: { v: 0 },
          v: Number(n.dataset.count),
          duration: 1100,
          delay: delay + 120 + i * 90,
          easing: "easeOutExpo",
          update(anim) {
            n.textContent = format(n, anim.animations[0].currentValue);
          },
        });
      });
      el.querySelectorAll("[data-bar]").forEach((b, i) => {
        b.style.width = "0%";
        window.anime({
          targets: b,
          width: `${b.dataset.bar}%`,
          duration: 900,
          delay: delay + 160 + i * 70,
          easing: "cubicBezier(0.16, 1, 0.3, 1)",
        });
      });
    });
  }, { threshold: 0.18, rootMargin: "0px 0px -8% 0px" });

  items.forEach((el) => io.observe(el));
  return () => io.disconnect();
}

export function format(el, v) {
  const decimals = Number(el.dataset.decimals || 0);
  const unit = el.dataset.unit || "";
  const n = Number.isFinite(v) ? v : Number(el.dataset.count || 0);
  return n.toLocaleString("zh-CN", {
    minimumFractionDigits: decimals, maximumFractionDigits: decimals,
  }) + unit;
}

/* 视图切换：整块内容从下方抬起 */
export function enter(el) {
  if (reduced()) return;
  window.anime({
    targets: el,
    opacity: [0, 1],
    translateY: [18, 0],
    duration: 620,
    easing: "cubicBezier(0.16, 1, 0.3, 1)",
  });
}
