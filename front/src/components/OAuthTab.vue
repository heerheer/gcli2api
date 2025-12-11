<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  authToken: string
  projectId: string
  getAllProjectsCreds: boolean
  authUrl: string
  authUrlVisible: boolean
  credentialsContent: string
  credentialsVisible: boolean
  authInProgress: boolean
  projectIdOpen: boolean
  callbackUrlOpen: boolean
  callbackUrl: string
  currentProjectId: string | null
}>()

const emits = defineEmits<{
  (e: 'update:projectId', v: string): void
  (e: 'update:getAllProjectsCreds', v: boolean): void
  (e: 'toggleProjectIdOpen'): void
  (e: 'toggleCallbackUrlOpen'): void
  (e: 'startAuth'): void
  (e: 'getCredentials'): void
  (e: 'processCallbackUrl', v: string): void
}>()

const canOperate = computed(() => !!props.authToken)
</script>

<template>
  <div class="card">
    <div class="card-header">OAuth 认证</div>

    <div class="space-y-3">
      <div class="form-row">
        <label class="label">项目ID（可选）</label>
        <div class="flex gap-2">
          <input
            class="input"
            :value="projectId"
            placeholder="留空以自动检测"
            @input="emits('update:projectId', ($event.target as HTMLInputElement).value)"
          />
          <button class="btn btn-secondary" @click="emits('toggleProjectIdOpen')">高级</button>
        </div>
        <div v-if="projectIdOpen" class="hint">当批量获取全部项目凭证时将自动关闭此项</div>
      </div>

      <div class="form-row">
        <label class="label">批量获取所有项目凭证</label>
        <input type="checkbox" :checked="getAllProjectsCreds" @change="emits('update:getAllProjectsCreds', ($event.target as HTMLInputElement).checked)" />
      </div>

      <div class="flex gap-2">
        <button class="btn btn-primary" :disabled="!canOperate" @click="emits('startAuth')">获取认证链接</button>
        <button class="btn" :disabled="!authInProgress" @click="emits('getCredentials')">获取凭证</button>
        <button class="btn btn-secondary" @click="emits('toggleCallbackUrlOpen')">使用回调URL</button>
      </div>

      <div v-if="authUrlVisible" class="info-box">
        <div class="label">认证链接</div>
        <a class="link" :href="authUrl" target="_blank">{{ authUrl }}</a>
      </div>

      <div v-if="callbackUrlOpen" class="form-row">
        <label class="label">回调URL</label>
        <input class="input" :value="callbackUrl" @input="emits('processCallbackUrl', ($event.target as HTMLInputElement).value)" />
      </div>

      <div v-if="credentialsVisible" class="code-box">
        <pre>{{ credentialsContent }}</pre>
      </div>
    </div>
  </div>
  </template>

<style scoped>
.card { @apply bg-white rounded-lg shadow p-4; }
.card-header { @apply text-lg font-semibold mb-3; }
.form-row { @apply space-y-2; }
.label { @apply text-sm text-gray-600; }
.input { @apply w-full border rounded px-3 py-2; }
.btn { @apply px-3 py-2 rounded border; }
.btn-primary { @apply bg-blue-600 text-white; }
.btn-secondary { @apply bg-gray-100; }
.link { @apply text-blue-600 break-all; }
.info-box { @apply bg-gray-50 p-3 rounded border; }
.code-box { @apply bg-black text-green-200 p-3 rounded; }
.hint { @apply text-xs text-gray-500; }
</style>