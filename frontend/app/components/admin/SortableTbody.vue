<template>
  <tbody ref="tbodyRef">
    <slot />
  </tbody>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUpdate, onUpdated } from 'vue'
import Sortable from 'sortablejs'

const props = defineProps<{
  modelValue: any[]
  options?: Sortable.Options
}>()

const emit = defineEmits<{
  'update:modelValue': [value: any[]]
  'orderChanged': [newOrder: any[]]
}>()

const tbodyRef = ref<HTMLElement | null>(null)
let sortable: Sortable | null = null

function createSortable() {
  if (!tbodyRef.value) return
  sortable = Sortable.create(tbodyRef.value, {
    animation: 150,
    handle: '.drag-handle',
    ghostClass: 'bg-blue-100',
    ...props.options,
    onEnd: function (evt) {
      const list = [...props.modelValue]
      const movedItem = list.splice(evt.oldIndex!, 1)[0]
      list.splice(evt.newIndex!, 0, movedItem)
      emit('update:modelValue', list)
      emit('orderChanged', list)
    }
  })
}

onMounted(() => {
  createSortable()
})

onBeforeUpdate(() => {
  if (sortable) {
    sortable.destroy()
    sortable = null
  }
})

onUpdated(() => {
  createSortable()
})
</script>