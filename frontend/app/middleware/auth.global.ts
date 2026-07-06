export default defineNuxtRouteMiddleware((to) => {
  // Allow unauthenticated access to the login page
  if (to.path === '/admin/login') return

  const { isLoggedIn } = useAuth()
  if (to.path.startsWith('/admin') && !isLoggedIn.value) {
    return navigateTo('/admin/login')
  }
})