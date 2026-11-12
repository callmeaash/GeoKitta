<script setup>
import { computed } from 'vue'
import { ICONS } from '../icons.js'

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 20 }
})
const paths = computed(() => ICONS[props.name] || '')
</script>

<template>
  <svg :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
       stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" v-html="paths"></svg>
</template>
