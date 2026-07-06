<template>
  <div
    class="mb-6 p-4 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100">
    <h3 class="font-semibold mb-2">{{ title }}</h3>
    <div class="flex gap-2">
      <input type="file" :accept="accept" ref="fileInput" @change="onFileChange"
        class="border border-gray-300 dark:border-gray-600 rounded p-1 dark:bg-gray-700 dark:text-gray-100" />
      <button @click="upload" :disabled="!file"
        class="bg-blue-600 text-white px-4 py-1 rounded disabled:opacity-50 disabled:cursor-not-allowed hover:bg-blue-700">
        {{ buttonText }}
      </button>
    </div>
    <p v-if="error" class="text-red-600 dark:text-red-400 mt-1">{{ error }}</p>
    <slot />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(defineProps<{
  title: string
  accept?: string
  buttonText?: string
}>(), {
  accept: '.rdf,.owl,.xml,.ttl,.nt,.nq,.jsonld,.json,.trig,.trix',
  buttonText: 'Import'
})

const emit = defineEmits<{ (e: 'upload', file: File): void }>()

const file = ref<File | null>(null)
const fileInput = ref<HTMLInputElement>()
const error = ref('')

function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files?.[0]) {
    file.value = target.files[0]
    error.value = ''
  }
}

function upload() {
  if (!file.value) return
  try {
    emit('upload', file.value)
    file.value = null
    if (fileInput.value) fileInput.value.value = ''
    error.value = ''
  } catch (e: any) {
    error.value = e.message
  }
}
</script>