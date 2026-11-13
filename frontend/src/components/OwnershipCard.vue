<script setup>
import { ref, watch } from 'vue'
import { request } from '../api.js'
import { bsText, label, shareLabel, txnLabel } from '../utils/format.js'
import Icon from './Icon.vue'
import RokkaDialog from './officer/RokkaDialog.vue'

const props = defineProps({ parcelId: { type: Number, required: true } })
const data = ref(null)
const error = ref('')
const releasing = ref(null)
const emit = defineEmits(['changed'])

async function released() {
  releasing.value = null
  await load(props.parcelId)
  emit('changed')
}

async function load(id) {
  data.value = null
  error.value = ''
  try {
    data.value = await request(`/api/officer/parcels/${id}/ownership`)
  } catch (e) {
    error.value = e.status === 401 ? 'Your session has ended. Sign in again to see owners.' : e.message
  }
}
watch(() => props.parcelId, load, { immediate: true })
</script>

<template>
  <div class="ownership">
    <div class="section-title"><Icon name="users" :size="14" /> Owners <span class="tag tag-teal">Officer view</span></div>
    <p v-if="error" class="note">{{ error }}</p>
    <p v-else-if="!data" class="note">Loading owners…</p>
    <template v-else>
      <div v-for="r in data.rokka" :key="r.start_date + r.requested_by_name" class="card card-error">
        <Icon name="lock" :size="16" />
        <div><strong>Rokka since {{ bsText(r.start_date) }}</strong>
          <span>{{ r.requested_by_name }} ({{ label(r.requested_by_type) }}){{ r.reason ? ` — ${r.reason}` : '' }}.
            Transfers are blocked until fukuwa.</span>
          <button class="link" style="margin-top: 4px" @click="releasing = r">Release (fukuwa)</button></div>
      </div>
      <ul class="owner-list">
        <li v-for="o in data.current" :key="o.owner_id">
          <RouterLink class="link" :to="`/officer/owners/${o.owner_id}`">{{ o.full_name }}</RouterLink>
          <span class="share">{{ shareLabel(o.share) }}</span>
          <span class="sub">{{ o.lin }} · since {{ bsText(o.valid_from) }}{{ o.txn_type ? ` · ${txnLabel(o.txn_type)}` : '' }}</span>
        </li>
      </ul>
      <details v-if="data.history.length" class="history">
        <summary>Ownership history ({{ data.history.length }})</summary>
        <ul class="owner-list past">
          <li v-for="o in data.history" :key="o.owner_id + o.valid_from">
            <RouterLink class="link" :to="`/officer/owners/${o.owner_id}`">{{ o.full_name }}</RouterLink>
            <span class="share">{{ shareLabel(o.share) }}</span>
            <span class="sub">{{ bsText(o.valid_from) }} → {{ bsText(o.valid_to) }}{{ o.txn_type ? ` · ${txnLabel(o.txn_type)}` : '' }}</span>
          </li>
        </ul>
      </details>
    </template>
    <RokkaDialog v-if="releasing" mode="release" :rokka="releasing" :parcel-id="parcelId" @done="released" @close="releasing = null" />
  </div>
</template>

<style scoped>
.ownership { margin-bottom: 10px; }
.section-title { display: flex; align-items: center; gap: 6px; margin-top: 4px; }
.section-title .tag { margin-left: auto; height: 20px; font-size: 11px; }
.owner-list { list-style: none; margin: 0 0 8px; padding: 0; border: 1px solid var(--color-border); border-radius: var(--radius-md); }
.owner-list li { display: grid; grid-template-columns: 1fr auto; gap: 2px 8px; padding: 9px 12px; border-bottom: 1px solid var(--color-border); font-size: 13px; }
.owner-list li:last-child { border-bottom: none; }
.owner-list .share { font-weight: 600; color: var(--color-heading); font-variant-numeric: tabular-nums; }
.owner-list .sub { grid-column: 1 / -1; font-size: 12px; color: var(--color-muted); }
.owner-list.past li { background: var(--color-bg); }
.history summary { cursor: pointer; font-size: 13px; font-weight: 500; color: var(--color-primary); margin: 4px 0 8px; }
</style>
