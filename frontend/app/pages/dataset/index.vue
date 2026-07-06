<template>
  <div>
    <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-gray-100">Dataset</h2>
    <p class="text-sm text-gray-600 dark:text-gray-400 mb-4">
      Showing {{ filteredInstances.length }} instance(s).
    </p>

    <div class="mb-4 max-w-md">
      <SearchBox v-model="searchQuery" placeholder="Search dataset…" />
    </div>

    <div v-if="store.loading" class="text-gray-500 dark:text-gray-400">Loading…</div>
    <p v-else-if="store.error" class="text-red-600 dark:text-red-400">{{ store.error }}</p>
    <div v-else-if="filteredInstances.length">
      <table class="w-full border-collapse border border-gray-300 dark:border-gray-600">
        <thead>
          <tr class="bg-gray-50 dark:bg-gray-700">
            <th class="border border-gray-300 dark:border-gray-600 p-2 text-left text-gray-700 dark:text-gray-300">Name
            </th>
            <th class="border border-gray-300 dark:border-gray-600 p-2 text-left text-gray-700 dark:text-gray-300">Types
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="inst in filteredInstances" :key="inst.uri" class="hover:bg-gray-50 dark:hover:bg-gray-800">
            <td class="border border-gray-300 dark:border-gray-600 p-2 text-sm">
              <NuxtLink v-if="inst.uri && inst.uri !== 'undefined'"
                :to="`/dataset/data?uri=${encodeURIComponent(inst.uri)}`"
                class="text-blue-600 dark:text-blue-400 hover:underline block leading-6">
                {{ instanceDisplayName(inst) }}
              </NuxtLink>
            </td>
            <td class="border border-gray-300 dark:border-gray-600 p-2 text-sm text-gray-700 dark:text-gray-300">
              <template v-for="(t, idx) in inst.types" :key="t">
                <a :href="t" target="_blank" class="hover:underline">{{ formatUri(t) }}</a>
                <span v-if="idx < inst.types.length - 1">, </span>
              </template>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="text-gray-500 dark:text-gray-400">No instances available.</p>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useAppStore } from '@/stores/app'
import { usePublicDisplay } from '@/composables/usePublicDisplay'
import SearchBox from '@/components/shared/SearchBox.vue'

const searchQuery = ref('')

const store = useAppStore()
const { formatUri } = usePublicDisplay()

function instanceDisplayName(inst: any): string {
  return inst.label || formatUri(inst.uri)
}

onMounted(async () => {
  if (!store.isReady) await store.fetchState()
})

const filteredInstances = computed(() => {
  let list = store.instances.filter(
    (inst: any) =>
      inst.uri &&
      inst.uri !== 'undefined' &&
      (inst.uri.startsWith('http') || inst.uri.startsWith('urn:'))
  )

  if (!store.publicShowBlankNodes) {
    list = list.filter((inst: any) => !inst.is_blank)
  }

  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase().trim()
    list = list.filter((inst: any) => {
      const name = instanceDisplayName(inst).toLowerCase()
      return name.includes(q) || inst.uri.toLowerCase().includes(q)
    })
  }

  // Sort starred instances first
  const starred = list.filter((inst: any) => inst.starred)
  const unstarred = list.filter((inst: any) => !inst.starred)
  list = [...starred, ...unstarred]

  return list
})

useHead({ title: 'Dataset' })
</script>