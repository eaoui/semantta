<template>
  <!-- Fixed layout width on small screens; full width on lg+. -->
  <div class="relative z-50 h-screen w-16 shrink-0 bg-slate-100 dark:bg-slate-800 lg:w-56">
    <nav
      class="group absolute inset-y-0 left-0 z-50 flex w-16 flex-col gap-1 overflow-x-hidden overflow-y-auto whitespace-nowrap bg-slate-100 px-2 py-4 transition-[width] duration-200 ease-in-out hover:w-56 hover:shadow-md dark:bg-slate-800 lg:static lg:inset-auto lg:h-screen lg:w-56 lg:overflow-x-hidden lg:overflow-y-auto lg:shadow-none">
      <!-- Semantta Home -->
      <NuxtLink to="/admin"
        class="mb-4 flex items-center justify-center gap-1 p-1 text-cyan-950 transition-colors hover:text-cyan-500 dark:text-cyan-50 lg:justify-start group-hover:justify-start">
        <svg viewBox="0 0 256 256" fill="#06b6d4" width="32px" height="32px" class="shrink-0">
          <polygon points="32,224 48,192 176,192 160,160 64,160 128,32 160,96 128,96 112,128 176,128 224,224 " />
        </svg>
        <h1 class="hidden pt-1 text-xl font-bold transition-colors group-hover:block lg:block">
          Semantta
        </h1>
      </NuxtLink>

      <!-- Ontologies -->
      <NuxtLink to="/admin/ontologies"
        class="flex items-center justify-center gap-2 rounded p-2 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700 lg:justify-start group-hover:justify-start"
        active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">
        <PhosphorIcon name="graph" :size="24" color="currentColor" aria-hidden="true" class="shrink-0" />
        <span class="hidden group-hover:inline lg:inline">Ontologies</span>
      </NuxtLink>

      <!-- Application Profile -->
      <NuxtLink to="/admin/profile"
        class="flex items-center justify-center gap-2 rounded p-2 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700 lg:justify-start group-hover:justify-start"
        active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">
        <PhosphorIcon name="crosshair" :size="24" color="currentColor" aria-hidden="true" class="shrink-0" />
        <span class="hidden group-hover:inline lg:inline">Application Profile</span>
      </NuxtLink>

      <!-- Metadata submenu -->
      <div>
        <button @click="metadataOpen = !metadataOpen"
          class="flex w-full items-center justify-center rounded p-2 text-left hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700 lg:justify-between group-hover:justify-between"
          :class="{ 'bg-slate-300 dark:bg-slate-600 dark:text-white': isMetadataActive }">
          <span class="flex items-center gap-2">
            <PhosphorIcon name="database" :size="24" color="currentColor" aria-hidden="true" class="shrink-0" />
            <span class="hidden group-hover:inline lg:inline">Metadata</span>
          </span>
          <svg class="hidden h-4 w-4 shrink-0 transition-transform group-hover:block lg:block"
            :class="{ 'rotate-90': metadataOpen }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
          </svg>
        </button>

        <div v-if="metadataOpen" class="ml-4 mt-1 hidden flex-col gap-1 group-hover:flex lg:flex">
          <NuxtLink to="/admin/metadata/instances"
            class="block rounded px-3 py-2 text-sm hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700"
            active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">Instances</NuxtLink>
          <NuxtLink to="/admin/metadata/create"
            class="block rounded px-3 py-2 text-sm hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700"
            active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">Create</NuxtLink>
          <NuxtLink to="/admin/metadata/imports"
            class="block rounded px-3 py-2 text-sm hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700"
            active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">Imports</NuxtLink>
        </div>
      </div>

      <!-- Plugins -->
      <NuxtLink to="/admin/plugins"
        class="flex items-center justify-center gap-2 rounded p-2 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700 lg:justify-start group-hover:justify-start"
        active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">
        <PhosphorIcon name="plug" :size="24" color="currentColor" aria-hidden="true" class="shrink-0" />
        <span class="hidden group-hover:inline lg:inline">Plugins</span>
      </NuxtLink>

      <!-- Themes -->
      <NuxtLink to="/admin/themes"
        class="flex items-center justify-center gap-2 rounded p-2 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700 lg:justify-start group-hover:justify-start"
        active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">
        <PhosphorIcon name="swatches" :size="24" color="currentColor" aria-hidden="true" class="shrink-0" />
        <span class="hidden group-hover:inline lg:inline">Themes</span>
      </NuxtLink>

      <!-- Preferences submenu -->
      <div>
        <button @click="prefsOpen = !prefsOpen"
          class="flex w-full items-center justify-center rounded p-2 text-left hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700 lg:justify-between group-hover:justify-between"
          :class="{ 'bg-slate-300 dark:bg-slate-600 dark:text-white': isPrefsActive }">
          <span class="flex items-center gap-2">
            <PhosphorIcon name="sliders-horizontal" :size="24" color="currentColor" aria-hidden="true"
              class="shrink-0" />
            <span class="hidden group-hover:inline lg:inline">Preferences</span>
          </span>
          <svg class="hidden h-4 w-4 shrink-0 transition-transform group-hover:block lg:block"
            :class="{ 'rotate-90': prefsOpen }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
          </svg>
        </button>

        <div v-if="prefsOpen" class="ml-4 mt-1 hidden flex-col gap-1 group-hover:flex lg:flex">
          <NuxtLink to="/admin/preferences/display"
            class="block rounded px-3 py-2 text-sm hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700"
            active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">Display</NuxtLink>
        </div>
      </div>

      <!-- Settings submenu -->
      <div>
        <button @click="settingsOpen = !settingsOpen"
          class="flex w-full items-center justify-center rounded p-2 text-left hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700 lg:justify-between group-hover:justify-between"
          :class="{ 'bg-slate-300 dark:bg-slate-600 dark:text-white': isSettingsActive }">
          <span class="flex items-center gap-2">
            <PhosphorIcon name="gear" :size="24" color="currentColor" aria-hidden="true" class="shrink-0" />
            <span class="hidden group-hover:inline lg:inline">Settings</span>
          </span>
          <svg class="hidden h-4 w-4 shrink-0 transition-transform group-hover:block lg:block"
            :class="{ 'rotate-90': settingsOpen }" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
          </svg>
        </button>

        <div v-if="settingsOpen" class="ml-4 mt-1 hidden flex-col gap-1 group-hover:flex lg:flex">
          <NuxtLink to="/admin/settings/general"
            class="block rounded px-3 py-2 text-sm hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700"
            active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">General</NuxtLink>
          <NuxtLink to="/admin/settings/advanced"
            class="block rounded px-3 py-2 text-sm hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-700"
            active-class="bg-slate-300 dark:bg-slate-600 dark:text-white">Advanced</NuxtLink>
        </div>
      </div>
    </nav>
  </div>
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