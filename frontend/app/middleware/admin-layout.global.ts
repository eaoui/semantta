export default defineNuxtRouteMiddleware((to) => {
  if (to.path.startsWith('/admin')) {
    setPageLayout('admin')
  }
})