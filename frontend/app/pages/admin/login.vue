<template>
  <div class="flex items-center justify-center h-screen bg-white dark:bg-gray-900">
    <form @submit.prevent
      class="border border-gray-300 dark:border-gray-600 rounded p-6 shadow bg-white dark:bg-gray-800">
      <h2 class="text-xl font-bold mb-4 text-gray-900 dark:text-gray-100">Admin Login</h2>
      <p class="text-gray-500 dark:text-gray-400 mb-4">Authentication will be implemented here.</p>
      <input v-model="email" type="email" placeholder="Email"
        class="border border-gray-300 dark:border-gray-600 p-2 w-full mb-2 bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400"
        disabled />
      <input v-model="password" type="password" placeholder="Password"
        class="border border-gray-300 dark:border-gray-600 p-2 w-full mb-4 bg-gray-100 dark:bg-gray-700 text-gray-500 dark:text-gray-400"
        disabled />
      <button type="submit" class="bg-blue-600 text-white px-4 py-2 rounded w-full opacity-50 cursor-not-allowed"
        disabled>
        Login
      </button>
    </form>
  </div>
</template>

<script setup lang="ts">
const email = ref('')
const password = ref('')
</script>