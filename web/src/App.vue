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

      <button class="md-btn md-btn--text theme-toggle" @click="toggleTheme">
        {{ theme === 'dark' ? '切到亮色' : '切到暗色' }}
      </button>
    </aside>

    <main class="content" tabindex="-1">
      <div v-if="demo" class="demo-banner" role="status">
        <span class="md-chip md-chip--warn">演示模式</span>
        <span>数据由 mock 生成，不是真实测量。</span>
      </div>
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 232px minmax(0, 1fr);
  min-height: 100vh;
  background: var(--md-surface);
}

.rail {
  display: flex;
  flex-direction: column;
  gap: var(--space-5);
  padding: var(--space-5) var(--space-3);
  border-right: 1px solid var(--md-surface-container-highest);
  background: var(--md-surface-container-low);
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
  display: flex;
  align-items: center;
  height: 44px;
  padding: 0 var(--space-4);
  border-radius: var(--md-shape-full);
  color: var(--md-on-surface-variant);
  font: var(--md-label-large);
  transition: background-color var(--md-dur-short) var(--md-ease);
}
.nav-item:hover {
  background: color-mix(in srgb, var(--md-on-surface) 8%, transparent);
}
.nav-item--active {
  background: var(--md-card-bg);
  border: 1px solid var(--md-card-border);
  color: var(--md-on-surface-variant);
}

.theme-toggle {
  margin-top: auto;
  justify-content: flex-start;
}

.content {
  padding: var(--space-5) var(--space-6) var(--space-6);
  min-width: 0;
}

.demo-banner {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-4);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--md-shape-sm);
  background: var(--md-card-bg);
  border: 1px solid var(--md-card-border);
  color: var(--md-on-surface-variant);
  font: var(--md-body-small);
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
