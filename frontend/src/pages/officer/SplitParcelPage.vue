<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { request } from '../../api.js'
import Icon from '../../components/Icon.vue'
import CoordinateEditor from '../../components/officer/CoordinateEditor.vue'
import PreviewMap from '../../components/officer/PreviewMap.vue'
import ValidationList from '../../components/officer/ValidationList.vue'
import { fmt, shareLabel } from '../../utils/format.js'

const route = useRoute()
const router = useRouter()
const id = Number(route.params.id)
const KINDS = ['childA', 'childB', 'childC', 'childA', 'childB', 'childC']
const COLORS = ['#0F766E', '#2563EB', '#7C3AED', '#0F766E', '#2563EB', '#7C3AED']

const parcel = ref(null)
const owners = ref([])
const loadError = ref('')
const children = ref([{ points: [], crs: 'utm' }, { points: [], crs: 'utm' }])
const result = ref(null)
const checking = ref(false)
const saving = ref(false)
const errors = ref([])

onMounted(async () => {
  try {
    parcel.value = await request(`/api/parcels/${id}`)
    owners.value = (await request(`/api/officer/parcels/${id}/ownership`)).current
  } catch (e) {
    loadError.value = e.status === 404 ? 'This parcel is not active (it may already have been split).' : e.message
  }
})

const filled = c => c.points.filter(p => p[0] != null && p[1] != null)
const ready = computed(() => children.value.every(c => filled(c).length >= 3))
const shapes = computed(() => [
  { geometry: parcel.value?.geometry, kind: 'parent' },
  ...(result.value?.children || []).map((c, n) => ({ geometry: c.geometry, kind: KINDS[n] }))
])
const step = computed(() => (!ready.value ? 2 : result.value?.ok ? 4 : 3))

let timer
let seq = 0
watch(children, () => {
  clearTimeout(timer)
  timer = setTimeout(runCheck, 400)
}, { deep: true })

const body = () => ({ children: children.value.map(c => ({ points: filled(c), crs: c.crs })) })

async function runCheck() {
  if (!ready.value) {
    result.value = null
    return
  }
  const mine = ++seq
  checking.value = true
  try {
    const r = await request(`/api/officer/parcels/${id}/split/check`, {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body())
    })
    if (mine === seq) result.value = r
  } catch (e) {
    if (mine === seq) result.value = { ok: false, children: [], checks: [{ id: 'input', status: 'fail', title: 'Cannot read the coordinates', detail: e.message }] }
  } finally {
    if (mine === seq) checking.value = false
  }
}

