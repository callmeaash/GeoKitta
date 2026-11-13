<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { request } from '../../api.js'
import Icon from '../../components/Icon.vue'
import PreviewMap from '../../components/officer/PreviewMap.vue'
import { fmt, label } from '../../utils/format.js'

const route = useRoute()
const router = useRouter()
const STATUS = [['open', 'Open'], ['resolved', 'Resolved'], ['dispute', 'Disputes']]
const TYPES = [['overlap', 'Overlap'], ['sliver', 'Sliver'], ['area_mismatch', 'Area mismatch'], ['invalid', 'Invalid geometry']]
const status = ref(route.query.status || 'open')
const type = ref(route.query.type || null)
const list = ref(null)
const selected = ref(null)
const note = ref('')
const saving = ref(false)
const error = ref('')

async function loadList(keep = false) {
  const params = new URLSearchParams({ status: status.value, limit: '100' })
  if (type.value) params.set('issue_type', type.value)
  list.value = await request(`/api/officer/issues?${params}`)
  if (!keep || !list.value.issues.some(i => i.id === selected.value?.id)) {
    const first = list.value.issues[0]
    selected.value = first ? await request(`/api/officer/issues/${first.id}`) : null
  }
  router.replace({ query: { status: status.value, ...(type.value ? { type: type.value } : {}) } })
}

async function open(issue) {
  selected.value = await request(`/api/officer/issues/${issue.id}`)
  note.value = selected.value.note || ''
  error.value = ''
}

async function review(next) {
  error.value = ''
  saving.value = true
  try {
    await request(`/api/officer/issues/${selected.value.id}/review`, {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: next, note: note.value.trim() || null })
    })
    note.value = ''
    await loadList()
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}

onMounted(() => loadList())
watch([status, type], () => loadList())

const shapes = computed(() => !selected.value ? [] : [
  { geometry: selected.value.parcel.geometry, kind: 'issueA' },
  ...(selected.value.other ? [{ geometry: selected.value.other.geometry, kind: 'issueB' }] : []),
  ...(selected.value.overlap_geometry ? [{ geometry: selected.value.overlap_geometry, kind: 'overlap' }] : [])
])
const typeLabel = t => (TYPES.find(x => x[0] === t) || [t, label(t)])[1]
const when = iso => new Date(iso).toLocaleDateString('en-CA')
</script>

