<script setup lang="ts">
import type { StatusType } from '../types'
const props = defineProps<{
  connectionText: string
  connectionType: StatusType
  logs: string[]
  filter: string
  autoScroll: boolean
}>()

const emits = defineEmits<{
  (e: 'connect'): void
  (e: 'disconnect'): void
  (e: 'clearDisplay'): void
  (e: 'download'): void
  (e: 'clear'): void
  (e: 'update:filter', v: string): void
  (e: 'update:autoScroll', v: boolean): void
}>()
</script>

<template>
  <div class="card">
    <div class="card-header">运行日志</div>

    <div class="flex gap-2 mb-2">
      <button class="btn" @click="emits('connect')">连接</button>
      <button class="btn" @click="emits('disconnect')">断开</button>
      <button class="btn" @click="emits('download')">下载</button>
      <button class="btn" @click="emits('clear')">清空</button>
      <label class="ml-auto flex items-center gap-2 text-sm">
        <span>自动滚动</span>
        <input type="checkbox" :checked="autoScroll" @change="emits('update:autoScroll', ($event.target as HTMLInputElement).checked)" />
      </label>
    </div>

    <div class="flex items-center gap-2 mb-2">
      <span class="status" :class="connectionType">{{ connectionText }}</span>
      <input class="input ml-auto" :value="filter" placeholder="过滤关键字" @input="emits('update:filter', ($event.target as HTMLInputElement).value)" />
    </div>

    <div class="log-box">
      <pre>
{{ logs.join('\n') }}
      </pre>
    </div>
  </div>
</template>

<style scoped>
.card { @apply bg-white rounded-lg shadow p-4; }
.card-header { @apply text-lg font-semibold mb-3; }
.btn { @apply px-3 py-2 rounded border; }
.input { @apply border rounded px-2 py-1; }
.status { @apply text-xs px-2 py-1 rounded; }
.status.info { @apply bg-gray-100; }
.status.success { @apply bg-green-100; }
.status.error { @apply bg-red-100; }
.log-box { @apply h-64 overflow-auto bg-black text-green-200 rounded p-2; }
</style>