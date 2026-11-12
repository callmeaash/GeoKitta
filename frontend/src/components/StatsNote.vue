<script setup>
defineProps({ stats: { type: Object, default: null } })
</script>

<template>
  <p v-if="stats" class="stats-note" title="How the linear quadtree answered this query">
    Linear quadtree: {{ stats.rows_read }} index rows read, {{ stats.checked || stats.candidates }} parcels checked
    exactly, {{ stats.ms }} ms
  </p>
</template>
