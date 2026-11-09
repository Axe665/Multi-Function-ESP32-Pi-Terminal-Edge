<script setup>
defineProps({ title: String, sub: String })
</script>

<template>
  <header class="head">
    <div>
      <h1>{{ title }}</h1>
      <p v-if="sub" class="sub">{{ sub }}</p>
    </div>
    <div class="actions"><slot /></div>
  </header>
</template>

<style scoped>
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
  flex-wrap: wrap;
}
.sub {
  margin-top: var(--space-1);
  font: var(--md-body-medium);
  color: var(--md-on-surface-variant);
  max-width: 76ch;
}
.actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
}
</style>
