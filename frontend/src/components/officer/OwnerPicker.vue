<script setup>
import { computed, ref } from 'vue'
import { request } from '../../api.js'
import { sumShares } from '../../utils/survey.js'
import Icon from '../Icon.vue'

/** Owners of a new parcel with exact shares, e.g. 1/2 + 1/2. Owners are found with the fuzzy owner search. */
const owners = defineModel({ type: Array, required: true }) // [{ id, lin, full_name, share }]
const q = ref('')
const hits = ref([])
let timer

function search() {
  clearTimeout(timer)
  if (q.value.trim().length < 2) {
    hits.value = []
    return
  }
  timer = setTimeout(async () => {
    try {
      hits.value = (await request(`/api/officer/owners?q=${encodeURIComponent(q.value.trim())}`)).slice(0, 8)
    } catch {
      hits.value = []
    }
  }, 250)
}

function add(h) {
  if (!owners.value.some(o => o.id === h.id)) {
    const next = [...owners.value, { id: h.id, lin: h.lin, full_name: h.full_name, share: '' }]
    if (next.length === 1) next[0].share = '1'
    owners.value = next
  }
  q.value = ''
  hits.value = []
}
function remove(id) { owners.value = owners.value.filter(o => o.id !== id) }

const total = computed(() => sumShares(owners.value.map(o => o.share)))
const totalText = computed(() => (total.value ? (total.value[1] === 1 ? String(total.value[0]) : total.value.join('/')) : '?'))
const ok = computed(() => owners.value.length && total.value && total.value[0] === total.value[1])
defineExpose({ ok })
</script>

<template>
  <div>
    <div class="search owner-search">
      <span class="s-icon"><Icon name="search" :size="16" /></span>
      <input v-model="q" type="search" placeholder="Find owner by name or LIN…" autocomplete="off" @input="search">
      <div class="dropdown" :class="{ open: hits.length }">
        <div v-for="h in hits" :key="h.id" class="dd-item" @mousedown.prevent="add(h)">
          <span class="dd-icon"><Icon name="user" :size="16" /></span>{{ h.full_name }}
          <span class="dd-type">{{ h.date_of_birth || h.owner_type }}</span><span class="meta">{{ h.lin }}</span>
        </div>
      </div>
    </div>
    <table v-if="owners.length" class="tbl" style="margin-top: 10px">
      <thead><tr><th>Owner</th><th>LIN</th><th style="width: 110px">Share</th><th></th></tr></thead>
      <tbody>
        <tr v-for="o in owners" :key="o.id">
          <td>{{ o.full_name }}</td><td class="num">{{ o.lin }}</td>
          <td><input v-model="o.share" class="input num" placeholder="1/2" :aria-label="`Share of ${o.full_name}`"></td>
          <td><button class="icon-btn" type="button" :aria-label="`Remove ${o.full_name}`" @click="remove(o.id)"><Icon name="x" :size="16" /></button></td>
        </tr>
      </tbody>
    </table>
    <p class="hint" style="margin-top: 8px">
      <template v-if="!owners.length">Add at least one owner. Register new owners first under Owners.</template>
      <template v-else>Shares add up to <strong :style="{ color: ok ? 'var(--color-success)' : 'var(--color-error)' }">{{ totalText }}</strong>
        {{ ok ? '' : '(must be exactly 1)' }}</template>
    </p>
  </div>
</template>

<style scoped>
.owner-search { max-width: none; margin: 0; }
</style>
