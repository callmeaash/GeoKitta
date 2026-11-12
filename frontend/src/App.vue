<script setup>
import { onMounted, ref } from 'vue'
import { getHealth } from './api.js'

const status = ref('checking')

onMounted(async () => {
  try {
    const health = await getHealth()
    status.value = health.status === 'ok' ? 'ok' : 'error'
  } catch {
    status.value = 'error'
  }
})
</script>

<template>
  <main class="start">
    <img src="/brand/svg/geokitta-logo-horizontal.svg" alt="GeoKitta" class="logo">
    <p class="lead">Cadastral information system for Kathmandu. Demonstration with synthetic data.</p>
    <p class="status" :class="status" role="status">
      <span class="dot"></span>
      <template v-if="status === 'checking'">Checking the API…</template>
      <template v-else-if="status === 'ok'">API connected</template>
      <template v-else>API not reachable — start the backend on port 8000</template>
    </p>
  </main>
</template>

<style scoped>
.start {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 24px;
  text-align: center;
}
.logo { height: 64px; }
.lead { margin: 4px 0 8px; color: var(--color-muted); max-width: 420px; }
.status {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 0;
  padding: 6px 12px;
  border-radius: 999px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  font-weight: 500;
}
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--color-muted); }
.status.ok { color: var(--color-success); }
.status.ok .dot { background: var(--color-success); }
.status.error { color: var(--color-error); }
.status.error .dot { background: var(--color-error); }
</style>
