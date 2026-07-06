<template>
  <div>
    <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-gray-100">Themes</h2>

    <ImportBox title="Install Theme" accept=".zip" buttonText="Install" @upload="upload" />

    <div v-if="loading" class="text-gray-500 dark:text-gray-400">Loading…</div>
    <div v-else-if="themes.length === 0" class="text-gray-500 dark:text-gray-400">No themes installed.</div>
    <div v-else class="space-y-3">
      <ItemCard v-for="theme in themes" :key="theme.folder" :title="theme.name" :version="theme.version"
        :description="theme.description">
        <template #actions>
          <PhosphorIcon v-if="theme.removable" name="trash" size="16"
            class="text-red-600 hover:text-red-800 cursor-pointer"
            @click="selectedTheme = theme.folder; confirmDelete = true" />
        </template>

        <template #footer>
          <div class="flex items-center gap-3">
            <button v-if="theme.enabled" @click="setActive(theme.folder)"
              class="text-sm bg-green-600 text-white px-2 py-1 rounded hover:bg-green-700">
              {{ activeTheme === theme.folder ? 'Active' : 'Activate' }}
            </button>
            <label v-if="theme.removable"
              class="flex items-center gap-2 cursor-pointer text-gray-700 dark:text-gray-300">
              <input type="checkbox" :checked="theme.enabled" @change="toggleTheme(theme.folder, !theme.enabled)"
                class="h-4 w-4" />
              <span class="text-sm">{{ theme.enabled ? 'Enabled' : 'Disabled' }}</span>
            </label>
          </div>
        </template>
      </ItemCard>
    </div>

    <ConfirmDialog :show="confirmDelete" message="Delete this theme? Its folder will be removed."
      @confirm="handleDelete" @cancel="confirmDelete = false; selectedTheme = ''" />

    <LoadingOverlay :show="!!loadingMsg" :message="loadingMsg" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import ConfirmDialog from '@/components/admin/ConfirmDialog.vue'
import LoadingOverlay from '@/components/shared/LoadingOverlay.vue'
import ImportBox from '@/components/admin/ImportBox.vue'
import ItemCard from '@/components/admin/ItemCard.vue'
import { useToast } from '@/composables/useToast'

const apiBase = useRuntimeConfig().public.apiBase
const toast = useToast()

interface ThemeInfo {
  folder: string
  name: string
  version: string
  description: string
  enabled: boolean
  removable: boolean
}

const themes = ref<ThemeInfo[]>([])
const loading = ref(true)
const file = ref<File | null>(null)
const fileInput = ref<HTMLInputElement>()
const uploadError = ref('')
const loadingMsg = ref('')
const selectedTheme = ref('')
const confirmDelete = ref(false)
const activeTheme = ref('default')

onMounted(async () => {
  try {
    const res = await $fetch<{ themes: ThemeInfo[] }>(`${apiBase}/api/themes`)
    themes.value = res.themes
    const settings = await $fetch<{ active_theme?: string }>(`${apiBase}/api/settings`)
    activeTheme.value = settings.active_theme || 'default'
  } catch (e: any) {
    toast.error('Failed to load themes')
  } finally {
    loading.value = false
  }
})

async function upload(file: File) {
  loadingMsg.value = 'Installing theme…'
  try {
    const formData = new FormData()
    formData.append('file', file)
    await $fetch(`${apiBase}/api/themes/upload`, { method: 'POST', body: formData })
    toast.success('Theme installed. Enable it and set as active to use it.')
    const res = await $fetch<{ themes: ThemeInfo[] }>(`${apiBase}/api/themes`)
    themes.value = res.themes
  } catch (e: any) {
    toast.error(e?.data?.detail || e.message || 'Upload failed')
  } finally {
    loadingMsg.value = ''
  }
}

async function toggleTheme(folder: string, enabled: boolean) {
  try {
    await $fetch(`${apiBase}/api/themes/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: folder, enabled })
    })
    const t = themes.value.find(t => t.folder === folder)
    if (t) t.enabled = enabled
    toast.info(`Theme ${enabled ? 'enabled' : 'disabled'}. Restart frontend to apply.`)
  } catch (e: any) {
    toast.error('Toggle failed: ' + (e?.data?.detail || e.message))
  }
}

async function setActive(folder: string) {
  loadingMsg.value = 'Setting active theme…'
  try {
    await $fetch(`${apiBase}/api/themes/set-active`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ theme: folder })
    })
    activeTheme.value = folder
    toast.success('Active theme updated. Restart frontend to apply.')
  } catch (e: any) {
    toast.error('Failed to set active theme: ' + (e?.data?.detail || e.message))
  } finally {
    loadingMsg.value = ''
  }
}

async function handleDelete() {
  if (!selectedTheme.value) return
  confirmDelete.value = false
  try {
    await $fetch(`${apiBase}/api/themes/${encodeURIComponent(selectedTheme.value)}`, { method: 'DELETE' })
    themes.value = themes.value.filter(t => t.folder !== selectedTheme.value)
    toast.success('Theme deleted.')
  } catch (e: any) {
    toast.error('Delete failed: ' + (e?.data?.detail || e.message))
  } finally {
    selectedTheme.value = ''
  }
}
</script>