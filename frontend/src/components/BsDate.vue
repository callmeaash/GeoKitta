<script setup>
import { computed } from 'vue'
import { formatBs } from '../utils/bs.js'

/** A stored (AD) date shown in Bikram Sambat, with the AD date on hover or underneath. */
const props = defineProps({
  date: { type: String, default: null },
  showAd: { type: Boolean, default: false }
})
const ad = computed(() => (props.date ? String(props.date).slice(0, 10) : ''))
const bs = computed(() => formatBs(ad.value))
</script>

<template>
  <span v-if="!ad">—</span>
  <span v-else-if="!bs" class="num">{{ ad }} <small class="muted">AD</small></span>
  <span v-else class="num bs-date" :title="`${ad} AD`">{{ bs }} <small class="muted">BS</small><small
    v-if="showAd" class="muted ad"> · {{ ad }} AD</small></span>
</template>

<style scoped>
.bs-date { white-space: nowrap; }
.bs-date small { font-weight: 400; }
</style>
