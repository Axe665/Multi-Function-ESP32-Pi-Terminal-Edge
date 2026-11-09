<script setup>
import { useSnack } from './useSnack'
const { text } = useSnack()
</script>

<template>
  <div v-if="text" class="md-snackbar" role="status" aria-live="polite">{{ text }}</div>
</template>
