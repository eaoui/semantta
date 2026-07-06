<template>
  <div>
    <h2 class="text-2xl font-bold mb-4 text-gray-900 dark:text-gray-100">Plugins</h2>

    <ImportBox title="Install Plugin" accept=".zip" buttonText="Install" @upload="upload" />

    <div v-if="loading" class="text-gray-500 dark:text-gray-400">Loading…</div>
    <div v-else-if="plugins.length === 0" class="text-gray-500 dark:text-gray-400">No plugins installed.</div>
    <div v-else class="space-y-3">
      <ItemCard v-for="p in plugins" :key="p.folder" :title="p.name" :version="p.version" :description="p.description">
        <template #actions>
          <PhosphorIcon v-if="p.removable" name="trash" size="16" class="text-red-600 hover:text-red-800 cursor-pointer"
            @click="selectedPlugin = p.folder; confirmDelete = true" />
        </template>

        <template #footer>
          <label class="flex items-center gap-2 cursor-pointer text-gray-700 dark:text-gray-300">
            <input type="checkbox" :checked="p.enabled" @change="togglePlugin(p.folder, !p.enabled)" class="h-4 w-4" />
            <span class="text-sm">{{ p.enabled ? 'Enabled' : 'Disabled' }}</span>
          </label>
        </template>
      </ItemCard>
    </div>

    <ConfirmDialog :show="confirmDelete" message="Delete this plugin? Its folder will be removed."
      @confirm="handleDelete" @cancel="confirmDelete = false; selectedPlugin = ''" />

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

interface PluginInfo {
  folder: string
  name: string
  version: string
  description: string
  enabled: boolean
  removable: boolean
}

const plugins = ref<PluginInfo[]>([])
const loading = ref(true)
const loadingMsg = ref('')
const selectedPlugin = ref('')
const confirmDelete = ref(false)

onMounted(async () => {
  try {
    const res = await $fetch<{ plugins: PluginInfo[] }>(`${apiBase}/api/plugins`)
    plugins.value = res.plugins
  } catch (e: any) {
    toast.error('Failed to load plugins')
  } finally {
    loading.value = false
  }
})

async function upload(file: File) {
  loadingMsg.value = 'Installing plugin…'
  try {
    const formData = new FormData()
    formData.append('file', file)
    await $fetch(`${apiBase}/api/plugins/upload`, { method: 'POST', body: formData })
    toast.success('Plugin installed. Enable it and restart the server.')
    const res = await $fetch<{ plugins: PluginInfo[] }>(`${apiBase}/api/plugins`)
    plugins.value = res.plugins
  } catch (e: any) {
    toast.error(e?.data?.detail || e.message || 'Upload failed')
  } finally {
    loadingMsg.value = ''
  }
}

async function togglePlugin(folder: string, enabled: boolean) {
  try {
    await $fetch(`${apiBase}/api/plugins/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: folder, enabled })
    })
    const p = plugins.value.find(p => p.folder === folder)
    if (p) p.enabled = enabled
    toast.info(`Plugin ${enabled ? 'enabled' : 'disabled'}. Restart server to apply.`)
  } catch (e: any) {
    toast.error('Toggle failed: ' + (e?.data?.detail || e.message))
  }
}

async function handleDelete() {
  if (!selectedPlugin.value) return
  confirmDelete.value = false
  try {
    await $fetch(`${apiBase}/api/plugins/${encodeURIComponent(selectedPlugin.value)}`, { method: 'DELETE' })
    plugins.value = plugins.value.filter(p => p.folder !== selectedPlugin.value)
    toast.success('Plugin deleted.')
  } catch (e: any) {
    toast.error('Delete failed: ' + (e?.data?.detail || e.message))
  } finally {
    selectedPlugin.value = ''
  }
}
</script>