<template>
  <main class="page">
    <div class="page-head">
      <div>
        <div class="crumbs"><RouterLink to="/officer">Dashboard</RouterLink><Icon name="chevronRight" :size="12" />Issues</div>
        <h1 class="page-title">Issue review</h1>
        <p class="page-sub">Problems found by validation when parcels are saved and by the city-wide scan. Large overlaps may be genuine boundary disputes.</p>
      </div>
    </div>

    <div class="grid-side">
      <section class="box flush">
        <div style="padding: 6px 16px 0">
          <div class="tabs" role="tablist" style="margin-bottom: 12px">
            <button v-for="s in STATUS" :key="s[0]" class="tab" :class="{ on: status === s[0] }" role="tab" @click="status = s[0]">
              {{ s[1] }} <span class="count">{{ list?.counts[s[0]] ?? '…' }}</span></button>
          </div>
          <div class="chips" style="margin-bottom: 12px">
            <button v-for="t in TYPES" :key="t[0]" class="chip" :class="{ on: type === t[0] }" @click="type = type === t[0] ? null : t[0]">
              {{ t[1] }} <span class="muted">{{ list?.types[t[0]] ?? 0 }}</span></button>
          </div>
        </div>
        <div style="border-top: 1px solid var(--color-border); max-height: 640px; overflow-y: auto">
          <div v-for="i in list?.issues || []" :key="i.id" class="issue-row" :class="{ active: selected?.id === i.id }" @click="open(i)">
            <span class="issue-ic" :class="i.severity === 'error' ? 'red' : 'amber'"><Icon name="alert" :size="16" /></span>
            <div style="min-width: 0">
              <strong>{{ typeLabel(i.type) }} — Kitta {{ i.parcel.kitta }}<template v-if="i.other"> &amp; {{ i.other.kitta }}</template></strong>
              <span>Ward {{ i.parcel.ward }} · {{ i.summary }}</span>
            </div>
            <span class="when">{{ when(i.found_at) }}</span>
          </div>
          <p v-if="list && !list.issues.length" class="note" style="padding: 16px">No {{ status }} issues{{ type ? ` of this type` : '' }}.</p>
          <p v-if="list && list.total > list.issues.length" class="note" style="padding: 0 16px 16px">Showing {{ list.issues.length }} of {{ list.total }}.</p>
        </div>
      </section>

      <div class="stack">
        <section class="box">
          <PreviewMap :shapes="shapes" :height="380">
            <template v-if="selected"><span><i class="sw sw-issue"></i>Kitta {{ selected.parcel.kitta }}</span>
              <span v-if="selected.other"><i class="sw sw-warn"></i>Kitta {{ selected.other.kitta }}</span>
              <span v-if="selected.overlap_geometry"><i class="sw sw-overlap"></i>Overlap</span></template>
          </PreviewMap>
        </section>
        <section v-if="selected" class="box">
          <div class="box-head">
            <div><h2 class="box-title">{{ typeLabel(selected.type) }} — Kitta {{ selected.parcel.kitta }}<template v-if="selected.other"> &amp; {{ selected.other.kitta }}</template></h2>
              <p class="box-sub">Found {{ when(selected.found_at) }} by {{ selected.source === 'scan' ? 'the city-wide scan' : 'validation on save' }}</p></div>
            <span class="status" :class="selected.status === 'open' ? 'st-amber' : selected.status === 'resolved' ? 'st-green' : 'st-red'">{{ label(selected.status) }}</span>
          </div>
          <dl class="kv wide">
            <dt>Parcel</dt><dd><RouterLink class="link" :to="`/officer/parcels/${selected.parcel.id}`">{{ selected.parcel.pin }}</RouterLink>
              <span class="sub">Registered {{ fmt(selected.parcel.registered_m2) }} m² · boundary {{ fmt(selected.parcel.boundary_m2) }} m²</span></dd>
            <template v-if="selected.other"><dt>Other parcel</dt><dd><RouterLink class="link" :to="`/officer/parcels/${selected.other.id}`">{{ selected.other.pin }}</RouterLink></dd></template>
            <dt>Finding</dt><dd>{{ selected.summary }}</dd>
            <template v-if="selected.reviewed_by"><dt>Reviewed</dt><dd>{{ selected.reviewed_by }} · {{ when(selected.reviewed_at) }}<span v-if="selected.note" class="sub">{{ selected.note }}</span></dd></template>
          </dl>
          <div class="field"><label for="note">Review note</label>
            <textarea id="note" v-model="note" placeholder="How was it resolved, or why is it a dispute?"></textarea></div>
          <div v-if="error" class="banner banner-error"><Icon name="alert" :size="16" /><span>{{ error }}</span></div>
          <div class="res-actions" style="flex-wrap: wrap">
            <template v-if="selected.status === 'open'">
              <button class="btn btn-primary btn-sm" :disabled="saving" @click="review('resolved')"><Icon name="check" :size="14" />Mark resolved</button>
              <button class="btn btn-secondary btn-sm" :disabled="saving" @click="review('dispute')"><Icon name="flag" :size="14" />Boundary dispute</button>
            </template>
            <button v-else class="btn btn-secondary btn-sm" :disabled="saving" @click="review('open')">Reopen</button>
            <RouterLink v-if="selected.parcel.status === 'active'" class="btn btn-ghost btn-sm" :to="`/officer/parcels/${selected.parcel.id}/boundary`">
              <Icon name="edit" :size="14" />Fix boundary of kitta {{ selected.parcel.kitta }}</RouterLink>
          </div>
        </section>
        <section v-else-if="list" class="box"><p class="note" style="margin: 0">Select an issue to review it.</p></section>
      </div>
    </div>
  </main>
</template>
