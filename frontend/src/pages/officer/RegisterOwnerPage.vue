<script setup>
import BsDateInput from '../../components/BsDateInput.vue'
import { computed, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { request } from '../../api.js'
import Icon from '../../components/Icon.vue'
import { DISTRICT_OPTIONS, bsText, districtName, label, plural, todayAd } from '../../utils/format.js'

const router = useRouter()
const TYPES = ['individual', 'organisation', 'government', 'communal']
const SUFFIX = { male: 'M', female: 'F', other: 'X', organisation: 'O', government: 'G', communal: 'C' }

const form = reactive({
  owner_type: 'individual', full_name: '', full_name_ne: '', gender: 'male', date_of_birth: '', citizenship_no: '',
  district_code: 27, address: '', phone: ''
})
const similar = ref([])
const checking = ref(false)
const saving = ref(false)
const errors = ref([])
const duplicates = ref(null) // set when the API refuses with 409

const individual = computed(() => form.owner_type === 'individual')
const linPreview = computed(() => `${String(form.district_code).padStart(2, '0')}-______-${
  individual.value ? SUFFIX[form.gender] : SUFFIX[form.owner_type]}`)

let timer
let seq = 0
watch(() => [form.full_name, form.date_of_birth, form.owner_type, form.district_code], () => {
  clearTimeout(timer)
  timer = setTimeout(checkSimilar, 350)
})

async function checkSimilar() {
  const name = form.full_name.trim()
  if (name.length < 3) {
    similar.value = []
    return
  }
  const mine = ++seq
  checking.value = true
  try {
    const found = await request('/api/officer/owners/similar', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ owner_type: form.owner_type, full_name: name, district_code: form.district_code,
        date_of_birth: individual.value && form.date_of_birth ? form.date_of_birth : null })
    })
    if (mine === seq) similar.value = found
  } finally {
    if (mine === seq) checking.value = false
  }
}

function body(confirmNew = false) {
  const clean = v => (typeof v === 'string' && v.trim() === '' ? null : typeof v === 'string' ? v.trim() : v)
  const out = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, clean(v)]))
  if (!individual.value) {
    out.gender = null
    out.date_of_birth = null
  }
  return { ...out, confirm_new: confirmNew }
}

async function save(confirmNew = false) {
  errors.value = []
  saving.value = true
  try {
    const res = await fetch('/api/officer/owners', {
      method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body(confirmNew))
    })
    const data = await res.json()
    if (res.status === 201) {
      router.push({ path: `/officer/owners/${data.id}`, query: { created: '1' } })
    } else if (res.status === 409) {
      duplicates.value = data.similar
    } else if (res.status === 422) {
      errors.value = Array.isArray(data.detail)
        ? data.detail.map(d => `${d.loc.slice(1).join(' ') || 'form'}: ${d.msg.replace(/^Value error, /, '')}`)
        : [String(data.detail)]
    } else if (res.status === 401) {
      router.push({ path: '/officer/login', query: { next: '/officer/owners/new' } })
    } else {
      errors.value = [data.detail || `Save failed (${res.status})`]
    }
  } catch (e) {
    errors.value = [e.message]
  } finally {
    saving.value = false
  }
}

const existing = computed(() => duplicates.value?.[0])
const reasons = s => [s.likely_duplicate ? 'Likely the same owner' : null, s.same_dob ? 'same date of birth' : null,
  s.same_district ? 'same district' : null].filter(Boolean).join(' · ')
</script>

