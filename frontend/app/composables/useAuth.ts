import { ref } from 'vue'

/**
 * Mock authentication – always logged in as admin.
 * Replace with a real auth provider when needed.
 */
const mockUser = ref({
  name: 'User Name',
  role: 'admin',
})

const isLoggedIn = ref(true)

export const useAuth = () => {
  return {
    isLoggedIn,
    user: mockUser,
    session: ref(null),
  }
}