async function save() {
  errors.value = []
  saving.value = true
  try {
    const res = await fetch(`/api/officer/parcels/${id}/split`, {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body())
    })
    const data = await res.json()
    if (res.status === 201) {
      const kittas = data.children.map(c => c.kitta).join(', ')
      router.push({ path: `/officer/parcels/${id}`,
        query: { saved: `${data.parent_pin} split into kitta ${kittas}, case ${data.case_id}.` } })
    } else {
      errors.value = data.checks ? data.checks.filter(c => c.status === 'fail').map(c => c.title) : [data.detail]
    }
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <main class="page">
    <div class="page-head">
      <div>
        <div class="crumbs"><RouterLink to="/officer">Dashboard</RouterLink><Icon name="chevronRight" :size="12" /><RouterLink to="/officer/parcels">Parcels</RouterLink><Icon name="chevronRight" :size="12" />
          <RouterLink :to="`/officer/parcels/${id}`">Kitta {{ parcel?.kitta || '…' }}</RouterLink><Icon name="chevronRight" :size="12" />Split</div>
        <h1 class="page-title">Split parcel (kitta kaat){{ parcel ? ` — Kitta ${parcel.kitta}` : '' }}</h1>
        <p class="page-sub"><span class="tag">Split</span> The parent is retired and each child gets a new kitta number.</p>
      </div>
    </div>
    <div class="stepper" aria-label="Progress">
      <div class="step done"><span class="dot"><Icon name="check" :size="14" /></span>Select parent</div>
      <div class="step-line" :class="{ done: step > 2 }"></div>
      <div class="step" :class="step > 2 ? 'done' : 'current'"><span class="dot"><Icon v-if="step > 2" name="check" :size="14" /><template v-else>2</template></span>Child coordinates</div>
      <div class="step-line" :class="{ done: step > 3 }"></div>
      <div class="step" :class="step > 3 ? 'done' : step === 3 ? 'current' : ''"><span class="dot"><Icon v-if="step > 3" name="check" :size="14" /><template v-else>3</template></span>Validate</div>
      <div class="step-line" :class="{ done: step > 3 }"></div>
      <div class="step" :class="step === 4 ? 'current' : ''"><span class="dot">4</span>Confirm</div>
    </div>
    <div v-if="loadError" class="banner banner-error"><Icon name="alert" :size="16" /><span>{{ loadError }}</span></div>
    <div v-if="errors.length" class="banner banner-error"><Icon name="alert" :size="16" /><span>{{ errors.join(' ') }}</span></div>

    <div v-if="parcel" class="grid-2">
      <div class="stack">
        <section class="box">
          <div class="box-head"><h2 class="box-title"><Icon name="parcel" :size="18" />Parent parcel</h2><span class="tag">Will be retired</span></div>
          <dl class="kv wide" style="margin: 0">
            <dt>Kitta / PIN</dt><dd>{{ parcel.kitta }} · {{ parcel.pin }}</dd>
            <dt>Ward / sheet</dt><dd>Ward {{ parcel.ward }} · Map sheet {{ parcel.map_sheet }}</dd>
            <dt>Area</dt><dd>{{ fmt(parcel.boundary_area_m2) }} m²</dd>
            <dt>Owners</dt><dd>{{ owners.map(o => `${o.full_name} (${shareLabel(o.share)})`).join(', ') || '—' }}
              <span class="sub">Children inherit the parent's owners and shares</span></dd>
          </dl>
        </section>
        <section class="box">
          <div class="box-head"><div><h2 class="box-title"><Icon name="split" :size="18" />Child parcels</h2>
            <p class="box-sub">Survey coordinates for each new parcel.</p></div></div>
          <details v-for="(c, n) in children" :key="n" class="sec" open>
            <summary><i class="dot-swatch" :style="{ background: COLORS[n] + '55', border: `2px solid ${COLORS[n]}` }"></i>
              Child {{ 'ABCDEF'[n] }}<template v-if="result?.children[n]"> — new kitta {{ result.children[n].kitta }}
                <span class="tag" style="margin-left: 8px">{{ fmt(result.children[n].area_m2) }} m²</span></template>
              <button v-if="children.length > 2" class="icon-btn" type="button" style="margin-left: auto" :aria-label="`Remove child ${'ABCDEF'[n]}`"
                      @click.prevent="children.splice(n, 1)"><Icon name="x" :size="16" /></button></summary>
            <div class="sec-body"><CoordinateEditor v-model:points="c.points" v-model:crs="c.crs" /></div>
          </details>
          <button v-if="children.length < 6" class="link" type="button" @click="children.push({ points: [], crs: 'utm' })">
            <Icon name="plus" :size="14" />Add another child parcel</button>
        </section>
      </div>
      <div class="stack sticky">
        <section class="box">
          <div class="box-head"><h2 class="box-title"><Icon name="map" :size="18" />Preview</h2></div>
          <PreviewMap :shapes="shapes" :height="360">
            <span><i class="sw sw-old"></i>Parent</span><span><i class="sw sw-childA"></i>Child A</span><span><i class="sw sw-childB"></i>Child B</span>
          </PreviewMap>
        </section>
        <section class="box">
          <div class="box-head"><h2 class="box-title"><Icon name="checkCircle" :size="18" />Validation</h2>
            <span v-if="result" class="status" :class="result.ok ? 'st-green' : 'st-red'">{{ result.ok ? 'All checks passed' : 'Fix the problems' }}</span></div>
          <ValidationList :checks="result?.checks || []" :busy="checking" />
        </section>
      </div>
    </div>

    <div v-if="parcel" class="footer-bar">
      <span class="left"><Icon name="info" :size="16" />The split is saved as one case: parent retired, children created, lineage and owners recorded.</span>
      <RouterLink class="btn btn-ghost" :to="`/officer/parcels/${id}`">Cancel</RouterLink>
      <button class="btn btn-primary" :disabled="saving || !result?.ok" @click="save"><Icon name="check" :size="16" />{{ saving ? 'Saving…' : 'Confirm split' }}</button>
    </div>
  </main>
</template>