<template>
  <main class="page">
    <div class="page-head">
      <div>
        <div class="crumbs"><RouterLink to="/officer">Dashboard</RouterLink><Icon name="chevronRight" :size="12" />
          <RouterLink to="/officer/owners">Owners</RouterLink><Icon name="chevronRight" :size="12" />Register owner</div>
        <h1 class="page-title">Register owner</h1>
        <p class="page-sub">Owners are checked against existing records so the same person is not registered twice.</p>
      </div>
    </div>

    <div v-if="errors.length" class="banner banner-error" role="alert"><Icon name="alert" :size="16" />
      <div><strong>Please check the form</strong><span v-for="e in errors" :key="e" style="display: block">{{ e }}</span></div>
    </div>

    <form class="grid-2-wide" novalidate @submit.prevent="save(false)">
      <section class="box">
        <div class="field"><span class="label">Owner type</span>
          <div class="seg" role="group" aria-label="Owner type">
            <button v-for="t in TYPES" :key="t" type="button" :class="{ on: form.owner_type === t }"
                    @click="form.owner_type = t">{{ label(t) }}</button>
          </div>
        </div>
        <div class="form-grid">
          <div class="field span-2"><label for="name">Full name</label>
            <input id="name" v-model="form.full_name" type="text" autocomplete="off" required>
            <span class="hint">As written on the citizenship certificate or registration document</span></div>
          <div class="field span-2"><label for="name-ne">Name in Nepali (optional)</label>
            <input id="name-ne" v-model="form.full_name_ne" type="text" autocomplete="off" lang="ne"></div>
          <template v-if="individual">
            <div class="field"><label for="gender">Gender</label>
              <select id="gender" v-model="form.gender">
                <option value="male">Male</option><option value="female">Female</option><option value="other">Other</option>
              </select></div>
            <div class="field"><label for="dob">Date of birth</label>
              <BsDateInput id="dob" v-model="form.date_of_birth" min="1918-04-13" :max="todayAd()" /></div>
          </template>
          <div class="field"><label for="cit">{{ individual ? 'Citizenship No.' : 'Registration No.' }}</label>
            <input id="cit" v-model="form.citizenship_no" type="text" class="num" placeholder="e.g. 27-01-74-05512">
            <span class="hint">Fictional numbers only in this demo</span></div>
          <div class="field"><label for="district">District</label>
            <select id="district" v-model.number="form.district_code">
              <option v-for="d in DISTRICT_OPTIONS" :key="d.code" :value="d.code">{{ d.name }}</option>
            </select></div>
          <div class="field"><label for="addr">Address</label><input id="addr" v-model="form.address" type="text"></div>
          <div class="field"><label for="phone">Phone</label>
            <input id="phone" v-model="form.phone" type="text" class="num" inputmode="tel" placeholder="98XXXXXXXX"></div>
        </div>
      </section>

      <section class="box">
        <div class="box-head"><h2 class="box-title"><Icon name="key" :size="18" />Landowner ID (LIN)</h2></div>
        <p class="note" style="margin-top: 0">A LIN is generated when the owner is saved: district code, serial number and
          a letter for the owner type or gender.</p>
        <div class="input-like" style="background: #fff"><span class="num muted">{{ linPreview }}</span>
          <span class="tag" style="margin-left: auto">Generated on save</span></div>
        <div class="divider" style="margin: 18px 0"></div>
        <div class="box-head" style="margin-bottom: 8px">
          <h2 class="box-title"><Icon name="search" :size="18" />Similar existing owners</h2>
          <span v-if="checking" class="muted" style="font-size: 12px">checking…</span>
        </div>
        <ul class="checklist">
          <li v-for="s in similar" :key="s.id" :class="s.likely_duplicate ? 'warn' : ''">
            <Icon :name="s.likely_duplicate ? 'alert' : 'user'" :size="16" />
            <div>
              <strong>{{ s.full_name }} <span class="muted num">· {{ s.lin }}</span></strong>
              <span>{{ s.distance === 0 ? 'Same name' : `${s.distance} letter${s.distance > 1 ? 's' : ''} different` }}
                <template v-if="s.date_of_birth"> · born {{ bsText(s.date_of_birth) }}</template> · {{ plural(s.parcels, 'parcel') }}
                <template v-if="reasons(s)"><br>{{ reasons(s) }}</template></span>
            </div>
            <RouterLink class="link" :to="`/officer/owners/${s.id}`" target="_blank" style="margin-left: auto">View</RouterLink>
          </li>
          <li v-if="!similar.length && form.full_name.trim().length >= 3 && !checking">
            <Icon name="checkCircle" :size="16" /><div><span>No similar owners found.</span></div></li>
          <li v-if="form.full_name.trim().length < 3"><div><span class="muted">Type a name to check for duplicates.</span></div></li>
        </ul>
      </section>
    </form>

    <div class="footer-bar">
      <RouterLink class="btn btn-ghost" to="/officer/owners">Cancel</RouterLink>
      <button class="btn btn-primary" :disabled="saving" @click="save(false)"><Icon name="check" :size="16" />
        {{ saving ? 'Saving…' : 'Save owner' }}</button>
    </div>

    <div v-if="existing" class="modal-backdrop open" role="dialog" aria-modal="true" aria-labelledby="dup-title">
      <div class="modal">
        <div class="modal-head">
          <span class="modal-icon amber"><Icon name="users" :size="20" /></span>
          <div><h2 id="dup-title">Possible duplicate owner found</h2>
            <p>An owner with a very similar name<template v-if="existing.same_dob"> and the same date of birth</template>
              already exists.</p></div>
        </div>
        <div class="modal-body">
          <div class="compare">
            <div class="cmp-col"><h5>Entered</h5><div class="cmp-name">{{ form.full_name }}</div>
              <div class="cmp-meta">{{ bsText(form.date_of_birth) }} · {{ districtName(form.district_code) }}</div></div>
            <div class="cmp-col existing"><h5>Existing record</h5><div class="cmp-name">{{ existing.full_name }}</div>
              <div class="cmp-meta">{{ bsText(existing.date_of_birth) }} · {{ districtName(existing.district_code) }} ·
                {{ existing.lin }}</div></div>
          </div>
          <ul class="match-list">
            <li class="diff"><Icon name="alert" :size="16" />
              <span>{{ existing.distance === 0 ? 'Exactly the same name' : `Name differs by ${existing.distance} letter${existing.distance > 1 ? 's' : ''}` }}</span></li>
            <li v-if="existing.same_dob"><Icon name="check" :size="16" />Same date of birth</li>
            <li v-if="existing.same_district"><Icon name="check" :size="16" />Same district</li>
            <li><Icon name="parcel" :size="16" />Holds {{ existing.parcels }} parcel{{ existing.parcels === 1 ? '' : 's' }}</li>
            <li v-if="duplicates.length > 1"><Icon name="users" :size="16" />{{ duplicates.length - 1 }} more similar record(s)</li>
          </ul>
        </div>
        <div class="modal-foot">
          <button class="btn btn-ghost" @click="duplicates = null">Cancel</button>
          <button class="btn btn-secondary" :disabled="saving" @click="duplicates = null; save(true)">Create new owner anyway</button>
          <RouterLink class="btn btn-primary" :to="`/officer/owners/${existing.id}`">Use existing owner</RouterLink>
        </div>
      </div>
    </div>
  </main>
</template>
