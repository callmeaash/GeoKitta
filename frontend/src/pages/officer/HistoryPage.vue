<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { request } from '../../api.js'
import Icon from '../../components/Icon.vue'
import PreviewMap from '../../components/officer/PreviewMap.vue'
import { fmt, label, shareLabel, txnLabel } from '../../utils/format.js'

const route = useRoute()
const id = Number(route.params.id)
const data = ref(null)
const own = ref(null)
const error = ref('')
const tab = ref('timeline')
const version = ref(null) // boundary version shown next to the current one

onMounted(async () => {
  try {
    ;[data.value, own.value] = await Promise.all([request(`/api/officer/parcels/${id}/history`),
      request(`/api/officer/parcels/${id}/ownership`)])
    version.value = data.value.boundaries[1]?.version ?? null
  } catch (e) {
    error.value = e.message
  }
})

const DOT = { rokka: ['lock', '#B45309'], fukuwa: ['unlock', '#15803D'], boundary_update: ['edit', '#1D4ED8'],
  split: ['split', '#7C3AED'], registration: ['plus', '#0F766E'], samsodhan: ['file', '#64748B'] }
const dot = kind => DOT[kind] || ['transfer', '#0F766E']
const printPage = () => window.print()
const periods = computed(() => own.value ? [...own.value.current, ...own.value.history] : [])
const current = computed(() => data.value?.boundaries[0])
const older = computed(() => data.value?.boundaries.find(b => b.version === version.value))
const shapes = computed(() => [
  ...(older.value && older.value !== current.value ? [{ geometry: older.value.geometry, kind: 'old' }] : []),
  ...(current.value ? [{ geometry: current.value.geometry, kind: 'new' }] : [])
])
</script>

