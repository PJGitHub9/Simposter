<script setup lang="ts">
// "Sign in with Plex": opens Plex's sign-in page, then lists the account's
// servers with the connections Simposter can reach, and hands back the chosen
// server's address and token. Backend: backend/api/plex_auth.py.
import { onBeforeUnmount, ref } from 'vue'
import { getApiBase } from '@/services/apiBase'

const emit = defineEmits<{ connected: [value: { url: string; token: string; name: string }] }>()

interface Connection { uri: string; label: string; reachable: boolean }
interface Server { id: string; name: string; owned: boolean; connections: Connection[] }

const apiBase = getApiBase()
const state = ref<'idle' | 'waiting' | 'loading' | 'choose' | 'done'>('idle')
const error = ref('')
const authUrl = ref('')
const servers = ref<Server[]>([])
const picked = ref<Record<string, string>>({})
const using = ref('')
let pinId: number | null = null
let popup: Window | null = null
let timer: ReturnType<typeof setTimeout> | null = null
let startedAt = 0

const stop = () => {
  if (timer) clearTimeout(timer)
  timer = null
}
onBeforeUnmount(() => {
  stop()
  try { popup?.close() } catch { /* ignore */ }
})

const errorText = async (res: Response) => {
  try {
    const d = await res.json()
    return d.detail || `Request failed (${res.status})`
  } catch {
    return `Request failed (${res.status})`
  }
}

const start = async () => {
  error.value = ''
  servers.value = []
  // Open the window now, while this is still a click, or browsers block it.
  popup = window.open('', 'simposter-plex-sign-in', 'width=600,height=720')
  state.value = 'waiting'
  try {
    const res = await fetch(`${apiBase}/api/plex-auth/pin`, { method: 'POST' })
    if (!res.ok) throw new Error(await errorText(res))
    const d = await res.json()
    pinId = d.id
    authUrl.value = d.auth_url
    if (popup && !popup.closed) popup.location.href = d.auth_url
    startedAt = Date.now()
    timer = setTimeout(poll, 2000)
  } catch (e) {
    try { popup?.close() } catch { /* ignore */ }
    state.value = 'idle'
    error.value = e instanceof Error ? e.message : 'Couldn’t start the Plex sign-in'
  }
}

const poll = async () => {
  if (pinId == null) return
  const popupClosed = !!popup && popup.closed
  try {
    const res = await fetch(`${apiBase}/api/plex-auth/pin/${pinId}`)
    if (!res.ok) throw new Error(await errorText(res))
    const d = await res.json()
    if (d.status === 'authorized') {
      try { popup?.close() } catch { /* ignore */ }
      await loadServers()
      return
    }
    if (d.status === 'expired' || Date.now() - startedAt > 10 * 60 * 1000) {
      cancel('The sign-in took too long. Try again.')
      return
    }
  } catch (e) {
    cancel(e instanceof Error ? e.message : 'The sign-in stopped working. Try again.')
    return
  }
  if (popupClosed) {
    cancel('The Plex window was closed before signing in.')
    return
  }
  timer = setTimeout(poll, 2000)
}

const cancel = (message = '') => {
  stop()
  try { popup?.close() } catch { /* ignore */ }
  pinId = null
  state.value = 'idle'
  error.value = message
}

const loadServers = async (refresh = false) => {
  if (pinId == null) return
  state.value = 'loading'
  try {
    const res = await fetch(`${apiBase}/api/plex-auth/pin/${pinId}/servers${refresh ? '?refresh=true' : ''}`)
    if (!res.ok) throw new Error(await errorText(res))
    const d = await res.json()
    servers.value = d.servers || []
    const p: Record<string, string> = {}
    for (const s of servers.value) {
      const best = s.connections.find(c => c.reachable) || s.connections[0]
      if (best) p[s.id] = best.uri
    }
    picked.value = p
    state.value = 'choose'
  } catch (e) {
    cancel(e instanceof Error ? e.message : 'Couldn’t list your servers')
  }
}

const use = async (server: Server) => {
  const uri = picked.value[server.id]
  if (pinId == null || !uri) return
  using.value = server.id
  error.value = ''
  try {
    const res = await fetch(`${apiBase}/api/plex-auth/pin/${pinId}/use`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ server_id: server.id, uri }),
    })
    if (!res.ok) throw new Error(await errorText(res))
    const d = await res.json()
    pinId = null
    state.value = 'done'
    emit('connected', { url: d.url, token: d.token, name: d.name })
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Couldn’t use that server'
  } finally {
    using.value = ''
  }
}

const reachableCount = (s: Server) => s.connections.filter(c => c.reachable).length
</script>

