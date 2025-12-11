<script setup lang="ts">
import type { ConfigForm } from '../types'

const props = defineProps<{
  loading: boolean
  form: ConfigForm
  envLocked: Set<string>
}>()

const emits = defineEmits<{
  (e: 'save'): void
  (e: 'useMirror'): void
  (e: 'useOfficial'): void
}>()

const isLocked = (key: string) => props.envLocked.has(key)
</script>

<template>
  <div class="card">
    <div class="card-header">系统配置</div>
    <div v-if="loading" class="hint">加载配置中...</div>
    <div v-else class="grid grid-cols-1 md:grid-cols-2 gap-3">
      <label class="block">
        <span class="label">Host</span>
        <input class="input" v-model="form.host" :disabled="isLocked('host')" />
      </label>
      <label class="block">
        <span class="label">Port</span>
        <input class="input" type="number" v-model.number="form.port" :disabled="isLocked('port')" />
      </label>
      <label class="block">
        <span class="label">密码</span>
        <input class="input" v-model="form.configPassword" :disabled="isLocked('password')" />
      </label>
      <label class="block">
        <span class="label">凭证目录</span>
        <input class="input" v-model="form.credentialsDir" :disabled="isLocked('credentials_dir')" />
      </label>
      <label class="block">
        <span class="label">代理</span>
        <input class="input" v-model="form.proxy" :disabled="isLocked('proxy')" />
      </label>
      <label class="block">
        <span class="label">Code Assist</span>
        <input class="input" v-model="form.codeAssistEndpoint" />
      </label>
      <label class="block">
        <span class="label">OAuth 端点</span>
        <input class="input" v-model="form.oauthProxyUrl" />
      </label>
      <label class="block">
        <span class="label">Google APIs</span>
        <input class="input" v-model="form.googleapisProxyUrl" />
      </label>
      <label class="block">
        <span class="label">Resource Manager</span>
        <input class="input" v-model="form.resourceManagerApiUrl" />
      </label>
      <label class="block">
        <span class="label">Service Usage</span>
        <input class="input" v-model="form.serviceUsageApiUrl" />
      </label>

      <div class="col-span-full flex gap-2 mt-2">
        <button class="btn" @click="emits('useMirror')">使用镜像端点</button>
        <button class="btn" @click="emits('useOfficial')">使用官方端点</button>
        <button class="btn btn-primary" @click="emits('save')">保存配置</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.card { @apply bg-white rounded-lg shadow p-4; }
.card-header { @apply text-lg font-semibold mb-3; }
.label { @apply text-sm text-gray-600; }
.input { @apply w-full border rounded px-3 py-2; }
.btn { @apply px-3 py-2 rounded border; }
.btn-primary { @apply bg-blue-600 text-white; }
.hint { @apply text-sm text-gray-500; }
</style>