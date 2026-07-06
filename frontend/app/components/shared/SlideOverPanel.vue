<template>
  <!-- Backdrop -->
  <Transition enter-active-class="transition-opacity duration-300" leave-active-class="transition-opacity duration-300"
    enter-from-class="opacity-0" leave-to-class="opacity-0">
    <div v-if="show" class="fixed inset-0 bg-black/50 z-40" @click="$emit('close')" />
  </Transition>

  <!-- Panel -->
  <Transition enter-active-class="transition-transform duration-300 ease-in-out"
    leave-active-class="transition-transform duration-300 ease-in-out" enter-from-class="translate-x-full"
    leave-to-class="translate-x-full">
    <div v-if="show" class="fixed inset-y-0 right-0 z-50 w-full bg-white dark:bg-gray-800
             shadow-xl overflow-y-auto overscroll-contain p-6" :class="panelWidthClass">
      <button @click="$emit('close')" class="absolute top-4 right-4 text-gray-500 dark:text-gray-400
               hover:text-gray-700 dark:hover:text-gray-200 text-xl">
        ✕
      </button>
      <slot />
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  show: boolean
  level?: number   // 0 = outermost, 1 = first nested, etc.
}>()

defineEmits<{ close: [] }>()

const panelWidthClass = computed(() => {
  const level = props.level || 0
  const widths = ['max-w-3xl', 'max-w-2xl', 'max-w-xl', 'max-w-lg']
  return widths[level] || 'max-w-md'
})
</script>