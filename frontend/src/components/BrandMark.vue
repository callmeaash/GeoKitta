<script setup>
/** The GeoKitta app icon ("Kitta Pin · Cut") from the brand kit. */
defineProps({ size: { type: Number, default: 32 } })
</script>

<template>
  <img src="/brand/svg/geokitta-icon.svg" alt="" :width="size" :height="size" class="brand-icon" aria-hidden="true">
</template>

<style scoped>
.brand-icon { display: block; flex: none; }
</style>
