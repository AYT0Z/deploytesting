import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import client, { setAuthHeader } from '@/api/client'

const STORAGE_KEY = 'watchtogether_auth'

function userIdFromAccessToken(token) {
  if (!token || typeof token !== 'string') return null
  try {
    const payload = token.split('.')[1]
    if (!payload) return null
    const b64 = payload.replace(/-/g, '+').replace(/_/g, '/')
    const pad = b64.length % 4 ? '='.repeat(4 - (b64.length % 4)) : ''
    const json = atob(b64 + pad)
    const data = JSON.parse(json)
    const id = data.user_id ?? data.userId ?? data.sub
    return id != null ? Number(id) : null
  } catch {
    return null
  }
}

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref('')
  const refreshToken = ref('')
  const username = ref('')

  const isAuthenticated = computed(() => Boolean(accessToken.value))
  const userId = computed(() => userIdFromAccessToken(accessToken.value))

  function loadFromStorage() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return
      const data = JSON.parse(raw)
      accessToken.value = data.access || ''
      refreshToken.value = data.refresh || ''
      username.value = data.username || ''
      setAuthHeader(accessToken.value)
    } catch {
      /* ignore */
    }
  }

  function persist() {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        access: accessToken.value,
        refresh: refreshToken.value,
        username: username.value,
      }),
    )
    setAuthHeader(accessToken.value)
  }

  async function register(payload) {
    await client.post('/api/auth/register/', payload)
    await login({ username: payload.username, password: payload.password })
  }

  async function login(payload) {
    const { data } = await client.post('/api/token/', payload)
    accessToken.value = data.access
    refreshToken.value = data.refresh
    username.value = payload.username
    persist()
  }

  async function refreshAccess() {
    if (!refreshToken.value) throw new Error('no refresh')
    const { data } = await client.post('/api/token/refresh/', {
      refresh: refreshToken.value,
    })
    accessToken.value = data.access
    persist()
  }

  function logout() {
    accessToken.value = ''
    refreshToken.value = ''
    username.value = ''
    localStorage.removeItem(STORAGE_KEY)
    setAuthHeader('')
  }

  loadFromStorage()

  return {
    accessToken,
    refreshToken,
    username,
    userId,
    isAuthenticated,
    register,
    login,
    refreshAccess,
    logout,
    loadFromStorage,
  }
})
