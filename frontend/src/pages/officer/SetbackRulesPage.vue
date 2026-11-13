<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { request } from '../../api.js'
import Icon from '../../components/Icon.vue'
import { fmt, label, measuredFrom } from '../../utils/format.js'

const rules = ref([])
const error = ref('')
const message = ref('')
const editing = ref(null) // null | 'new' | rule id
const form = reactive({ feature_type: 'river', distance_m: 15, measured_from: 'bank', source: 'municipal', note: '' })
const formError = ref('')
const preview = ref(null)
const DEFAULT_FROM = { highway: 'centre_line', road: 'centre_line', river: 'bank', stream: 'bank', power_line: 'line' }

async function load() {
  rules.value = await request('/api/setback-rules')
  if (!preview.value && rules.value.length) preview.value = rules.value.find(r => r.feature_type === 'river') || rules.value[0]
}
onMounted(() => load().catch(e => { error.value = e.message }))

function edit(rule) {
  formError.value = ''
  if (rule) {
    Object.assign(form, { ...rule, note: rule.note || '' })
    editing.value = rule.id
  } else {
    Object.assign(form, { feature_type: 'river', distance_m: 15, measured_from: 'bank', source: 'municipal', note: '' })
    editing.value = 'new'
  }
}

async function save() {
  formError.value = ''
  const body = { ...form, distance_m: Number(form.distance_m), note: form.note || null }
  delete body.id
  try {
    const saved = await request(editing.value === 'new' ? '/api/admin/setback-rules' : `/api/admin/setback-rules/${editing.value}`, {
      method: editing.value === 'new' ? 'POST' : 'PUT', credentials: 'include',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
    })
    message.value = `${label(saved.feature_type)} rule saved: ${fmt(saved.distance_m)} m from the ${measuredFrom(saved.measured_from)} (${saved.source}). The setback search uses it at once.`
    editing.value = null
    preview.value = saved
    await load()
  } catch (e) {
    formError.value = e.message
  }
}

async function remove(rule) {
  if (!window.confirm(`Delete the ${rule.source} ${label(rule.feature_type).toLowerCase()} rule (${fmt(rule.distance_m)} m)?`)) return
  try {
    await request(`/api/admin/setback-rules/${rule.id}`, { method: 'DELETE', credentials: 'include' })
    message.value = 'Rule deleted.'
    if (preview.value?.id === rule.id) preview.value = null
    await load()
  } catch (e) {
    error.value = e.message
  }
}

/** Schematic cross-section for the preview: the feature in the middle and the protected zone either side. */
const diagram = computed(() => {
  const r = preview.value
  if (!r) return null
  const wide = { river: 25, stream: 4, highway: 14, road: 8, power_line: 1 }[r.feature_type] ?? 8
  const half = r.measured_from === 'bank' ? wide / 2 + r.distance_m : r.distance_m
  const scale = 140 / Math.max(half, wide / 2 + 5)
  return { feature: wide * scale, zone: half * 2 * scale, color: ['river', 'stream'].includes(r.feature_type) ? '#A5CFF5' : r.feature_type === 'power_line' ? '#64748B' : '#CBD5E1' }
})
</script>

