```vue
<template>
  <div>
    <div class="text-center">
      <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-gray-100">
        Hello Semantic World!
      </h2>

      <div class="mt-6 max-w-md mx-auto">
        <SearchBox
          v-model="homeSearch"
          placeholder="Search…"
        />
      </div>
    </div>

    <!-- Search results -->
    <div v-if="searching">
      <h3
        class="text-lg font-semibold mb-4 mt-8 text-gray-900 dark:text-gray-100"
      >
        Search results
        <span v-if="searchResultsTotal > 0">
          ({{ searchResultsTotal }})
        </span>
      </h3>

      <div
        v-if="searchResultsLoading"
        class="text-gray-500 dark:text-gray-400"
      >
        Searching…
      </div>

      <p
        v-else-if="searchResultsError"
        class="text-red-600 dark:text-red-400"
      >
        {{ searchResultsError }}
      </p>

      <div
        v-else-if="searchResults.length"
        class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
      >
        <InstanceCard
          v-for="inst in searchResults"
          :key="inst.uri"
          :instance="inst"
        />
      </div>

      <p
        v-else
        class="text-gray-500 dark:text-gray-400"
      >
        No matching instances found.
      </p>
    </div>

    <!-- Default content -->
    <template v-else>
      <!-- Featured instances -->
      <div
        v-if="featuredLoading"
        class="mt-8 text-gray-500 dark:text-gray-400"
      >
        Loading featured instances…
      </div>

      <p
        v-else-if="featuredError"
        class="mt-8 text-red-600 dark:text-red-400"
      >
        {{ featuredError }}
      </p>

      <div
        v-else-if="starredInstances.length"
        class="mt-8"
      >
        <h3
          class="text-lg font-semibold mb-4 text-gray-900 dark:text-gray-100"
        >
          Featured
        </h3>

        <div
          class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4"
        >
          <InstanceCard
            v-for="inst in starredInstances"
            :key="inst.uri"
            :instance="inst"
          />
        </div>
      </div>

      <NuxtLink
        to="/dataset"
        class="text-blue-600 dark:text-blue-400 hover:underline mt-4 block"
      >
        Browse full dataset →
      </NuxtLink>
    </template>
  </div>
</template>

<script setup lang="ts">
import {
  ref,
  computed,
  onMounted,
  watch,
} from 'vue'

import type { Instance } from '@/types'

import InstanceCard from '@/components/public/InstanceCard.vue'
import SearchBox from '@/components/shared/SearchBox.vue'

const api = useApi()

const homeSearch = ref('')

const starredInstances = ref<Instance[]>([])
const searchResults = ref<Instance[]>([])

const featuredLoading = ref(false)
const featuredError = ref<string | null>(null)

const searchResultsLoading = ref(false)
const searchResultsError = ref<string | null>(null)
const searchResultsTotal = ref(0)

const searching = computed(() =>
  homeSearch.value.trim().length > 0,
)

async function loadFeatured() {
  featuredLoading.value = true
  featuredError.value = null

  try {
    const data = await api.fetchInstances({
      limit: 12,
      starred: true,
    })

    starredInstances.value = data.instances
  } catch (error: any) {
    featuredError.value =
      error?.message ||
      'Failed to load featured instances.'
  } finally {
    featuredLoading.value = false
  }
}

async function searchInstances() {
  const query = homeSearch.value.trim()

  if (!query) {
    searchResults.value = []
    searchResultsTotal.value = 0
    searchResultsError.value = null
    return
  }

  searchResultsLoading.value = true
  searchResultsError.value = null

  try {
    const data = await api.fetchInstances({
      limit: 24,
      offset: 0,
      search: query,
    })

    searchResults.value = data.instances
    searchResultsTotal.value = data.total
  } catch (error: any) {
    searchResults.value = []
    searchResultsTotal.value = 0
    searchResultsError.value =
      error?.message ||
      'Failed to search instances.'
  } finally {
    searchResultsLoading.value = false
  }
}

watch(
  homeSearch,
  async () => {
    await searchInstances()
  },
)

onMounted(async () => {
  await loadFeatured()
})

useHead({
  title: 'Semantta',
})
</script>
```
