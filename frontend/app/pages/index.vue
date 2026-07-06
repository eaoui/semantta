<template>
  <div>
    <div class="text-center">
      <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-gray-100">Hello Semantic World!</h2>
      <div class="mt-6 max-w-md mx-auto">
        <SearchBox v-model="homeSearch" placeholder="Search…" />
      </div>
    </div>

    <!-- Search results (shown only when there is a query) -->
    <div v-if="homeSearch.trim()">
      <h3 class="text-lg font-semibold mb-4 mt-8 text-gray-900 dark:text-gray-100">
        Search results ({{ filteredInstances.length }})
      </h3>
      <div v-if="filteredInstances.length" class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <InstanceCard v-for="inst in filteredInstances" :key="inst.uri" :instance="inst" />
      </div>
      <p v-else class="text-gray-500 dark:text-gray-400">No matching instances found.</p>
    </div>

    <!-- Default content (only when not searching) -->
    <template v-else>
      <!-- Starred Instances -->
      <div v-if="starredInstances.length" class="mt-8">
        <h3 class="text-lg font-semibold mb-4 text-gray-900 dark:text-gray-100">Featured</h3>
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <InstanceCard v-for="inst in starredInstances" :key="inst.uri" :instance="inst" />
        </div>
      </div>
      <NuxtLink to="/dataset" class="text-blue-600 dark:text-blue-400 hover:underline mt-4 block">
        Browse full dataset →
      </NuxtLink>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import InstanceCard from '@/components/public/InstanceCard.vue'
import SearchBox from '@/components/shared/SearchBox.vue'

const store = useAppStore()
const homeSearch = ref('')

onMounted(async () => {
  if (!store.isReady) await store.fetchState()
})

const starredInstances = computed(() =>
  store.instances.filter((inst) => inst.starred)
)

/** Filter all valid instances by the search query (label or URI) */
const filteredInstances = computed(() => {
  const q = homeSearch.value.trim().toLowerCase()
  const valid = store.instances.filter(
    (inst) =>
      inst.uri &&
      inst.uri !== 'undefined' &&
      (inst.uri.startsWith('http') || inst.uri.startsWith('urn:')) &&
      !inst.is_blank
  )

  if (!q) return []
  return valid.filter((inst) => {
    const label = (inst.label || inst.uri).toLowerCase()
    return label.includes(q) || inst.uri.toLowerCase().includes(q)
  })
})
</script>