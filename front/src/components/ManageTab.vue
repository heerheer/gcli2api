<script setup lang="ts">
import type { CredInfo } from '../types'

const props = defineProps<{
  loading: boolean
  creds: CredInfo[]
  total: number
  pageSize: number
  currentPage: number
  statusFilter: 'all' | 'enabled' | 'disabled'
  selected: Set<string>
}>()

const emits = defineEmits<{
  (e: 'refresh'): void
  (e: 'changePage', d: number): void
  (e: 'changePageSize', size: number): void
  (e: 'applyStatusFilter', v: 'all' | 'enabled' | 'disabled'): void
  (e: 'toggleDetails', cred: CredInfo): void
  (e: 'action', filename: string, action: 'enable' | 'disable' | 'delete'): void
  (e: 'download', filename: string): void
  (e: 'downloadAll'): void
  (e: 'toggleFile', filename: string): void
  (e: 'toggleAll', checked: boolean): void
  (e: 'batch', action: 'enable' | 'disable' | 'delete'): void
  (e: 'fetchEmail', filename: string): void
  (e: 'refreshAllEmails'): void
}>()
</script>

<template>
  <div class="card">
    <div class="card-header">凭证管理</div>

    <div class="flex gap-2 mb-3">
      <select class="input" :value="statusFilter" @change="emits('applyStatusFilter', ($event.target as HTMLSelectElement).value as any)">
        <option value="all">全部</option>
        <option value="enabled">启用</option>
        <option value="disabled">禁用</option>
      </select>
      <button class="btn" @click="emits('refresh')">刷新</button>
      <button class="btn" @click="emits('downloadAll')">打包下载</button>
    </div>

    <div v-if="loading" class="hint">加载中...</div>
    <div v-else class="space-y-2">
      <div class="toolbar flex gap-2">
        <button class="btn" @click="emits('batch', 'enable')">批量启用</button>
        <button class="btn" @click="emits('batch', 'disable')">批量禁用</button>
        <button class="btn btn-danger" @click="emits('batch', 'delete')">批量删除</button>
        <button class="btn" @click="emits('refreshAllEmails')">刷新所有邮箱</button>
      </div>

      <div class="list">
        <div class="item" v-for="cred in creds" :key="cred.filename">
          <input type="checkbox" :checked="selected.has(cred.filename)" @change="emits('toggleFile', cred.filename)" />
          <div class="grow">
            <div class="name">{{ cred.filename }}</div>
            <div class="meta text-xs text-gray-500">状态：{{ cred.status.disabled ? '禁用' : '启用' }}</div>
          </div>
          <div class="actions flex gap-2">
            <button class="btn" @click="emits('toggleDetails', cred)">详情</button>
            <button class="btn" @click="emits('download', cred.filename)">下载</button>
            <button class="btn" @click="emits('fetchEmail', cred.filename)">邮箱</button>
            <button class="btn" @click="emits('action', cred.filename, cred.status.disabled ? 'enable' : 'disable')">{{ cred.status.disabled ? '启用' : '禁用' }}</button>
            <button class="btn btn-danger" @click="emits('action', cred.filename, 'delete')">删除</button>
          </div>
          <div v-if="cred.expanded" class="code-box"><pre>{{ cred.contentText }}</pre></div>
        </div>
      </div>

      <div class="pagination flex items-center gap-2">
        <button class="btn" @click="emits('toggleAll', true)">全选本页</button>
        <button class="btn" @click="emits('toggleAll', false)">取消全选</button>
        <button class="btn" @click="emits('changePage', -1)">上一页</button>
        <span>第 {{ currentPage }} 页</span>
        <button class="btn" @click="emits('changePage', 1)">下一页</button>
        <select class="input" :value="pageSize" @change="emits('changePageSize', Number(($event.target as HTMLSelectElement).value))">
          <option :value="10">10</option>
          <option :value="20">20</option>
          <option :value="50">50</option>
        </select>
      </div>
    </div>
  </div>
</template>

<style scoped>
.card { @apply bg-white rounded-lg shadow p-4; }
.card-header { @apply text-lg font-semibold mb-3; }
.btn { @apply px-3 py-2 rounded border; }
.btn-danger { @apply bg-red-600 text-white; }
.input { @apply border rounded px-2 py-1; }
.list { @apply space-y-2; }
.item { @apply flex items-start gap-3 p-2 border rounded; }
.code-box { @apply bg-black text-green-200 p-2 rounded mt-2; }
.hint { @apply text-sm text-gray-500; }
</style>