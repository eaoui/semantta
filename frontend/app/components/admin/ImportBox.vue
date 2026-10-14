<template>
  <div
    class="mb-6 p-4 border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100">
    <h3 class="font-semibold mb-2">{{ title }}</h3>
    <div class="flex gap-2">
      <input type="file" :accept="accept" :multiple="multiple" :disabled="disabled" ref="fileInput"
        @change="onFileChange"
        class="border border-gray-300 dark:border-gray-600 rounded p-1 dark:bg-gray-700 dark:text-gray-100" />
      <button @click="upload" :disabled="disabled || files.length === 0"
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
  multiple?: boolean
  disabled?: boolean
}>(), {
  accept: '.rdf,.owl,.xml,.ttl,.nt,.nq,.jsonld,.json,.trig,.trix',
  buttonText: 'Import',
  multiple: false,
  disabled: false,
})

const emit = defineEmits<{
  (e: 'upload', file: File): void
  (e: 'upload-multiple', files: File[]): void
}>()

const files = ref<File[]>([])
const fileInput = ref<HTMLInputElement>()
const error = ref('')

function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  const selectedFiles = Array.from(target.files ?? [])

  files.value = props.multiple
    ? selectedFiles
    : selectedFiles.slice(0, 1)

  error.value = ''
}

function upload() {
  if (props.disabled || files.value.length === 0) return

  const selectedFiles = [...files.value]

  try {
    if (props.multiple) {
      emit('upload-multiple', selectedFiles)
    } else {
      const selectedFile = selectedFiles[0]
      if (!selectedFile) return

      emit('upload', selectedFile)
    }

    files.value = []

    if (fileInput.value) {
      fileInput.value.value = ''
    }

    error.value = ''
  } catch (e: unknown) {
    error.value = e instanceof Error
      ? e.message
      : 'Could not start the upload.'
  }
}
</script>