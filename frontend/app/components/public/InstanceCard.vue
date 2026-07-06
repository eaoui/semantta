<template>
  <NuxtLink :to="`/dataset/data?uri=${encodeURIComponent(instance.uri)}`"
    class="block border border-gray-200 dark:border-gray-700 rounded p-3 bg-white dark:bg-gray-800 hover:shadow-md transition-shadow">
    <p class="text-sm text-gray-600 dark:text-gray-400 mb-1">
      {{instance.types.map((t: string) => formatUri(t)).join(', ')}}
    </p>
    <h4 class="font-semibold text-gray-900 dark:text-gray-100">
      {{ instance.label || formatUri(instance.uri) }}
    </h4>
  </NuxtLink>
</template>

<script setup lang="ts">
import { usePublicDisplay } from '@/composables/usePublicDisplay'

defineProps<{ instance: any }>()

const { formatUri } = usePublicDisplay()
</script>