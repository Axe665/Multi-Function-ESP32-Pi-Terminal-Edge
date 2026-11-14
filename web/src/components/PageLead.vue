<script setup>
// 页面首行：一句口径说明 + 页面级动作。页面名在顶栏，这里不重复标题。
defineProps({ sub: { type: String, default: '' } })
</script>

<template>
  <div class="lead">
    <p v-if="sub" class="sub">{{ sub }}</p>
    <div class="actions"><slot /></div>
  </div>
</template>

<style scoped>
.lead {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-4);
  max-width: var(--content-max);
  margin: 0 auto var(--space-4);
  flex-wrap: wrap;
}
.sub {
  font: var(--md-body-medium);
  color: var(--md-on-surface-variant);
  max-width: 90ch;
}
.actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-left: auto;
  flex-wrap: wrap;
}
</style>
