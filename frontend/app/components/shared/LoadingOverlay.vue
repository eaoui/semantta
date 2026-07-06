<template>
  <Transition enter-active-class="transition-opacity duration-200" leave-active-class="transition-opacity duration-200"
    enter-from-class="opacity-0" leave-to-class="opacity-0">
    <div v-if="show" class="fixed inset-0 z-50 flex flex-col items-center justify-center
             bg-white/80 dark:bg-gray-900/80 backdrop-blur-sm">
      <PhosphorIcon name="circle-notch" size="48" class="animate-spin text-gray-600 dark:text-gray-300 mb-4" />
      <p class="text-lg font-semibold text-gray-700 dark:text-gray-200">
        Loading
      </p>
      <p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
        {{ message }}
      </p>
    </div>
  </Transition>
</template>

<script setup lang="ts">
defineProps<{
  show: boolean
  message: string
}>()
</script>