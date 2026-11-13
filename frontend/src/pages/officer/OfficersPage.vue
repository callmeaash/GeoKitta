<script setup>
import { onMounted, reactive, ref } from 'vue'
import { request } from '../../api.js'
import { auth, initials } from '../../auth.js'
import Icon from '../../components/Icon.vue'

const officers = ref([])
const error = ref('')
const message = ref('')
const dialog = ref(null) // { kind: 'add' } | { kind: 'password', officer }
const form = reactive({ username: '', full_name: '', office: 'Survey Office (demo)', is_admin: false, password: '' })
const formError = ref('')
const busy = ref(false)

const post = (url, body, method = 'POST') => request(url, {
  method, credentials: 'include', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
})
const when = iso => (iso ? new Date(iso).toLocaleString('en-GB', { dateStyle: 'medium', timeStyle: 'short' }) : 'Never')

async function load() {
  try {
    officers.value = await request('/api/admin/officers')
  } catch (e) {
    error.value = e.message
  }
}
onMounted(load)

function openAdd() {
  Object.assign(form, { username: '', full_name: '', office: 'Survey Office (demo)', is_admin: false, password: '' })
  formError.value = ''
  dialog.value = { kind: 'add' }
}

async function submit() {
  formError.value = ''
  busy.value = true
  try {
    if (dialog.value.kind === 'add') {
      await post('/api/admin/officers', { ...form, username: form.username.trim().toLowerCase() })
      message.value = `Account ${form.username} created. Give the password to the officer in person.`
    } else {
      await post(`/api/admin/officers/${dialog.value.officer.id}/password`, { password: form.password })
      message.value = `Password reset for ${dialog.value.officer.username}.`
    }
    dialog.value = null
    await load()
  } catch (e) {
    formError.value = e.message
  } finally {
    busy.value = false
  }
}

async function toggle(o, field) {
  error.value = ''
  try {
    await post(`/api/admin/officers/${o.id}`, { [field]: !o[field] }, 'PATCH')
    message.value = field === 'is_active'
      ? `${o.username} ${o.is_active ? 'can no longer sign in' : 'can sign in again'}.`
      : `${o.username} is ${o.is_admin ? 'no longer an admin' : 'now an admin'}.`
    await load()
  } catch (e) {
    error.value = e.message
  }
}

function generate() {
  const bytes = crypto.getRandomValues(new Uint8Array(12))
  form.password = btoa(String.fromCharCode(...bytes)).replace(/[^a-zA-Z0-9]/g, '').slice(0, 14)
}
</script>

<template>
  <main class="page">
    <div class="page-head">
      <div>
        <div class="crumbs"><RouterLink to="/officer">Dashboard</RouterLink><Icon name="chevronRight" :size="12" />Admin<Icon name="chevronRight" :size="12" />Officer accounts</div>
        <h1 class="page-title">Officer accounts</h1>
        <p class="page-sub">Each officer has a personal account so every change is recorded in the audit log.</p>
      </div>
      <div class="head-actions"><button class="btn btn-primary" @click="openAdd"><Icon name="userPlus" :size="16" />Add officer</button></div>
    </div>
    <div v-if="message" class="banner banner-success" role="status"><Icon name="checkCircle" :size="16" /><span>{{ message }}</span></div>
    <div v-if="error" class="banner banner-error"><Icon name="alert" :size="16" /><span>{{ error }}</span></div>

    <section class="box flush">
      <div class="tbl-wrap">
        <table class="tbl">
          <thead><tr><th>Name</th><th>Username</th><th>Office</th><th>Role</th><th>Status</th><th>Last sign-in</th><th>Changes</th><th style="text-align: right">Actions</th></tr></thead>
          <tbody>
            <tr v-for="o in officers" :key="o.id">
              <td><span class="avatar sm">{{ initials(o.full_name) }}</span>{{ o.full_name }}<span v-if="o.id === auth.officer?.id" class="tag" style="margin-left: 6px">You</span></td>
              <td class="num">{{ o.username }}</td>
              <td>{{ o.office || '—' }}</td>
              <td><span class="tag" :class="{ 'tag-teal': o.is_admin }">{{ o.is_admin ? 'Admin' : 'Officer' }}</span></td>
              <td><span class="status" :class="o.is_active ? 'st-green' : 'st-grey'">{{ o.is_active ? 'Active' : 'Disabled' }}</span></td>
              <td class="num">{{ when(o.last_login_at) }}</td>
              <td class="num">{{ o.changes }}</td>
              <td>
                <div class="row-actions">
                  <button class="btn btn-ghost btn-sm" @click="formError = ''; form.password = ''; dialog = { kind: 'password', officer: o }"><Icon name="key" :size="14" />Reset password</button>
                  <template v-if="o.id !== auth.officer?.id">
                    <button class="btn btn-ghost btn-sm" @click="toggle(o, 'is_admin')">{{ o.is_admin ? 'Remove admin' : 'Make admin' }}</button>
                    <button class="btn btn-ghost btn-sm" @click="toggle(o, 'is_active')">{{ o.is_active ? 'Disable' : 'Enable' }}</button>
                  </template>
                </div>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <div v-if="dialog" class="modal-backdrop open" role="dialog" aria-modal="true" @click.self="dialog = null">
      <form class="modal" @submit.prevent="submit">
        <div class="modal-head"><span class="modal-icon amber"><Icon :name="dialog.kind === 'add' ? 'userPlus' : 'key'" :size="20" /></span>
          <div><h2>{{ dialog.kind === 'add' ? 'Add officer' : `Reset password — ${dialog.officer.full_name}` }}</h2>
            <p>Passwords are stored as argon2 hashes; nobody can read them back.</p></div></div>
        <div class="modal-body">
          <div v-if="dialog.kind === 'add'" class="form-grid">
            <div class="field"><label for="o-name">Full name</label><input id="o-name" v-model="form.full_name" required></div>
            <div class="field"><label for="o-user">Username</label><input id="o-user" v-model="form.username" placeholder="e.g. sita.maharjan" autocapitalize="none"></div>
            <div class="field span-2"><label for="o-office">Office</label><input id="o-office" v-model="form.office"></div>
            <label class="check span-2"><input v-model="form.is_admin" type="checkbox">Admin (can manage officers and setback rules)</label>
          </div>
          <div class="field"><label for="o-pw">{{ dialog.kind === 'add' ? 'Password' : 'New password' }}</label>
            <div class="input-wrap"><input id="o-pw" v-model="form.password" type="text" class="num" autocomplete="new-password">
              <button class="btn btn-ghost btn-sm end-btn" type="button" @click="generate">Generate</button></div>
            <span class="hint">At least 10 characters.</span></div>
          <div v-if="formError" class="banner banner-error"><Icon name="alert" :size="16" /><span>{{ formError }}</span></div>
        </div>
        <div class="modal-foot">
          <button class="btn btn-ghost" type="button" @click="dialog = null">Cancel</button>
          <button class="btn btn-primary" type="submit" :disabled="busy">{{ dialog.kind === 'add' ? 'Create account' : 'Reset password' }}</button>
        </div>
      </form>
    </div>
  </main>
</template>

<style scoped>
.avatar.sm { width: 26px; height: 26px; font-size: 11px; margin-right: 8px; display: inline-grid; vertical-align: middle; }
.input-wrap .end-btn { height: 28px; }
</style>
