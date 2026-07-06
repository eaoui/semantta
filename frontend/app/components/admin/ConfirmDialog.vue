<template>
  <div v-if="show" class="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
    <div class="bg-white dark:bg-gray-800 p-6 rounded shadow-lg max-w-sm w-full text-gray-900 dark:text-gray-100">
      <p class="mb-4">{{ message }}</p>
      <div class="flex justify-end gap-2">
        <button @click="$emit('cancel')"
          class="px-4 py-2 bg-gray-200 dark:bg-gray-600 dark:hover:bg-gray-500 rounded hover:bg-gray-300 dark:text-gray-200">Cancel</button>
        <button @click="$emit('confirm')"
          class="px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700">Delete</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ show: boolean; message: string }>()
defineEmits<{ confirm: []; cancel: [] }>()
</script>