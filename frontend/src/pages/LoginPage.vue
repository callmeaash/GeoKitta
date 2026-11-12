<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { login } from '../auth.js'
import BrandMark from '../components/BrandMark.vue'
import Icon from '../components/Icon.vue'

const route = useRoute()
const router = useRouter()
const username = ref('')
const password = ref('')
const show = ref(false)
const busy = ref(false)
const error = ref('')

async function submit() {
  error.value = ''
  if (!username.value.trim() || !password.value) {
    error.value = 'Enter your username and password.'
    return
  }
  busy.value = true
  try {
    await login(username.value.trim(), password.value)
    const next = typeof route.query.next === 'string' && route.query.next.startsWith('/') ? route.query.next : '/officer'
    router.replace(next)
  } catch (e) {
    error.value = e.status === 401 ? 'Wrong username or password.' : e.status === 429 ? `${e.message[0].toUpperCase()}${e.message.slice(1)}.` : `Sign in failed: ${e.message}`
    password.value = ''
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="login">
    <div class="login-art" aria-hidden="true">
      <svg viewBox="0 0 600 800" preserveAspectRatio="xMidYMid slice">
        <defs>
          <pattern id="kitta" width="120" height="96" patternUnits="userSpaceOnUse" patternTransform="rotate(-8)">
            <path d="M0 0h52l8 44-60 6zM52 0h68v38l-60 6zM0 50l60-6 6 52H0zM60 44l60-6v58H66z"
                  fill="none" stroke="#1E3A8A" stroke-opacity=".35" stroke-width="1.2" />
          </pattern>
        </defs>
        <rect width="600" height="800" fill="url(#kitta)" />
        <path d="M80 300l90-20 30 70-80 30z" fill="rgba(253,186,116,.45)" stroke="#EA580C" stroke-width="2.5" />
      </svg>
      <div class="veil"></div>
      <div class="login-copy">
        <BrandMark :size="44" />
        <h2>Land parcel records, mapped and validated.</h2>
        <p>The GeoKitta officer workspace for registering owners and parcels from survey coordinates, recording
          ownership transfers and reviewing data quality.</p>
      </div>
    </div>

    <div class="login-side">
      <form class="login-card" novalidate @submit.prevent="submit">
        <RouterLink class="brand" to="/" style="min-width: 0">
          <BrandMark :size="32" />
          <span><span class="brand-name">GeoKitta</span><span class="brand-sub">Officer workspace</span></span>
        </RouterLink>
        <h1>Officer sign in</h1>
        <p class="lead">Use your office account to continue.</p>

        <div v-if="error" class="banner banner-error" role="alert"><Icon name="alert" :size="16" /><span>{{ error }}</span></div>
        <div class="field">
          <label for="user">Username</label>
          <input id="user" v-model="username" type="text" autocomplete="username" autocapitalize="none" spellcheck="false">
        </div>
        <div class="field">
          <label for="pw">Password</label>
          <div class="input-wrap">
            <input id="pw" v-model="password" :type="show ? 'text' : 'password'" autocomplete="current-password">
            <button type="button" class="icon-btn end-btn" :aria-label="show ? 'Hide password' : 'Show password'"
                    @click="show = !show"><Icon :name="show ? 'eyeOff' : 'eye'" :size="18" /></button>
          </div>
          <span class="hint">Forgot it? Ask your office administrator to reset it.</span>
        </div>
        <button type="submit" class="btn btn-primary btn-block" style="height: 42px" :disabled="busy">
          {{ busy ? 'Signing in…' : 'Sign in' }}
        </button>
        <div class="login-back"><RouterLink class="link" to="/"><Icon name="arrowLeft" :size="16" />Back to public map</RouterLink></div>
        <div class="login-note"><Icon name="info" :size="16" />
          <span>Demonstration system — synthetic data only. Not an official government service.</span></div>
      </form>
    </div>
  </div>
</template>
