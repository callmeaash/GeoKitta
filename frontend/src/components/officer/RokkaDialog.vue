<script setup>
import BsDateInput from '../../components/BsDateInput.vue'
import { reactive, ref } from 'vue'
import { request } from '../../api.js'
import { bsText, todayAd } from '../../utils/format.js'
import Icon from '../Icon.vue'

/** Place a rokka (hold) on a parcel, or release one (fukuwa). Each is recorded as its own case. */
const props = defineProps({
  mode: { type: String, default: 'place' }, // place | release
  parcelId: { type: Number, required: true },
  rokka: { type: Object, default: null } // the hold to release
})
const emit = defineEmits(['done', 'close'])
const today = todayAd()
const form = reactive({ requested_by_type: 'bank', requested_by_name: '', reason: '', date: today, remarks: '' })
const saving = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  if (props.mode === 'place' && form.requested_by_name.trim().length < 2) {
    error.value = 'Enter who requested the rokka.'
    return
  }
  saving.value = true
  try {
    const url = props.mode === 'place' ? `/api/officer/parcels/${props.parcelId}/rokka` : `/api/officer/rokka/${props.rokka.id}/release`
    const body = props.mode === 'place'
      ? { requested_by_type: form.requested_by_type, requested_by_name: form.requested_by_name.trim(), reason: form.reason || null, start_date: form.date }
      : { fukuwa_date: form.date, remarks: form.remarks || null }
    const r = await request(url, { method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    emit('done', r)
  } catch (e) {
    error.value = e.message
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="modal-backdrop open" role="dialog" aria-modal="true" @click.self="emit('close')">
    <form class="modal" @submit.prevent="submit">
      <div class="modal-head">
        <span class="modal-icon" :class="mode === 'place' ? 'red' : 'amber'"><Icon :name="mode === 'place' ? 'lock' : 'unlock'" :size="20" /></span>
        <div v-if="mode === 'place'"><h2>Place rokka</h2><p>Transfers of this parcel are blocked until the rokka is released (fukuwa).</p></div>
        <div v-else><h2>Release rokka (fukuwa)</h2><p>Held for {{ rokka.requested_by_name }} since {{ bsText(rokka.start_date) }}.</p></div>
      </div>
      <div class="modal-body">
        <div v-if="mode === 'place'" class="form-grid">
          <div class="field"><label for="rq-type">Requested by</label>
            <select id="rq-type" v-model="form.requested_by_type">
              <option value="bank">Bank</option><option value="court">Court</option><option value="ciaa">CIAA</option>
              <option value="government">Government office</option><option value="other">Other</option>
            </select></div>
          <div class="field"><label for="rq-name">Name</label><input id="rq-name" v-model="form.requested_by_name" placeholder="e.g. Nilgiri Demo Bank"></div>
          <div class="field"><label for="rq-reason">Reason</label><input id="rq-reason" v-model="form.reason" placeholder="e.g. loan security"></div>
          <div class="field"><label for="rq-date">Start date</label><BsDateInput id="rq-date" v-model="form.date" :max="today" /></div>
        </div>
        <div v-else class="form-grid">
          <div class="field"><label for="fk-date">Release date</label><BsDateInput id="fk-date" v-model="form.date" :min="rokka.start_date" :max="today" /></div>
          <div class="field"><label for="fk-rem">Remarks</label><input id="fk-rem" v-model="form.remarks" placeholder="e.g. loan repaid"></div>
        </div>
        <div v-if="error" class="banner banner-error" style="margin: 8px 0 0"><Icon name="alert" :size="16" /><span>{{ error }}</span></div>
      </div>
      <div class="modal-foot">
        <button class="btn btn-ghost" type="button" @click="emit('close')">Cancel</button>
        <button class="btn" :class="mode === 'place' ? 'btn-danger' : 'btn-primary'" type="submit" :disabled="saving">
          {{ saving ? 'Saving…' : mode === 'place' ? 'Place rokka' : 'Release rokka' }}</button>
      </div>
    </form>
  </div>
</template>
