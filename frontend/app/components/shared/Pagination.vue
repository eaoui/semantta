<template>
  <div class="flex items-center justify-between mt-4">
    <button :disabled="currentPage <= 1 || loading" class="px-3 py-1 rounded border
        border-gray-300 dark:border-gray-600
        bg-white dark:bg-gray-700
        text-gray-700 dark:text-gray-200
        hover:bg-gray-50 dark:hover:bg-gray-600
        disabled:opacity-50
        disabled:cursor-not-allowed" @click="goPrevious">
      Previous
    </button>

    <span class="text-sm text-gray-600 dark:text-gray-300">
      Page {{ currentPage }}
    </span>

    <button :disabled="!hasNext || loading" class="px-3 py-1 rounded border
        border-gray-300 dark:border-gray-600
        bg-white dark:bg-gray-700
        text-gray-700 dark:text-gray-200
        hover:bg-gray-50 dark:hover:bg-gray-600
        disabled:opacity-50
        disabled:cursor-not-allowed" @click="goNext">
      Next
    </button>
  </div>
</template>

<script setup lang="ts">
const props = defineProps<{
  currentPage: number
  hasNext: boolean
  loading?: boolean
}>()

const emit = defineEmits<{
  'page-change': [page: number]
}>()

function goPrevious() {
  if (
    props.currentPage <= 1 ||
    props.loading
  ) {
    return
  }

  emit('page-change', props.currentPage - 1)
}

function goNext() {
  if (
    !props.hasNext ||
    props.loading
  ) {
    return
  }

  emit('page-change', props.currentPage + 1)
}
</script>