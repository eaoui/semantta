import type { Toast } from 'vue-sonner'

declare module '#app' {
  interface NuxtApp {
    $toast: Toast
  }
}