import { defineStore } from 'pinia'
import { ref } from 'vue'
import client from '@/api/client'

export const useRoomStore = defineStore('room', () => {
  const current = ref(null)
  const loading = ref(false)
  const error = ref('')

  async function fetchRoom(slug) {
    loading.value = true
    error.value = ''
    try {
      const { data } = await client.get(`/api/rooms/${slug}/`)
      current.value = data
      return data
    } catch (e) {
      error.value = e.response?.data?.detail || 'Комната не найдена'
      current.value = null
      throw e
    } finally {
      loading.value = false
    }
  }

  async function createRoom(payload) {
    const { data } = await client.post('/api/rooms/', payload)
    return data
  }

  function clear() {
    current.value = null
    error.value = ''
  }

  return { current, loading, error, fetchRoom, createRoom, clear }
})