<template>
  <div class="plex-sign-in">
    <div v-if="state === 'idle' || state === 'done'" class="psi-row">
      <button type="button" class="psi-btn" @click="start">
        <img src="/icons/plex.svg" alt="" class="psi-icon" />
        {{ state === 'done' ? 'Sign in again' : 'Sign in with Plex' }}
      </button>
      <span v-if="state === 'done'" class="psi-ok">✓ Server filled in below. Test it, then Save.</span>
      <span v-else class="psi-hint">Finds your server and fills in the address and token for you.</span>
    </div>

    <div v-else-if="state === 'waiting'" class="psi-row">
      <span class="psi-spinner" />
      <span class="psi-hint">
        Sign in to Plex in the window that opened.
        <a v-if="authUrl" :href="authUrl" target="_blank" rel="noopener">Didn’t open? Open it here</a>
      </span>
      <button type="button" class="psi-link" @click="cancel()">Cancel</button>
    </div>

    <div v-else-if="state === 'loading'" class="psi-row">
      <span class="psi-spinner" />
      <span class="psi-hint">Finding your servers and checking which addresses Simposter can reach…</span>
    </div>

    <div v-else-if="state === 'choose'" class="psi-choose">
      <p v-if="!servers.length" class="psi-hint">
        No Plex servers were found on this account.
        <button type="button" class="psi-link" @click="cancel()">Close</button>
      </p>
      <div v-for="s in servers" :key="s.id" class="psi-server">
        <div class="psi-server-head">
          <strong>{{ s.name }}</strong>
          <span v-if="!s.owned" class="psi-tag">Shared with you</span>
          <span class="psi-hint">{{ reachableCount(s) }} of {{ s.connections.length }} addresses reachable from Simposter</span>
        </div>
        <div class="psi-server-row">
          <select v-model="picked[s.id]" class="psi-select">
            <option v-for="c in s.connections" :key="c.uri" :value="c.uri">
              {{ c.reachable ? '✓' : '✗' }} {{ c.label }} · {{ c.uri }}
            </option>
          </select>
          <button type="button" class="psi-btn" :disabled="!!using || !picked[s.id]" @click="use(s)">
            {{ using === s.id ? 'Using…' : 'Use this server' }}
          </button>
        </div>
      </div>
      <div class="psi-row">
        <button type="button" class="psi-link" @click="loadServers(true)">Check again</button>
        <button type="button" class="psi-link" @click="cancel()">Cancel</button>
      </div>
    </div>

    <p v-if="error" class="psi-error">{{ error }}</p>
  </div>
</template>

<style scoped>
.plex-sign-in { display: flex; flex-direction: column; gap: 8px; }
.psi-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.psi-btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 8px 14px; border-radius: 8px; cursor: pointer;
  border: 1px solid rgba(229, 160, 13, 0.5); background: rgba(229, 160, 13, 0.12);
  color: var(--text-primary, #fff); font-size: 14px; font-weight: 600;
}
.psi-btn:hover:not(:disabled) { background: rgba(229, 160, 13, 0.22); }
.psi-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.psi-icon { width: 16px; height: 16px; }
.psi-hint { color: var(--text-muted, #888); font-size: 13px; }
.psi-hint a { color: var(--accent, #3dd6b7); }
.psi-ok { color: #3dd6b7; font-size: 13px; }
.psi-error { margin: 0; color: #f87171; font-size: 13px; }
.psi-link { background: none; border: none; padding: 0; color: var(--accent, #3dd6b7); cursor: pointer; font-size: 13px; }
.psi-link:hover { text-decoration: underline; }
.psi-choose { display: flex; flex-direction: column; gap: 10px; }
.psi-server { border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; }
.psi-server-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.psi-tag { font-size: 11px; padding: 1px 6px; border-radius: 6px; background: rgba(255, 255, 255, 0.08); color: var(--text-muted, #888); }
.psi-server-row { display: flex; gap: 8px; flex-wrap: wrap; }
.psi-select {
  flex: 1 1 260px; min-width: 0; padding: 7px 9px; border-radius: 6px;
  background: rgba(255, 255, 255, 0.04); border: 1px solid var(--border, #2a2f3e);
  color: var(--text-primary, #fff); font-size: 13px;
}
.psi-spinner {
  width: 14px; height: 14px; border-radius: 50%;
  border: 2px solid rgba(229, 160, 13, 0.3); border-top-color: #e5a00d;
  animation: psi-spin 0.8s linear infinite;
}
@keyframes psi-spin { to { transform: rotate(360deg); } }
</style>
