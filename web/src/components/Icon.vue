<script setup>
import { computed } from 'vue'
import { ICONS } from '../lib/icons'

const props = defineProps({
  name: { type: String, required: true },
  size: { type: Number, default: 24 },
  filled: { type: Boolean, default: false },
})

// 名字来自 scripts/icons.py 生成的表，拼错时页面留空而不是瞎猜一个图标
const glyph = computed(() => ICONS[props.name] ?? '')
if (!(props.name in ICONS)) console.warn(`未收录的图标：${props.name}，重跑 scripts/icons.py`)
</script>

<template>
  <span
    class="ms-icon"
    aria-hidden="true"
    :style="{
      fontSize: `${size}px`,
      fontVariationSettings: `'FILL' ${filled ? 1 : 0}, 'wght' 400, 'GRAD' 0, 'opsz' 24`,
    }"
    >{{ glyph }}</span
  >
</template>