<template>
  <main class="page">
    <div class="page-head">
      <div>
        <div class="crumbs"><RouterLink to="/officer">Dashboard</RouterLink><Icon name="chevronRight" :size="12" />
          <RouterLink to="/officer/parcels">Update parcel</RouterLink><Icon name="chevronRight" :size="12" />
          <RouterLink :to="`/officer/parcels/${id}`">Kitta {{ data?.parcel.kitta || '…' }}</RouterLink><Icon name="chevronRight" :size="12" />History</div>
        <h1 class="page-title">Kitta {{ data?.parcel.kitta || '…' }} — History</h1>
        <p v-if="data" class="page-sub">Ward {{ data.parcel.ward }} · PIN {{ data.parcel.pin }} ·
          <span class="status" :class="data.parcel.status === 'active' ? 'st-green' : 'st-grey'">{{ label(data.parcel.status) }}</span></p>
      </div>
      <div class="head-actions">
        <RouterLink class="btn btn-secondary" :to="{ path: '/', hash: `#parcel=${id}` }"><Icon name="map" :size="16" />Open on map</RouterLink>
        <button class="btn btn-secondary" @click="printPage"><Icon name="file" :size="16" />Print</button>
      </div>
    </div>
    <div v-if="error" class="banner banner-error"><Icon name="alert" :size="16" /><span>{{ error }}</span></div>

    <section v-if="data" class="box">
      <div class="tabs" role="tablist">
        <button v-for="t in [['timeline', 'Timeline', data.timeline.length], ['ownership', 'Ownership', periods.length],
                             ['boundaries', 'Boundaries', data.boundaries.length],
                             ['lineage', 'Lineage', data.lineage.parents.length + data.lineage.children.length]]"
                :key="t[0]" class="tab" :class="{ on: tab === t[0] }" role="tab" :aria-selected="tab === t[0]" @click="tab = t[0]">
          {{ t[1] }} <span class="count">{{ t[2] }}</span></button>
      </div>

      <ol v-if="tab === 'timeline'" class="timeline">
        <li v-for="(e, n) in data.timeline" :key="n" class="tl-item">
          <span class="tl-dot" :style="{ background: dot(e.kind)[1] }"><Icon :name="dot(e.kind)[0]" :size="14" /></span>
          <div class="tl-date">{{ e.date || '—' }}</div>
          <div class="tl-title">{{ e.title === 'Ownership transfer' ? `Ownership transfer — ${txnLabel(e.kind)}` : e.title }}</div>
          <div class="tl-desc">{{ e.detail }}</div>
          <div class="tl-meta"><span class="tag">Case {{ e.case_id }}</span><span v-if="e.deed_ref" class="tag">{{ e.deed_ref }}</span>
            <span class="tag">{{ label(e.status) }} by {{ e.officer }}</span></div>
        </li>
        <li v-if="!data.timeline.length" class="tl-item"><div class="tl-desc muted">No cases recorded for this parcel.</div></li>
      </ol>

      <div v-else-if="tab === 'ownership'" class="tbl-wrap">
        <table class="tbl">
          <thead><tr><th>Owner</th><th>Share</th><th>From</th><th>To</th><th>Deed</th></tr></thead>
          <tbody>
            <tr v-for="o in periods" :key="o.owner_id + o.valid_from">
              <td><RouterLink class="link" :to="`/officer/owners/${o.owner_id}`">{{ o.full_name }}</RouterLink><span class="muted num"> · LIN {{ o.lin }}</span></td>
              <td class="num">{{ shareLabel(o.share) }}</td><td class="num">{{ o.valid_from }}</td>
              <td class="num"><span v-if="!o.valid_to" class="status st-green">Current</span><template v-else>{{ o.valid_to }}</template></td>
              <td>{{ o.txn_type ? txnLabel(o.txn_type) : '—' }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-else-if="tab === 'boundaries'" class="grid-2">
        <div class="tbl-wrap">
          <table class="tbl">
            <thead><tr><th>Version</th><th>Area</th><th>Valid from</th><th>Valid to</th><th></th></tr></thead>
            <tbody>
              <tr v-for="b in data.boundaries" :key="b.version">
                <td>Version {{ b.version }}</td><td class="num">{{ fmt(b.area_m2) }} m²</td>
                <td class="num">{{ String(b.valid_from).slice(0, 10) }}</td>
                <td class="num"><span v-if="!b.valid_to" class="status st-green">Current</span><template v-else>{{ String(b.valid_to).slice(0, 10) }}</template></td>
                <td><button v-if="b.valid_to" class="link" @click="version = b.version">{{ version === b.version ? 'Shown' : 'Compare' }}</button></td>
              </tr>
            </tbody>
          </table>
          <p v-if="data.boundaries.length === 1" class="note">The boundary has not changed since the parcel was created.</p>
        </div>
        <PreviewMap :shapes="shapes" :height="340">
          <span><i class="sw sw-new"></i>Current</span><span v-if="older && older !== current"><i class="sw sw-old"></i>Version {{ older.version }}</span>
        </PreviewMap>
      </div>

      <div v-else class="lineage-wrap">
        <p class="note" style="margin-top: 0">Parent and child parcels created by splits (kitta kaat).</p>
        <div class="lineage">
          <div v-if="data.lineage.parents.length" class="lin-col">
            <RouterLink v-for="p in data.lineage.parents" :key="p.id" class="lin-node retired" :to="`/officer/parcels/${p.id}/history`">
              <strong>Kitta {{ p.kitta }}</strong><span>{{ p.pin }} · {{ label(p.status) }}</span></RouterLink>
          </div>
          <span v-if="data.lineage.parents.length" class="lin-arrow"><Icon name="arrowRight" :size="20" /></span>
          <div class="lin-col">
            <div class="lin-node cur"><strong>Kitta {{ data.parcel.kitta }}</strong><span>This parcel · {{ label(data.parcel.status) }}</span></div>
            <RouterLink v-for="s in data.lineage.siblings" :key="s.id" class="lin-node" :to="`/officer/parcels/${s.id}/history`">
              <strong>Kitta {{ s.kitta }}</strong><span>Sibling · {{ label(s.status) }}</span></RouterLink>
          </div>
          <template v-if="data.lineage.children.length">
            <span class="lin-arrow"><Icon name="arrowRight" :size="20" /></span>
            <div class="lin-col">
              <RouterLink v-for="c in data.lineage.children" :key="c.id" class="lin-node" :to="`/officer/parcels/${c.id}/history`">
                <strong>Kitta {{ c.kitta }}</strong><span>Child · {{ label(c.status) }}</span></RouterLink>
            </div>
          </template>
        </div>
        <p v-if="!data.lineage.parents.length && !data.lineage.children.length" class="note">This parcel has not been split and was not created by a split.</p>
      </div>
    </section>
  </main>
</template>

<style scoped>
.lin-node { text-decoration: none; }
@media print {
  .head-actions, .tabs { display: none; }
}
</style>