<template>
  <main class="page">
    <div class="page-head">
      <div>
        <div class="crumbs"><RouterLink to="/officer">Dashboard</RouterLink><Icon name="chevronRight" :size="12" />Admin<Icon name="chevronRight" :size="12" />Setback rules</div>
        <h1 class="page-title">Setback rules</h1>
        <p class="page-sub">Distances used to find parcels inside road, river and power-line setback zones.</p>
      </div>
      <div class="head-actions"><button class="btn btn-primary" @click="edit(null)"><Icon name="plus" :size="16" />Add rule</button></div>
    </div>
    <div v-if="message" class="banner banner-success" role="status"><Icon name="checkCircle" :size="16" /><span>{{ message }}</span></div>
    <div v-if="error" class="banner banner-error"><Icon name="alert" :size="16" /><span>{{ error }}</span></div>

    <div class="grid-2-wide">
      <div class="stack">
        <section class="box flush">
          <div class="tbl-wrap">
            <table class="tbl">
              <thead><tr><th>Feature type</th><th>Distance</th><th>Measured from</th><th>Source</th><th>Note</th><th style="text-align: right">Actions</th></tr></thead>
              <tbody>
                <tr v-for="r in rules" :key="r.id" class="row-link" @click="preview = r">
                  <td>{{ label(r.feature_type) }}</td><td class="num">{{ fmt(r.distance_m) }} m</td><td>{{ label(measuredFrom(r.measured_from)) }}</td>
                  <td><span class="tag" :class="{ 'tag-teal': r.source === 'national' }">{{ label(r.source) }}</span></td>
                  <td class="muted">{{ r.note || '—' }}</td>
                  <td><div class="row-actions">
                    <button class="btn btn-ghost btn-sm" @click.stop="edit(r)"><Icon name="edit" :size="14" />Edit</button>
                    <button class="btn btn-ghost btn-sm" @click.stop="remove(r)"><Icon name="trash" :size="14" /></button>
                  </div></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="editing" class="box">
          <div class="box-head"><h2 class="box-title">{{ editing === 'new' ? 'New rule' : 'Edit rule' }}</h2></div>
          <form class="form-grid" @submit.prevent="save">
            <div class="field"><label for="r-type">Feature type</label>
              <select id="r-type" v-model="form.feature_type" @change="form.measured_from = DEFAULT_FROM[form.feature_type]">
                <option value="highway">Highway</option><option value="road">Road</option><option value="river">River</option>
                <option value="stream">Stream</option><option value="power_line">Power line</option></select></div>
            <div class="field"><label for="r-dist">Distance</label>
              <div class="input-wrap"><input id="r-dist" v-model="form.distance_m" type="number" min="0.5" max="200" step="0.01" class="num"><span class="suffix">m</span></div></div>
            <div class="field"><label for="r-from">Measured from</label>
              <select id="r-from" v-model="form.measured_from"><option value="centre_line">Centre line</option><option value="bank">Bank</option><option value="line">Line</option></select></div>
            <div class="field"><label for="r-src">Source</label>
              <select id="r-src" v-model="form.source"><option value="municipal">Municipal</option><option value="national">National</option></select></div>
            <div class="field span-2"><label for="r-note">Note</label><input id="r-note" v-model="form.note" placeholder="e.g. 15 m from each bank"></div>
            <div v-if="formError" class="banner banner-error span-2"><Icon name="alert" :size="16" /><span>{{ formError }}</span></div>
            <div class="res-actions span-2">
              <button class="btn btn-primary btn-sm" type="submit"><Icon name="check" :size="14" />Save rule</button>
              <button class="btn btn-ghost btn-sm" type="button" @click="editing = null">Cancel</button>
            </div>
          </form>
        </section>

        <section class="box">
          <div class="box-head"><h2 class="box-title"><Icon name="info" :size="18" />Where these rules are used</h2></div>
          <p class="note" style="margin: 0">The public viewer's buffer and setback search, and the setback warning in parcel details.
            When a municipal and a national rule differ, the wider one is used for the warning and both can be chosen in the search.</p>
        </section>
      </div>

      <div class="stack sticky">
        <section v-if="preview && diagram" class="box">
          <div class="box-head"><h2 class="box-title">Preview</h2><span class="tag">{{ label(preview.feature_type) }} · {{ fmt(preview.distance_m) }} m</span></div>
          <svg viewBox="0 0 320 160" class="setback-diagram" role="img" :aria-label="`Setback zone of ${preview.distance_m} m`">
            <rect x="0" y="0" width="320" height="160" fill="#F4F4F2" />
            <rect :x="160 - diagram.zone / 2" y="0" :width="diagram.zone" height="160" fill="rgba(124,58,237,.16)" stroke="#7C3AED" stroke-dasharray="5 4" />
            <rect :x="160 - diagram.feature / 2" y="0" :width="Math.max(diagram.feature, 2)" height="160" :fill="diagram.color" />
            <line x1="160" y1="0" x2="160" y2="160" stroke="#334155" stroke-dasharray="2 4" />
            <text x="160" y="16" text-anchor="middle" font-size="11" font-weight="600" fill="#334155">{{ label(preview.feature_type) }}</text>
            <text :x="160 - diagram.zone / 2 + 6" y="152" font-size="11" fill="#5B21B6">{{ fmt(preview.distance_m) }} m from the {{ measuredFrom(preview.measured_from) }}</text>
          </svg>
        </section>
        <section class="box">
          <div class="box-head"><h2 class="box-title">How distances are measured</h2></div>
          <dl class="kv wide" style="margin: 0">
            <dt>Centre line</dt><dd>Roads and highways: from the road's centre line, on both sides.</dd>
            <dt>Bank</dt><dd>Rivers and streams: from each bank outwards (half the river's width is added).</dd>
            <dt>Line</dt><dd>Power lines: the corridor around the line.</dd>
          </dl>
        </section>
      </div>
    </div>
  </main>
</template>

<style scoped>
.setback-diagram { width: 100%; height: auto; display: block; border-radius: var(--radius-md); border: 1px solid var(--color-border); }
</style>
