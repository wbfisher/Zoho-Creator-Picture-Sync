import { create } from 'zustand'
import type { User } from '@/types'

interface AuthStore {
  // State
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  error: string | null

  // Actions
  setUser: (user: User | null) => void
  setLoading: (loading: boolean) => void
  setError: (error: string | null) => void
  checkAuth: () => Promise<boolean>
  logout: () => Promise<void>
}

export const useAuthStore = create<AuthStore>((set) => ({
  user: null,
  isLoading: true,
  isAuthenticated: false,
  error: null,

  setUser: (user) =>
    set({
      user,
      isAuthenticated: !!user,
      isLoading: false,
    }),

  setLoading: (isLoading) => set({ isLoading }),

  setError: (error) => set({ error }),

  checkAuth: async () => {
    set({ isLoading: true, error: null })
    try {
      const response = await fetch('/api/auth/check', {
        credentials: 'include',
      })

      if (!response.ok) {
        throw new Error('Auth check failed')
      }

      const data = await response.json()

      if (data.authenticated && data.user) {
        set({
          user: data.user,
          isAuthenticated: true,
          isLoading: false,
        })
        return true
      } else {
        set({
          user: null,
          isAuthenticated: false,
          isLoading: false,
        })
        return false
      }
    } catch (error) {
      set({
        user: null,
        isAuthenticated: false,
        isLoading: false,
        error: error instanceof Error ? error.message : 'Auth check failed',
      })
      return false
    }
  },

  logout: async () => {
    try {
      await fetch('/api/auth/logout', {
        method: 'POST',
        credentials: 'include',
      })
    } finally {
      set({
        user: null,
        isAuthenticated: false,
      })
      // Redirect to login page
      window.location.href = '/login'
    }
  },
}))
