<script setup>
import Icon from '../Icon.vue'

defineProps({ checks: { type: Array, default: () => [] }, busy: Boolean })
const CLASS = { pass: 'ok', warn: 'warn', fail: 'err' }
const ICON = { pass: 'checkCircle', warn: 'alert', fail: 'xCircle' }
</script>

<template>
  <ul class="checklist" aria-live="polite">
    <li v-for="c in checks" :key="c.id" :class="CLASS[c.status]">
      <Icon :name="ICON[c.status]" :size="18" />
      <div><strong>{{ c.title }}</strong><span>{{ c.detail }}</span></div>
    </li>
    <li v-if="!checks.length"><Icon name="info" :size="18" />
      <div><span>{{ busy ? 'Checking…' : 'Enter at least 3 corner points to validate the boundary.' }}</span></div></li>
  </ul>
</template>
