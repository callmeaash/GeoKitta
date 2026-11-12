<script setup>
import { setTab, store } from '../store.js'
import Icon from './Icon.vue'

const TABS = [
  { id: 'details', label: 'Details', icon: 'info' },
  { id: 'select', label: 'Select', icon: 'select' },
  { id: 'buffer', label: 'Buffer', icon: 'buffer' },
  { id: 'measure', label: 'Measure', icon: 'ruler' },
  { id: 'layers', label: 'Layers', icon: 'layers' }
]
</script>

<template>
  <nav class="rail" aria-label="Tools">
    <button v-for="t in TABS" :key="t.id" :class="{ active: store.tab === t.id }"
            :aria-pressed="store.tab === t.id" @click="setTab(t.id)">
      <Icon :name="t.icon" :size="20" /><span>{{ t.label }}</span>
    </button>
  </nav>
</template>
