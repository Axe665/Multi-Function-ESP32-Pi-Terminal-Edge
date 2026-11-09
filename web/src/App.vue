<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { useTheme } from './lib/theme'
import BrandMark from './components/BrandMark.vue'

const route = useRoute()
const drawer = ref(false)

const navItems = [
  { to: '/', label: '总览' },
  { to: '/devices', label: '设备' },
  { to: '/analysis', label: '分析' },
  { to: '/access', label: '接入' },
  { to: '/settings', label: '设置' },
]

const active = computed(() => {
  const p = route.path
  if (p.startsWith('/devices')) return '/devices'
  return p
})

// 演示模式横幅：数据由 mock 生成（文档 §8.5）
const demo = ref(false)
onMounted(async () => {
  try {
    const r = await fetch('/api/v1/health')
    if (r.ok) demo.value = Boolean((await r.json()).demo)
  } catch { /* 自检不可达时不挂横幅 */ }
})

const { theme, toggleTheme } = useTheme()
</script>

<template>
  <div class="shell">
    <aside class="rail" aria-label="主导航">
      <div class="brand">
        <BrandMark />
        <div>
          <div class="brand-name">Modular Terminal</div>
          <div class="brand-sub">边节点</div>
        </div>
      </div>

      <nav class="nav">
        <RouterLink
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-item"
          :class="{ 'nav-item--active': active === item.to }"
          :aria-current="active === item.to ? 'page' : undefined"
        >
          {{ item.label }}
        </RouterLink>
      </nav>

      <p v-if="demo" class="demo-note" role="status">
        <span class="demo-dot" aria-hidden="true"></span>
        <span>演示数据，mock 生成</span>
      </p>

      <button class="md-btn md-btn--text theme-toggle" @click="toggleTheme">
        {{ theme === 'dark' ? '切到亮色' : '切到暗色' }}
      </button>
    </aside>

    <main class="content" tabindex="-1">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 200px minmax(0, 1fr);
  min-height: 100vh;
  background: var(--md-surface);
}

.rail {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding: var(--space-5) var(--space-3);
  border-right: 1px solid var(--md-card-border);
  background: var(--md-surface);
  position: sticky;
  top: 0;
  height: 100vh;
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: 0 var(--space-2);
}
.brand-name {
  font: var(--md-title-small);
  color: var(--md-on-surface);
}
.brand-sub {
  font: var(--md-label-small);
  color: var(--md-on-surface-variant);
}

.nav {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  height: 36px;
  padding: 0 var(--space-3);
  border-radius: var(--md-shape-sm);
  color: var(--md-on-surface-variant);
  font: var(--md-label-large);
  transition: background-color var(--md-dur-short) var(--md-ease);
}
.nav-item:hover {
  background: color-mix(in srgb, var(--md-on-surface) 8%, transparent);
}
.nav-item--active {
  background: var(--md-surface-container-high);
  color: var(--md-on-surface);
  font-weight: 500;
}
.nav-item--active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  border-radius: 2px;
  background: var(--md-primary);
}

.theme-toggle {
  margin-top: auto;
  justify-content: flex-start;
}

.content {
  padding: var(--space-5) var(--space-6) var(--space-6);
  min-width: 0;
}

.demo-note {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 0 var(--space-3);
  color: var(--md-on-surface-variant);
  font: var(--md-body-small);
}
.demo-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--md-notice);
  flex: none;
}

@media (max-width: 900px) {
  .shell {
    grid-template-columns: minmax(0, 1fr);
  }
  .rail {
    position: static;
    height: auto;
    flex-direction: row;
    align-items: center;
    gap: var(--space-3);
    flex-wrap: wrap;
    padding: var(--space-2) var(--space-3);
    border-right: 0;
    border-bottom: 1px solid var(--md-surface-container-highest);
  }
  .brand {
    padding: 0;
    display: none;
  }
  .nav {
    flex-direction: row;
    gap: var(--space-1);
  }
  .nav-item {
    height: 40px;
    padding: 0 var(--space-3);
    white-space: nowrap;
  }
  .theme-toggle {
    margin-top: 0;
    margin-left: auto;
    padding-right: var(--space-2);
  }
  .content {
    padding: var(--space-4);
  }
}
</style>
