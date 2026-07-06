<template>
  <div
    class="border border-gray-300 dark:border-gray-600 rounded p-4 relative bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100">
    <!-- action buttons (top right) -->
    <div v-if="$slots.actions" class="flex gap-2 absolute top-4 right-4">
      <slot name="actions" />
    </div>

    <h4 class="font-medium text-lg">{{ title }}</h4>
    <p v-if="version" class="text-sm text-gray-600 dark:text-gray-400">v{{ version }}</p>
    <p v-if="description" class="text-sm text-gray-700 dark:text-gray-300 mt-1">{{ description }}</p>

    <slot />

    <div v-if="$slots.footer" class="mt-3 flex gap-2">
      <slot name="footer" />
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  title: string
  version?: string
  description?: string
}>()
</script>