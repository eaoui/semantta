<template>
  <nav
    class="w-56 bg-slate-100 dark:bg-slate-800 border-r border-slate-300 dark:border-slate-700 px-2 py-4 flex flex-col gap-1">
    <NuxtLink to="/admin"
      class="flex items-center mb-4 gap-1 p-1 text-cyan-950 dark:text-cyan-50 hover:text-cyan-500 transition-colors">
      <svg viewBox="0 0 256 256" fill="#06b6d4" width="32px" height="32px">
        <polygon points="32,224 48,192 176,192 160,160 64,160 128,32 160,96 128,96 112,128 176,128 224,224 " />
      </svg>
      <h1 class="text-xl font-bold pt-1 transition-colors">Semantta</h1>
    </NuxtLink>

    <NuxtLink to="/admin/ontologies"
      class="flex items-center gap-2 p-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 dark:text-slate-300"
      active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">
      <PhosphorIcon name="graph" :size="24" color="currentColor" aria-hidden="true" />
      <span>Ontologies</span>
    </NuxtLink>

    <NuxtLink to="/admin/profile"
      class="flex items-center gap-2 p-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 dark:text-slate-300"
      active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">
      <PhosphorIcon name="crosshair" :size="24" color="currentColor" aria-hidden="true" />
      <span>Application Profile</span>
    </NuxtLink>

    <!-- Metadata submenu -->
    <div>
      <button @click="metadataOpen = !metadataOpen"
        class="flex items-center justify-between w-full p-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-left dark:text-slate-300"
        :class="{ 'bg-slate-300 dark:bg-slate-600 dark:text-white': isMetadataActive }">
        <span class="flex items-center gap-2">
          <PhosphorIcon name="database" :size="24" color="currentColor" aria-hidden="true" />
          <span>Metadata</span>
        </span>
        <svg class="w-4 h-4 transition-transform" :class="{ 'rotate-90': metadataOpen }" fill="none"
          stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </button>
      <div v-show="metadataOpen" class="ml-4 flex flex-col gap-1 mt-1">
        <NuxtLink to="/admin/metadata/instances"
          class="block px-3 py-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-sm dark:text-slate-300"
          active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">Instances</NuxtLink>
        <NuxtLink to="/admin/metadata/create"
          class="block px-3 py-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-sm dark:text-slate-300"
          active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">Create</NuxtLink>
        <NuxtLink to="/admin/metadata/imports"
          class="block px-3 py-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-sm dark:text-slate-300"
          active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">Imports</NuxtLink>
      </div>
    </div>

    <!-- Plugins -->
    <NuxtLink to="/admin/plugins"
      class="flex items-center gap-2 p-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 dark:text-slate-300"
      active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">
      <PhosphorIcon name="plug" :size="24" color="currentColor" aria-hidden="true" />
      <span>Plugins</span>
    </NuxtLink>

    <!-- Themes -->
    <NuxtLink to="/admin/themes"
      class="flex items-center gap-2 p-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 dark:text-slate-300"
      active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">
      <PhosphorIcon name="swatches" :size="24" color="currentColor" aria-hidden="true" />
      <span>Themes</span>
    </NuxtLink>

    <!-- Preferences submenu -->
    <div>
      <button @click="prefsOpen = !prefsOpen"
        class="flex items-center justify-between w-full p-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-left dark:text-slate-300"
        :class="{ 'bg-slate-300 dark:bg-slate-600 dark:text-white': isPrefsActive }">
        <span class="flex items-center gap-2">
          <PhosphorIcon name="sliders-horizontal" :size="24" color="currentColor" aria-hidden="true" />
          <span>Preferences</span>
        </span>
        <svg class="w-4 h-4 transition-transform" :class="{ 'rotate-90': prefsOpen }" fill="none" stroke="currentColor"
          viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </button>
      <div v-show="prefsOpen" class="ml-4 flex flex-col gap-1 mt-1">
        <NuxtLink to="/admin/preferences/display"
          class="block px-3 py-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-sm dark:text-slate-300"
          active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">Display</NuxtLink>
      </div>
    </div>

    <!-- Settings submenu -->
    <div>
      <button @click="settingsOpen = !settingsOpen"
        class="flex items-center justify-between w-full p-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-left dark:text-slate-300"
        :class="{ 'bg-slate-300 dark:bg-slate-600 dark:text-white': isSettingsActive }">
        <span class="flex items-center gap-2">
          <PhosphorIcon name="gear" :size="24" color="currentColor" aria-hidden="true" />
          <span>Settings</span>
        </span>
        <svg class="w-4 h-4 transition-transform" :class="{ 'rotate-90': settingsOpen }" fill="none"
          stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
        </svg>
      </button>
      <div v-show="settingsOpen" class="ml-4 flex flex-col gap-1 mt-1">
        <NuxtLink to="/admin/settings/general"
          class="block px-3 py-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-sm dark:text-slate-300"
          active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">General</NuxtLink>
        <NuxtLink to="/admin/settings/advanced"
          class="block px-3 py-2 rounded hover:bg-slate-200 dark:hover:bg-slate-700 text-sm dark:text-slate-300"
          active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">Advanced</NuxtLink>
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