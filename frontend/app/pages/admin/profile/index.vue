<template>
  <div>
    <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-gray-100">Application Profile</h2>

    <div v-if="!store.isReady" class="text-gray-500 dark:text-gray-400">Loading…</div>
    <p v-else-if="store.error" class="text-red-600 dark:text-red-400">{{ store.error }}</p>
    <AdminProfileEntities v-else-if="store.profileEntities.length" />
    <p v-else class="text-gray-500 dark:text-gray-400">
      No entities found. Import an ontology first.
    </p>
  </div>
</template>

<script setup lang="ts">
import { useAppStore } from '@/stores/app'

const store = useAppStore()
</script>