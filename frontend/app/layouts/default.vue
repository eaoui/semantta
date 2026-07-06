<template>
  <div class="flex h-screen flex-col bg-white dark:bg-gray-900">
    <!-- Header -->
    <header
      class="border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-6 py-3 flex items-center justify-between">
      <!-- Left side -->
      <div class="flex items-center gap-8">
        <NuxtLink to="/"
          class="text-xl font-bold text-black dark:text-white hover:text-gray-700 dark:hover:text-gray-300">
          {{ siteTitle }}
        </NuxtLink>
        <nav class="flex gap-4">
          <NuxtLink to="/dataset"
            class="text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100"
            active-class="text-blue-600 dark:text-blue-400 font-semibold">
            Explore
          </NuxtLink>
        </nav>
      </div>

      <!-- Right side -->
      <div class="flex items-center gap-4">

        <!-- Logged in -->
        <div v-if="auth.isLoggedIn.value" class="relative" ref="userMenuRef">
          <button @click="userMenuOpen = !userMenuOpen"
            class="text-sm text-gray-700 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white px-3 py-1 rounded hover:bg-gray-100 dark:hover:bg-gray-700">
            {{ auth.user.value.name }}
          </button>

          <!-- Dropdown menu -->
          <div v-show="userMenuOpen"
            class="absolute right-0 mt-2 w-48 bg-white dark:bg-gray-700 border border-gray-200 dark:border-gray-600 rounded shadow-lg z-50">
            <NuxtLink v-if="auth.user.value.role === 'admin'" to="/admin"
              class="block px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600"
              @click="userMenuOpen = false">
              Dashboard
            </NuxtLink>
            <button @click="logout"
              class="block w-full text-left px-4 py-2 text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-600">
              Logout
            </button>
          </div>
        </div>

        <!-- Not logged in -->
        <template v-else>
          <NuxtLink to="/sign-in"
            class="text-sm text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-gray-100">
            Sign In
          </NuxtLink>
        </template>
      </div>
    </header>

    <!-- Page content -->
    <main class="flex-1 p-6 overflow-y-auto">
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { useAuth } from '@/composables/useAuth'
import { useSiteTitle } from '@/composables/useSiteTitle'

const { title: siteTitle } = useSiteTitle()
const auth = useAuth()
const userMenuOpen = ref(false)
const userMenuRef = ref<HTMLElement | null>(null)

function logout() {
  userMenuOpen.value = false
  // Real logout logic will be added later
}

// Close the menu when clicking outside
function onDocumentClick(e: MouseEvent) {
  if (!userMenuOpen.value) return
  if (userMenuRef.value && !userMenuRef.value.contains(e.target as Node)) {
    userMenuOpen.value = false
  }
}

onMounted(() => {
  document.addEventListener('click', onDocumentClick)
})

onUnmounted(() => {
  document.removeEventListener('click', onDocumentClick)
})

// Dynamic <title> for the browser tab
useHead({
  titleTemplate: (titleChunk) => {
    const site = siteTitle.value || 'Semantta'
    return titleChunk ? `${titleChunk} - ${site}` : site
  },
})
</script>