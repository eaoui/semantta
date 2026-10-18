<template>
  <div class="flex min-h-full flex-col">
    <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-gray-100">Welcome to Semantta</h2>
    <p class="mb-4 text-gray-600 dark:text-gray-400">
      Ontology‑Based Linked Data Management System
    </p>

    <!-- Error state -->
    <div v-if="store.error" class="text-red-600 dark:text-red-400 mt-2">
      {{ store.error }}
      <button @click="store.fetchState()" class="ml-2 underline text-blue-600 dark:text-blue-400">Retry</button>
    </div>

    <!-- Stats -->
    <h3 class="text-lg font-semibold mb-2 text-gray-900 dark:text-gray-100">Stats</h3>
    <div
      class="p-4 bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 rounded space-y-1 max-w-xs text-gray-900 dark:text-gray-100">
      <p><strong>Ontologies imported:</strong> {{ store.loading ? '...' : store.ontologies.length }}</p>
      <p><strong>Active profile entities:</strong> {{ store.loading ? '...' : activeEntityCount }}</p>
      <p>
        <strong>Instances:</strong>
        {{ store.loading ? '...' : store.instanceTotal }}
      </p>
    </div>

    <!-- Link to public site -->
    <div class="mt-6">
      <NuxtLink to="/" class="text-blue-600 dark:text-blue-400 hover:underline" target="_blank">
        View public site →
      </NuxtLink>
    </div>

    <footer class="mt-auto flex flex-wrap items-center justify-between gap-4
         border-t border-gray-200/60 dark:border-gray-700/60 pt-4">

      <nav aria-label="Semantta project links" class="flex flex-wrap items-center gap-x-4 gap-y-2
           text-xs text-gray-500/90 dark:text-gray-400/90">
        <a href="https://github.com/eaoui/semantta" target="_blank" rel="noopener noreferrer"
          class="hover:text-gray-700 dark:hover:text-gray-200">
          Repository
        </a>

        <a href="https://github.com/eaoui/semantta/releases" target="_blank" rel="noopener noreferrer"
          class="hover:text-gray-700 dark:hover:text-gray-200">
          Releases
        </a>

        <a href="https://github.com/eaoui/semantta/issues" target="_blank" rel="noopener noreferrer"
          class="hover:text-gray-700 dark:hover:text-gray-200">
          Report an Issue
        </a>
      </nav>

      <span class="text-[11px] text-gray-400 dark:text-gray-500">
        Semantta v{{ appVersion }}
      </span>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useAppStore } from '@/stores/app'

const runtimeConfig = useRuntimeConfig()
const appVersion = runtimeConfig.public.appVersion

const store = useAppStore()

const activeEntityCount = computed(() =>
  store.profileEntities.filter(e => e.active).length
)
</script>