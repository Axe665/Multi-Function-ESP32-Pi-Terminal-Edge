<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { routes } from './router'
import { useTheme } from './lib/theme'
import BrandMark from './components/BrandMark.vue'
import Icon from './components/Icon.vue'

const route = useRoute()
const { theme, toggleTheme } = useTheme()

const navItems = routes
  .filter((r) => r.meta?.nav && !r.path.includes(':'))
  .map((r) => ({ to: r.path, label: r.meta.nav, icon: r.meta.icon }))

const activeNav = computed(() => route.meta?.nav)
const title = computed(() => route.meta?.title ?? '')

// 演示模式提示：数据由 mock 生成（文档 §8.5）
const demo = ref(false)
onMounted(async () => {
  try {
    const r = await fetch('/api/v1/health')
    if (r.ok) demo.value = Boolean((await r.json()).demo)
  } catch { /* 自检不可达时不挂提示 */ }
})
</script>

<template>
  <div class="shell">
    <nav class="rail" aria-label="主导航">
      <RouterLink to="/" class="rail-brand" aria-label="Modular Terminal 边节点">
        <BrandMark />
      </RouterLink>

      <RouterLink
        v-for="item in navItems"
        :key="item.to"
        :to="item.to"
        class="md-rail-item"
        :class="{ 'md-rail-item--active': activeNav === item.label }"
        :aria-current="activeNav === item.label ? 'page' : undefined"
      >
        <Icon :name="item.icon" :filled="activeNav === item.label" />
        <span>{{ item.label }}</span>
      </RouterLink>

      <span class="rail-spacer"></span>

      <button
        class="md-btn md-btn--icon"
        :aria-label="theme === 'dark' ? '切到亮色' : '切到暗色'"
        :title="theme === 'dark' ? '切到亮色' : '切到暗色'"
        @click="toggleTheme"
      >
        <Icon :name="theme === 'dark' ? 'light_mode' : 'dark_mode'" />
      </button>
    </nav>

    <div class="main">
      <header class="appbar">
        <span class="appbar-title" data-page-title>{{ title }}</span>
        <span v-if="demo" class="md-chip" role="status">演示数据</span>
        <div class="appbar-actions">
          <slot name="appbar"></slot>
        </div>
      </header>

      <main class="content" tabindex="-1">
        <RouterView />
      </main>
    </div>
  </div>
</template>
