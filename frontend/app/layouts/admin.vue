<template>
  <div class="flex h-screen">
    <AdminAppSidebar />
    <main class="flex-1 p-6 overflow-y-auto bg-white dark:bg-gray-900">
      <NuxtPage :key="store.displayFormat" />
    </main>
    <Toaster richColors expand :duration="7000" close-button />
  </div>
</template>

<script setup lang="ts">
import { useAppStore } from '@/stores/app'
import { Toaster } from 'vue-sonner'

const store = useAppStore()
</script>