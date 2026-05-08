import { defineStore } from 'pinia'
import { ref, computed } from 'vue'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('token') || '')
  const username = ref(localStorage.getItem('username') || '')
  const name = ref(localStorage.getItem('name') || '')

  const isLoggedIn = computed(() => !!token.value)

  function setSession(payload) {
    token.value = payload.token || ''
    username.value = payload.username || ''
    name.value = payload.name || payload.username || ''
    localStorage.setItem('token', token.value)
    localStorage.setItem('username', username.value)
    localStorage.setItem('name', name.value)
  }

  function logout() {
    token.value = ''
    username.value = ''
    name.value = ''
    localStorage.removeItem('token')
    localStorage.removeItem('username')
    localStorage.removeItem('name')
  }

  return { token, username, name, isLoggedIn, setSession, logout }
})
