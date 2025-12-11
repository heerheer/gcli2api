<script setup lang="ts">
const props = defineProps<{
  files: File[]
  progressVisible: boolean
  progressPercent: number
}>()

const emits = defineEmits<{
  (e: 'triggerFileDialog'): void
  (e: 'addFiles', v: File[]): void
  (e: 'removeFile', index: number): void
  (e: 'clearFiles'): void
  (e: 'uploadFiles'): void
}>()

const onSelect = (e: Event) => {
  const input = e.target as HTMLInputElement
  const files = Array.from(input.files || [])
  emits('addFiles', files)
  input.value = ''
}
</script>

<template>
  <div class="card">
    <div class="card-header">上传凭证</div>
    <div class="space-y-3">
      <div class="flex gap-2">
        <input type="file" multiple @change="onSelect" />
        <button class="btn" @click="emits('triggerFileDialog')">选择文件</button>
        <button class="btn btn-primary" @click="emits('uploadFiles')">上传</button>
        <button class="btn btn-secondary" @click="emits('clearFiles')">清空</button>
      </div>

      <div v-if="files.length" class="list">
        <div v-for="(f, i) in files" :key="f.name + ':' + f.size" class="list-item">
          <span>{{ f.name }}</span>
          <button class="btn btn-secondary" @click="emits('removeFile', i)">移除</button>
        </div>
      </div>

      <div v-if="progressVisible" class="progress">
        <div class="bar" :style="{ width: progressPercent + '%' }"></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.card { @apply bg-white rounded-lg shadow p-4; }
.card-header { @apply text-lg font-semibold mb-3; }
.btn { @apply px-3 py-2 rounded border; }
.btn-primary { @apply bg-blue-600 text-white; }
.btn-secondary { @apply bg-gray-100; }
.list { @apply space-y-2; }
.list-item { @apply flex justify-between items-center; }
.progress { @apply w-full h-2 bg-gray-200 rounded; }
.bar { @apply h-2 bg-blue-600 rounded; }
</style>