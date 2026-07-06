<template>
  <nav class="w-56 bg-gray-100 dark:bg-gray-800 border-r border-gray-300 dark:border-gray-700 p-4 flex flex-col gap-1">
    <div class="flex items-center mb-4 gap-2">
      <svg viewBox="0 0 256 256" fill="#06b6d4" width="32px" height="32px">
        <polygon points="32,224 48,192 176,192 160,160 64,160 128,32 160,96 128,96 112,128 176,128 224,224 " />
      </svg>
      <h1 class="text-lg font-bold text-gray-900 dark:text-gray-100 pt-1">Semantta</h1>
    </div>

    <NuxtLink to="/admin" class="block px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700 dark:text-gray-300"
      exact-active-class="bg-gray-300 dark:bg-gray-600 font-semibold dark:text-white">
      Home
    </NuxtLink>

    <NuxtLink to="/admin/ontologies"
      class="block px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700 dark:text-gray-300"
      active-class="bg-gray-300 dark:bg-gray-600 font-semibold dark:text-white">Ontologies</NuxtLink>

    <NuxtLink to="/admin/profile"
      class="block px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700 dark:text-gray-300"
      active-class="bg-gray-300 dark:bg-gray-600 font-semibold dark:text-white">Application Profile</NuxtLink>

    <!-- Metadata submenu -->
    <div>
      <button @click="metadataOpen = !metadataOpen"
        class="flex items-center justify-between w-full px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-left dark:text-gray-300"
        :class="{ 'bg-gray-300 dark:bg-gray-600 font-semibold dark:text-white': isMetadataActive }">
        <span>Metadata</span>
        <svg class="w-4 h-4 transition-transform" :class="{ 'rotate-90': metadataOpen }" fill="none"
          stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </button>
      <div v-show="metadataOpen" class="ml-4 flex flex-col gap-1 mt-1">
        <NuxtLink to="/admin/metadata/instances"
          class="block px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-sm dark:text-gray-300"
          active-class="bg-gray-300 dark:bg-gray-600 font-semibold dark:text-white">Instances</NuxtLink>
        <NuxtLink to="/admin/metadata/create"
          class="block px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-sm dark:text-gray-300"
          active-class="bg-gray-300 dark:bg-gray-600 font-semibold dark:text-white">Create</NuxtLink>
        <NuxtLink to="/admin/metadata/imports"
          class="block px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-sm dark:text-gray-300"
          active-class="bg-gray-300 dark:bg-gray-600 font-semibold dark:text-white">Imports</NuxtLink>
      </div>
    </div>

    <!-- Plugins -->
    <NuxtLink to="/admin/plugins"
      class="block px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700 dark:text-gray-300"
      active-class="bg-gray-300 dark:bg-gray-600 font-semibold dark:text-white">Plugins</NuxtLink>

    <!-- Themes -->
    <NuxtLink to="/admin/themes"
      class="block px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700 dark:text-gray-300"
      active-class="bg-gray-300 dark:bg-gray-600 font-semibold dark:text-white">Themes</NuxtLink>

    <!-- Preferences submenu -->
    <div>
      <button @click="prefsOpen = !prefsOpen"
        class="flex items-center justify-between w-full px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-left dark:text-gray-300"
        :class="{ 'bg-gray-300 dark:bg-gray-600 font-semibold dark:text-white': isPrefsActive }">
        <span>Preferences</span>
        <svg class="w-4 h-4 transition-transform" :class="{ 'rotate-90': prefsOpen }" fill="none" stroke="currentColor"
          viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </button>
      <div v-show="prefsOpen" class="ml-4 flex flex-col gap-1 mt-1">
        <NuxtLink to="/admin/preferences/display"
          class="block px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-sm dark:text-gray-300"
          active-class="bg-gray-300 dark:bg-gray-600 font-semibold dark:text-white">Display</NuxtLink>
      </div>
    </div>

    <!-- Settings submenu -->
    <div>
      <button @click="settingsOpen = !settingsOpen"
        class="flex items-center justify-between w-full px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-left dark:text-gray-300"
        :class="{ 'bg-gray-300 dark:bg-gray-600 font-semibold dark:text-white': isSettingsActive }">
        <span>Settings</span>
        <svg class="w-4 h-4 transition-transform" :class="{ 'rotate-90': settingsOpen }" fill="none"
          stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </button>
      <div v-show="settingsOpen" class="ml-4 flex flex-col gap-1 mt-1">
        <NuxtLink to="/admin/settings/general"
          class="block px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-sm dark:text-gray-300"
          active-class="bg-gray-300 dark:bg-gray-600 font-semibold dark:text-white">General</NuxtLink>
        <NuxtLink to="/admin/settings/advanced"
          class="block px-3 py-2 rounded hover:bg-gray-200 dark:hover:bg-gray-700 text-sm dark:text-gray-300"
          active-class="bg-gray-300 dark:bg-gray-600 font-semibold dark:text-white">Advanced</NuxtLink>
      </div>
    </div>
  </nav>
</template>

<script setup lang="ts">
import { ref, watch, computed } from 'vue'
import { useRoute } from 'vue-router'
import { useAppStore } from '@/stores/app'

const route = useRoute()
const store = useAppStore()

const metadataOpen = ref(false)
const prefsOpen = ref(false)
const settingsOpen = ref(false)

// Auto‑open the relevant submenu based on the current route
watch(() => route.path, (path) => {
  metadataOpen.value = path.startsWith('/admin/metadata')
  prefsOpen.value = path.startsWith('/admin/preferences')
  settingsOpen.value = path.startsWith('/admin/settings')
}, { immediate: true })

const isMetadataActive = computed(() => route.path.startsWith('/admin/metadata'))
const isPrefsActive = computed(() => route.path.startsWith('/admin/preferences'))
const isSettingsActive = computed(() => route.path.startsWith('/admin/settings'))
</script>