// plugins/toast.client.ts
// Registers the vue‑sonner toast function as a global $toast helper.

import { toast } from 'vue-sonner'

export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.provide('toast', toast)
})