<script setup>
import { computed, ref, watch } from 'vue'
import { bsToAd, formatBs, parseBs } from '../utils/bs.js'

/** Date entry in Bikram Sambat (YYYY-MM-DD); the model holds the AD date that is stored. */
const model = defineModel({ type: String, default: '' }) // AD "YYYY-MM-DD"
const props = defineProps({
  id: { type: String, default: undefined },
  min: { type: String, default: null }, // AD bounds
  max: { type: String, default: null }
})

const text = ref(formatBs(model.value))
let typed = model.value // the value this input set itself; only outside changes rewrite the text
watch(model, ad => { if (ad !== typed && ad) text.value = formatBs(ad) })

const problem = computed(() => {
  if (!text.value.trim()) return 'Enter the date in BS, e.g. 2083-07-28.'
  const b = parseBs(text.value)
  if (!b) return 'Not a valid BS date (YYYY-MM-DD).'
  const ad = bsToAd(b.year, b.month, b.day)
  if (props.min && ad < props.min) return `Must be on or after ${formatBs(props.min)} BS.`
  if (props.max && ad > props.max) return `Must be on or before ${formatBs(props.max)} BS.`
  return ''
})

function onInput() {
  const b = parseBs(text.value)
  typed = b && !problem.value ? bsToAd(b.year, b.month, b.day) : ''
  model.value = typed
}
</script>

<template>
  <div>
    <div class="input-wrap">
      <input :id="id" v-model="text" class="num" type="text" inputmode="numeric" placeholder="2083-07-28"
             :aria-invalid="!!problem" @input="onInput">
      <span class="suffix">BS</span>
    </div>
    <span class="hint" :class="{ bad: problem }">{{ problem || `${model} AD` }}</span>
  </div>
</template>

<style scoped>
.hint { display: block; margin-top: 6px; }
.hint.bad { color: var(--color-error); }
</style>
