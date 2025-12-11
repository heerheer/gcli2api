<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import OAuthTab from './components/OAuthTab.vue'
import UploadTab from './components/UploadTab.vue'
import ManageTab from './components/ManageTab.vue'
import ConfigTab from './components/ConfigTab.vue'
import LogsTab from './components/LogsTab.vue'
import AboutTab from './components/AboutTab.vue'
import type { StatusType, TabName, CredInfo, ConfigForm } from './types'


const statusBanner = reactive<{ message: string; type: StatusType }>({ message: '', type: 'info' })
const showStatus = (message: string, type: StatusType = 'info') => {
  statusBanner.message = message
  statusBanner.type = type
}

const authToken = ref('')
const loginPassword = ref('')
const isLoggedIn = computed(() => Boolean(authToken.value))
const activeTab = ref<TabName>('oauth')
const hasLoadedCreds = ref(false)
const hasLoadedConfig = ref(false)

const getAuthHeaders = (opts: { json?: boolean } = { json: true }) => {
  const headers: Record<string, string> = {}
  if (opts.json !== false) {
    headers['Content-Type'] = 'application/json'
  }
  if (authToken.value) {
    headers['Authorization'] = `Bearer ${authToken.value}`
  }
  return headers
}

const login = async () => {
  if (!loginPassword.value) {
    showStatus('请输入密码', 'error')
    return
  }

  try {
    const response = await fetch('/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: loginPassword.value }),
    })

    const data = await response.json()

    if (response.ok) {
      authToken.value = data.token
      localStorage.setItem('gcli2api_auth_token', data.token)
      showStatus('登录成功', 'success')
    } else {
      showStatus(`登录失败: ${data.detail || data.error || '未知错误'}`, 'error')
    }
  } catch (error: unknown) {
    const err = error as Error
    showStatus(`网络错误: ${err.message}`, 'error')
  }
}

const autoLogin = async () => {
  const savedToken = localStorage.getItem('gcli2api_auth_token')
  if (!savedToken) return false

  authToken.value = savedToken

  try {
    const response = await fetch('/config/get', {
      method: 'GET',
      headers: getAuthHeaders(),
    })

    if (response.ok) {
      showStatus('自动登录成功', 'success')
      return true
    }

    if (response.status === 401) {
      localStorage.removeItem('gcli2api_auth_token')
      authToken.value = ''
    }
  } catch (error: unknown) {
    const err = error as Error
    showStatus(`网络错误: ${err.message}`, 'error')
  }

  return false
}

const logout = () => {
  localStorage.removeItem('gcli2api_auth_token')
  authToken.value = ''
  loginPassword.value = ''
  disconnectWebSocket()
  showStatus('已退出登录', 'info')
}

const handlePasswordEnter = (event: KeyboardEvent) => {
  if (event.key === 'Enter') {
    login()
  }
}

// OAuth state
const projectId = ref('')
const getAllProjectsCreds = ref(false)
const authUrl = ref('')
const authUrlVisible = ref(false)
const credentialsContent = ref('')
const credentialsVisible = ref(false)
const authInProgress = ref(false)
const projectIdOpen = ref(false)
const callbackUrlOpen = ref(false)
const callbackUrl = ref('')
const currentProjectId = ref<string | null>(null)

const startAuth = async () => {
  const btnText = getAllProjectsCreds.value ? '并发批量获取所有项目凭证中...' : '正在获取认证链接...'
  showStatus(btnText, 'info')

  const requestBody: Record<string, unknown> = {}
  if (projectId.value) requestBody.project_id = projectId.value
  if (getAllProjectsCreds.value) requestBody.get_all_projects = true

  try {
    const response = await fetch('/auth/start', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(requestBody),
    })

    const data = await response.json()

    if (response.ok) {
      authUrl.value = data.auth_url
      authUrlVisible.value = true
      authInProgress.value = true
      currentProjectId.value = projectId.value || null

      if (getAllProjectsCreds.value) {
        showStatus('批量并发认证链接已生成，完成授权后将并发为所有可访问项目生成凭证文件', 'info')
      } else if (data.auto_project_detection) {
        showStatus('认证链接已生成（将在认证完成后自动检测项目ID），请点击链接完成授权', 'info')
      } else {
        showStatus(`认证链接已生成（项目ID: ${data.detected_project_id}），请点击链接完成授权`, 'success')
      }
    } else {
      showStatus(`错误: ${data.error || '获取认证链接失败'}`, 'error')
    }
  } catch (error: unknown) {
    const err = error as Error
    showStatus(`网络错误: ${err.message}`, 'error')
  }
}

const getCredentials = async () => {
  if (!authInProgress.value) {
    showStatus('请先获取认证链接并完成授权', 'error')
    return
  }

  const requestBody: Record<string, unknown> = {}
  if (currentProjectId.value) requestBody.project_id = currentProjectId.value
  if (getAllProjectsCreds.value) requestBody.get_all_projects = true

  showStatus(getAllProjectsCreds.value ? '正在并发为所有项目获取认证凭证...' : '正在等待OAuth回调...', 'info')

  try {
    const response = await fetch('/auth/callback', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(requestBody),
    })

    const data = await response.json()

    if (response.ok) {
      credentialsVisible.value = true
      authInProgress.value = false

      if (getAllProjectsCreds.value && data.multiple_credentials) {
        const results = data.multiple_credentials
        let text = `批量并发认证完成！成功为 ${results.success.length} 个项目生成凭证：\n\n`

        results.success.forEach((item: any, index: number) => {
          text += `${index + 1}. 项目: ${item.project_name} (${item.project_id})\n   文件: ${item.file_path}\n\n`
        })

        if (results.failed.length > 0) {
          text += `\n失败的项目 (${results.failed.length} 个):\n`
          results.failed.forEach((item: any, index: number) => {
            text += `${index + 1}. 项目: ${item.project_name} (${item.project_id})\n   错误: ${item.error}\n\n`
          })
        }

        credentialsContent.value = text
        showStatus(
          `✅ 批量并发认证完成！成功生成 ${results.success.length} 个项目的凭证文件${results.failed.length > 0 ? `，${results.failed.length} 个项目失败` : ''}`,
          'success',
        )
      } else {
        credentialsContent.value = JSON.stringify(data.credentials, null, 2)
        if (data.auto_detected_project) {
          showStatus(`✅ 认证成功！项目ID已自动检测为: ${data.credentials.project_id}，文件已保存到: ${data.file_path}`,'success')
        } else {
          showStatus(`✅ 认证成功！文件已保存到: ${data.file_path}`,'success')
        }
      }
    } else {
      if (data.requires_project_selection && data.available_projects) {
        const selection = prompt(
          data.available_projects
            .map((project: any, idx: number) => `${idx + 1}. ${project.name} (${project.projectId})`)
            .join('\n'),
        )
        const projectIndex = selection ? parseInt(selection) - 1 : -1
        if (projectIndex >= 0 && projectIndex < data.available_projects.length) {
          currentProjectId.value = data.available_projects[projectIndex].projectId
          showStatus('使用选择的项目重新尝试...', 'info')
          await getCredentials()
          return
        }
      } else if (data.requires_manual_project_id) {
        const userProjectId = prompt('无法自动检测项目ID，请手动输入您的Google Cloud项目ID:')
        if (userProjectId && userProjectId.trim()) {
          currentProjectId.value = userProjectId.trim()
          showStatus('使用手动输入的项目ID重新尝试...', 'info')
          await getCredentials()
          return
        }
      } else {
        showStatus(`❌ 错误: ${data.error || '获取认证文件失败'}`, 'error')
        if (data.error && data.error.includes('未接收到授权回调')) {
          showStatus('提示：请确保已完成浏览器中的OAuth认证，并看到了"OAuth authentication successful"页面', 'info')
        }
      }
    }
  } catch (error: unknown) {
    const err = error as Error
    showStatus(`网络错误: ${err.message}`, 'error')
  }
}

const toggleProjectIdSection = () => {
  projectIdOpen.value = !projectIdOpen.value
}

const toggleCallbackUrlSection = () => {
  callbackUrlOpen.value = !callbackUrlOpen.value
}

const processCallbackUrl = async () => {
  if (!callbackUrl.value.trim()) {
    showStatus('请输入回调URL', 'error')
    return
  }

  if (!callbackUrl.value.startsWith('http://') && !callbackUrl.value.startsWith('https://')) {
    showStatus('请输入有效的URL（以http://或https://开头）', 'error')
    return
  }

  if (!callbackUrl.value.includes('code=') || !callbackUrl.value.includes('state=')) {
    showStatus('❌ 这不是有效的回调URL！请确保URL包含code和state参数', 'error')
    return
  }

  showStatus(getAllProjectsCreds.value ? '正在从回调URL并发批量获取所有项目凭证...' : '正在从回调URL获取凭证...', 'info')

  try {
    const response = await fetch('/auth/callback-url', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({
        callback_url: callbackUrl.value.trim(),
        project_id: projectId.value.trim() || null,
        get_all_projects: getAllProjectsCreds.value,
      }),
    })

    const result = await response.json()

    if (getAllProjectsCreds.value && result.multiple_credentials) {
      const results = result.multiple_credentials
      let text = `批量并发认证完成！成功为 ${results.success.length} 个项目生成凭证：\n\n`
      results.success.forEach((item: any, index: number) => {
        text += `${index + 1}. 项目: ${item.project_name} (${item.project_id})\n   文件: ${item.file_path}\n\n`
      })
      if (results.failed.length > 0) {
        text += `\n失败的项目 (${results.failed.length} 个):\n`
        results.failed.forEach((item: any, index: number) => {
          text += `${index + 1}. 项目: ${item.project_name} (${item.project_id})\n   错误: ${item.error}\n\n`
        })
      }
      credentialsContent.value = text
      credentialsVisible.value = true
      showStatus(
        `✅ 批量并发认证完成！成功生成 ${results.success.length} 个项目的凭证文件${results.failed.length > 0 ? `，${results.failed.length} 个项目失败` : ''}`,
        'success',
      )
    } else if (result.credentials) {
      credentialsContent.value = JSON.stringify(result.credentials, null, 2)
      credentialsVisible.value = true
      showStatus(result.message || '从回调URL获取凭证成功！', 'success')
    } else if (result.requires_manual_project_id) {
      showStatus('需要手动指定项目ID，请在高级选项中填入Google Cloud项目ID后重试', 'error')
    } else if (result.requires_project_selection) {
      showStatus('检测到多个项目，请在高级选项中指定项目ID', 'error')
    } else {
      showStatus(result.error || '从回调URL获取凭证失败', 'error')
    }

    callbackUrl.value = ''
    setTimeout(() => {
      refreshCredsStatus()
    }, 800)
  } catch (error: unknown) {
    const err = error as Error
    showStatus(`从回调URL获取凭证失败: ${err.message}`, 'error')
  }
}

const handleGetAllProjectsChange = () => {
  if (getAllProjectsCreds.value) {
    projectIdOpen.value = false
  }
}

// Upload state
const uploadSelectedFiles = ref<File[]>([])
const uploadProgress = reactive({ visible: false, percent: 0 })
// 组件内已管理拖拽态，移除全局 uploadAreaActive
const fileInputRef = ref<HTMLInputElement | null>(null)
const triggerFileDialog = () => {
  fileInputRef.value?.click()
}

// 组件化后未使用的文件选择/拖拽处理，移除

const addFiles = (files: File[]) => {
  files.forEach((file) => {
    const isJson = file.type === 'application/json' || file.name.endsWith('.json')
    const isZip = file.type === 'application/zip' || file.name.endsWith('.zip')
    if ((isJson || isZip) && !uploadSelectedFiles.value.find((f) => f.name === file.name && f.size === file.size)) {
      uploadSelectedFiles.value.push(file)
    } else if (!isJson && !isZip) {
      showStatus(`文件 ${file.name} 格式不支持，只支持JSON和ZIP文件`, 'error')
    }
  })
}

const removeFile = (index: number) => {
  uploadSelectedFiles.value.splice(index, 1)
}

const clearFiles = () => {
  uploadSelectedFiles.value = []
}

// formatFileSize 已移除（当前未使用）

const uploadFiles = async () => {
  if (uploadSelectedFiles.value.length === 0) {
    showStatus('请选择要上传的文件', 'error')
    return
  }

  uploadProgress.visible = true
  uploadProgress.percent = 0

  const formData = new FormData()
  uploadSelectedFiles.value.forEach((file) => formData.append('files', file))

  const hasZipFiles = uploadSelectedFiles.value.some((file) => file.name.endsWith('.zip'))
  if (hasZipFiles) {
    showStatus('正在上传并解压ZIP文件...', 'info')
  }

  try {
    await new Promise<void>((resolve, reject) => {
      const xhr = new XMLHttpRequest()
      xhr.timeout = 300000

      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable) {
          uploadProgress.percent = (event.loaded / event.total) * 100
        }
      }

      xhr.onload = () => {
        if (xhr.status === 200) {
          try {
            const data = JSON.parse(xhr.responseText)
            showStatus(`成功上传 ${data.uploaded_count} 个文件`, 'success')
            clearFiles()
            uploadProgress.visible = false
            resolve()
          } catch (e) {
            reject(new Error('上传失败: 服务器响应格式错误'))
          }
        } else {
          try {
            const error = JSON.parse(xhr.responseText)
            reject(new Error(`上传失败: ${error.detail || error.error || '未知错误'}`))
          } catch (e) {
            reject(new Error(`上传失败: HTTP ${xhr.status}`))
          }
        }
      }

      xhr.onerror = () => {
        reject(new Error('上传失败：连接中断，建议分批上传。'))
      }

      xhr.ontimeout = () => {
        reject(new Error('上传失败：请求超时，请减少文件数量或检查网络连接'))
      }

      xhr.open('POST', '/auth/upload')
      if (authToken.value) {
        xhr.setRequestHeader('Authorization', `Bearer ${authToken.value}`)
      }
      xhr.send(formData)
    })
  } catch (error: unknown) {
    const err = error as Error
    showStatus(err.message, 'error')
    uploadProgress.visible = false
  }
}

// Credential management
const credsLoading = ref(false)
const credsList = ref<CredInfo[]>([])
const totalCredsCount = ref(0)
const pageSize = ref(20)
const currentPage = ref(1)
const currentStatusFilter = ref<'all' | 'enabled' | 'disabled'>('all')
const selectedCredFiles = ref<Set<string>>(new Set())

// statsData 已移除（当前未使用）

const totalPages = computed(() => Math.max(1, Math.ceil(totalCredsCount.value / pageSize.value)))
// paginationText 已移除（当前未使用）

const refreshCredsStatus = async () => {
  credsLoading.value = true
  try {
    const offset = (currentPage.value - 1) * pageSize.value
    const response = await fetch(`/creds/status?offset=${offset}&limit=${pageSize.value}&status_filter=${currentStatusFilter.value}`, {
      method: 'GET',
      headers: getAuthHeaders(),
    })

    const data = await response.json()

    if (response.ok) {
      credsList.value = (data.items || []).map((item: any) => ({
        filename: item.filename,
        status: { disabled: item.disabled, error_codes: item.error_codes || [], last_success: item.last_success },
        user_email: item.user_email,
        cooldown_status: item.cooldown_status,
        cooldown_remaining_seconds: item.cooldown_remaining_seconds,
        cooldown_until: item.cooldown_until,
        contentLoaded: false,
        contentLoading: false,
        expanded: false,
      }))
      totalCredsCount.value = data.total || credsList.value.length
      selectedCredFiles.value = new Set(
        Array.from(selectedCredFiles.value).filter((filename) => credsList.value.some((c) => c.filename === filename)),
      )
      hasLoadedCreds.value = true
      showStatus(`已加载 ${totalCredsCount.value} 个凭证文件`, 'success')
    } else {
      showStatus(`加载失败: ${data.detail || data.error || '未知错误'}`, 'error')
    }
  } catch (error: unknown) {
    const err = error as Error
    showStatus(`网络错误: ${err.message}`, 'error')
  } finally {
    credsLoading.value = false
  }
}

const applyStatusFilter = () => {
  currentPage.value = 1
  refreshCredsStatus()
}

const changePage = (direction: number) => {
  const newPage = currentPage.value + direction
  if (newPage >= 1 && newPage <= totalPages.value) {
    currentPage.value = newPage
    refreshCredsStatus()
  }
}

const changePageSize = () => {
  currentPage.value = 1
  refreshCredsStatus()
}

const toggleCredDetails = async (cred: CredInfo) => {
  cred.expanded = !cred.expanded
  if (!cred.expanded || cred.contentLoaded || cred.contentLoading) return

  cred.contentLoading = true
  cred.contentText = '正在加载文件内容...'

  try {
    const response = await fetch(`/creds/detail/${encodeURIComponent(cred.filename)}`, {
      method: 'GET',
      headers: getAuthHeaders(),
    })
    const data = await response.json()
    if (response.ok && data.content) {
      cred.contentText = JSON.stringify(data.content, null, 2)
      cred.contentLoaded = true
    } else {
      cred.contentText = `无法加载文件内容: ${data.error || data.detail || '未知错误'}`
    }
  } catch (error: unknown) {
    const err = error as Error
    cred.contentText = `加载文件内容失败: ${err.message}`
  } finally {
    cred.contentLoading = false
  }
}

const credAction = async (filename: string, action: 'enable' | 'disable' | 'delete') => {
  try {
    const response = await fetch('/creds/action', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ filename, action }),
    })

    const data = await response.json()
    if (response.ok) {
      showStatus(data.message, 'success')
      await refreshCredsStatus()
    } else {
      showStatus(`操作失败: ${data.detail || data.error || '未知错误'}`, 'error')
    }
  } catch (error: unknown) {
    const err = error as Error
    showStatus(`网络错误: ${err.message}`, 'error')
  }
}

const downloadCred = async (filename: string) => {
  try {
    const response = await fetch(`/creds/download/${filename}`, {
      method: 'GET',
      headers: authToken.value ? { Authorization: `Bearer ${authToken.value}` } : {},
    })

    if (response.ok) {
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      window.URL.revokeObjectURL(url)
      showStatus(`已下载文件: ${filename}`, 'success')
    } else {
      const data = await response.json()
      showStatus(`下载失败: ${data.error || '未知错误'}`, 'error')
    }
  } catch (error: unknown) {
    const err = error as Error
    showStatus(`下载失败: ${err.message}`, 'error')
  }
}

const downloadAllCreds = async () => {
  try {
    const response = await fetch('/creds/download-all', {
      method: 'GET',
      headers: authToken.value ? { Authorization: `Bearer ${authToken.value}` } : {},
    })

    if (response.ok) {
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'credentials.zip'
      a.click()
      window.URL.revokeObjectURL(url)
      showStatus('已下载所有凭证文件', 'success')
    } else {
      const data = await response.json()
      showStatus(`打包下载失败: ${data.error || '未知错误'}`, 'error')
    }
  } catch (error: unknown) {
    const err = error as Error
    showStatus(`打包下载失败: ${err.message}`, 'error')
  }
}

// deleteCred 已移除（由 ManageTab 直接触发 action）

const toggleFileSelection = (filename: string) => {
  const set = new Set(selectedCredFiles.value)
  if (set.has(filename)) {
    set.delete(filename)
  } else {
    set.add(filename)
  }
  selectedCredFiles.value = set
}

const toggleSelectAll = (checked: boolean) => {
  const set = new Set(selectedCredFiles.value)
  if (checked) {
    credsList.value.forEach((cred) => set.add(cred.filename))
  } else {
    set.clear()
  }
  selectedCredFiles.value = set
}

const batchAction = async (action: 'enable' | 'disable' | 'delete') => {
  const selectedFiles = Array.from(selectedCredFiles.value)
  if (!selectedFiles.length) {
    showStatus('请先选择要操作的文件', 'error')
    return
  }

  let confirmMessage = ''
  if (action === 'enable') confirmMessage = `确定要启用选中的 ${selectedFiles.length} 个文件吗？`
  if (action === 'disable') confirmMessage = `确定要禁用选中的 ${selectedFiles.length} 个文件吗？`
  if (action === 'delete') confirmMessage = `确定要删除选中的 ${selectedFiles.length} 个文件吗？\n注意：此操作不可恢复！`

  if (!confirm(confirmMessage)) return

  try {
    const response = await fetch('/creds/batch-action', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify({ action, filenames: selectedFiles }),
    })
    const data = await response.json()
    if (response.ok) {
      showStatus(`批量操作完成：成功处理 ${data.success_count || selectedFiles.length}/${selectedFiles.length} 个文件`, 'success')
      selectedCredFiles.value = new Set()
      await refreshCredsStatus()
    } else {
      showStatus(`批量操作失败: ${data.detail || data.error || '未知错误'}`, 'error')
    }
  } catch (error: unknown) {
    const err = error as Error
    showStatus(`批量操作网络错误: ${err.message}`, 'error')
  }
}

const fetchUserEmail = async (filename: string) => {
  try {
    const response = await fetch(`/creds/fetch-email/${encodeURIComponent(filename)}`, {
      method: 'POST',
      headers: getAuthHeaders(),
    })
    const data = await response.json()
    if (response.ok && data.user_email) {
      showStatus(`成功获取邮箱: ${data.user_email}`, 'success')
      await refreshCredsStatus()
    } else {
      showStatus(data.message || '无法获取用户邮箱', 'error')
    }
  } catch (error: unknown) {
    const err = error as Error
    showStatus(`获取邮箱失败: ${err.message}`, 'error')
  }
}

const refreshAllEmails = async () => {
  if (!confirm('确定要刷新所有凭证的用户邮箱吗？这可能需要一些时间。')) return
  try {
    const response = await fetch('/creds/refresh-all-emails', {
      method: 'POST',
      headers: getAuthHeaders(),
    })
    const data = await response.json()
    if (response.ok) {
      showStatus(`邮箱刷新完成：成功获取 ${data.success_count}/${data.total_count} 个邮箱地址`, 'success')
      await refreshCredsStatus()
    } else {
      showStatus(data.message || '邮箱刷新失败', 'error')
    }
  } catch (error: unknown) {
    const err = error as Error
    showStatus(`邮箱刷新网络错误: ${err.message}`, 'error')
  }
}

// formatCooldown 已移除（当前未在模板使用）

let cooldownTimer: number | null = null
const startCooldownTimer = () => {
  stopCooldownTimer()
  cooldownTimer = window.setInterval(() => updateCooldownDisplays(), 1000)
}

const stopCooldownTimer = () => {
  if (cooldownTimer) {
    clearInterval(cooldownTimer)
    cooldownTimer = null
  }
}

const updateCooldownDisplays = () => {
  const now = Date.now() / 1000
  credsList.value.forEach((cred) => {
    if (cred.cooldown_status === 'cooling' && cred.cooldown_until) {
      const remainingSeconds = Math.max(0, Math.floor(cred.cooldown_until - now))
      cred.cooldown_remaining_seconds = remainingSeconds
      if (remainingSeconds <= 0) {
        cred.cooldown_status = 'ready'
        cred.cooldown_until = null
      }
    }
  })
}

// Config state
const configLoading = ref(false)
const configForm = reactive<ConfigForm>({
  host: '0.0.0.0',
  port: 7861,
  configApiPassword: '',
  configPanelPassword: '',
  configPassword: 'pwd',
  credentialsDir: '',
  proxy: '',
  codeAssistEndpoint: '',
  oauthProxyUrl: '',
  googleapisProxyUrl: '',
  resourceManagerApiUrl: '',
  serviceUsageApiUrl: '',
  autoBanEnabled: false,
  autoBanErrorCodes: '',
  callsPerRotation: 10,
  retry429Enabled: false,
  retry429MaxRetries: 20,
  retry429Interval: 0.1,
  compatibilityModeEnabled: false,
  returnThoughtsToFrontend: true,
  antiTruncationMaxAttempts: 3,
})

const envLockedFields = ref<Set<string>>(new Set())
const isFieldLocked = (key: string) => envLockedFields.value.has(key)

const loadConfig = async () => {
  configLoading.value = true
  try {
    const response = await fetch('/config/get', { method: 'GET', headers: getAuthHeaders() })
    const data = await response.json()
    if (response.ok) {
      const cfg = data.config || {}
      configForm.host = cfg.host || '0.0.0.0'
      configForm.port = cfg.port ?? 7861
      configForm.configApiPassword = cfg.api_password || ''
      configForm.configPanelPassword = cfg.panel_password || ''
      configForm.configPassword = cfg.password || 'pwd'
      configForm.credentialsDir = cfg.credentials_dir || ''
      configForm.proxy = cfg.proxy || ''
      configForm.codeAssistEndpoint = cfg.code_assist_endpoint || ''
      configForm.oauthProxyUrl = cfg.oauth_proxy_url || ''
      configForm.googleapisProxyUrl = cfg.googleapis_proxy_url || ''
      configForm.resourceManagerApiUrl = cfg.resource_manager_api_url || ''
      configForm.serviceUsageApiUrl = cfg.service_usage_api_url || ''
      configForm.autoBanEnabled = Boolean(cfg.auto_ban_enabled)
      configForm.autoBanErrorCodes = (cfg.auto_ban_error_codes || []).join(',')
      configForm.callsPerRotation = cfg.calls_per_rotation ?? 10
      configForm.retry429Enabled = Boolean(cfg.retry_429_enabled)
      configForm.retry429MaxRetries = cfg.retry_429_max_retries ?? 20
      configForm.retry429Interval = cfg.retry_429_interval ?? 0.1
      configForm.compatibilityModeEnabled = Boolean(cfg.compatibility_mode_enabled)
      configForm.returnThoughtsToFrontend = cfg.return_thoughts_to_frontend !== false
      configForm.antiTruncationMaxAttempts = cfg.anti_truncation_max_attempts ?? 3
      envLockedFields.value = new Set(data.env_locked || [])
      hasLoadedConfig.value = true
      showStatus('配置加载成功', 'success')
    } else {
      showStatus(`加载配置失败: ${data.detail || data.error || '未知错误'}`, 'error')
    }
  } catch (error: unknown) {
    const err = error as Error
    showStatus(`网络错误: ${err.message}`, 'error')
  } finally {
    configLoading.value = false
  }
}

const saveConfig = async () => {
  try {
    const payload = {
      config: {
        host: configForm.host,
        port: configForm.port,
        api_password: configForm.configApiPassword,
        panel_password: configForm.configPanelPassword,
        password: configForm.configPassword,
        code_assist_endpoint: configForm.codeAssistEndpoint,
        credentials_dir: configForm.credentialsDir,
        proxy: configForm.proxy,
        oauth_proxy_url: configForm.oauthProxyUrl,
        googleapis_proxy_url: configForm.googleapisProxyUrl,
        resource_manager_api_url: configForm.resourceManagerApiUrl,
        service_usage_api_url: configForm.serviceUsageApiUrl,
        auto_ban_enabled: configForm.autoBanEnabled,
        auto_ban_error_codes: configForm.autoBanErrorCodes
          .split(',')
          .map((code) => parseInt(code.trim()))
          .filter((code) => !Number.isNaN(code)),
        calls_per_rotation: configForm.callsPerRotation ?? 10,
        retry_429_enabled: configForm.retry429Enabled,
        retry_429_max_retries: configForm.retry429MaxRetries ?? 20,
        retry_429_interval: configForm.retry429Interval ?? 0.1,
        compatibility_mode_enabled: configForm.compatibilityModeEnabled,
        return_thoughts_to_frontend: configForm.returnThoughtsToFrontend,
        anti_truncation_max_attempts: configForm.antiTruncationMaxAttempts ?? 3,
      },
    }

    const response = await fetch('/config/save', {
      method: 'POST',
      headers: getAuthHeaders(),
      body: JSON.stringify(payload),
    })
    const data = await response.json()
    if (response.ok) {
      let message = '配置保存成功'
      if (data.hot_updated && data.hot_updated.length > 0) {
        message += `，以下配置已立即生效: ${data.hot_updated.join(', ')}`
      }
      if (data.restart_required && data.restart_required.length > 0) {
        message += `\n⚠️ 重启提醒: ${data.restart_notice}`
      }
      showStatus(message, 'success')
      setTimeout(() => loadConfig(), 800)
    } else {
      showStatus(`保存配置失败: ${data.detail || data.error || '未知错误'}`, 'error')
    }
  } catch (error: unknown) {
    const err = error as Error
    showStatus(`网络错误: ${err.message}`, 'error')
  }
}

const mirrorUrls = {
  codeAssistEndpoint: 'https://gcli-api.sukaka.top/cloudcode-pa',
  oauthProxyUrl: 'https://gcli-api.sukaka.top/oauth2',
  googleapisProxyUrl: 'https://gcli-api.sukaka.top/googleapis',
  resourceManagerApiUrl: 'https://gcli-api.sukaka.top/cloudresourcemanager',
  serviceUsageApiUrl: 'https://gcli-api.sukaka.top/serviceusage',
}

const officialUrls = {
  codeAssistEndpoint: 'https://cloudcode-pa.googleapis.com',
  oauthProxyUrl: 'https://oauth2.googleapis.com',
  googleapisProxyUrl: 'https://www.googleapis.com',
  resourceManagerApiUrl: 'https://cloudresourcemanager.googleapis.com',
  serviceUsageApiUrl: 'https://serviceusage.googleapis.com',
}

const useMirrorUrls = () => {
  if (
    confirm(
      '确定要将所有端点配置为镜像网址吗？\n\n镜像网址：\n• Code Assist: https://gcli-api.sukaka.top/cloudcode-pa\n• OAuth: https://gcli-api.sukaka.top/oauth2\n• Google APIs: https://gcli-api.sukaka.top/googleapis\n• Resource Manager: https://gcli-api.sukaka.top/cloudresourcemanager\n• Service Usage: https://gcli-api.sukaka.top/serviceusage',
    )
  ) {
    ;(Object.keys(mirrorUrls) as (keyof typeof mirrorUrls)[]).forEach((key) => {
      const snakeKey = key
        .replace(/([A-Z])/g, '_$1')
        .toLowerCase()
        .replace(/^_/, '')
      if (!isFieldLocked(snakeKey)) {
        ;(configForm as any)[key] = mirrorUrls[key]
      }
    })
    showStatus('✅ 已切换到镜像网址配置，记得点击"保存配置"按钮保存设置', 'success')
  }
}

const restoreOfficialUrls = () => {
  if (
    confirm(
      '确定要将所有端点配置为官方地址吗？\n\n官方端点：\n• Code Assist: https://cloudcode-pa.googleapis.com\n• OAuth: https://oauth2.googleapis.com\n• Google APIs: https://www.googleapis.com\n• Resource Manager: https://cloudresourcemanager.googleapis.com\n• Service Usage: https://serviceusage.googleapis.com',
    )
  ) {
    ;(Object.keys(officialUrls) as (keyof typeof officialUrls)[]).forEach((key) => {
      const snakeKey = key
        .replace(/([A-Z])/g, '_$1')
        .toLowerCase()
        .replace(/^_/, '')
      if (!isFieldLocked(snakeKey)) {
        ;(configForm as any)[key] = officialUrls[key]
      }
    })
    showStatus('✅ 已切换到官方端点配置，记得点击"保存配置"按钮保存设置', 'success')
  }
}

// Logs
const logWebSocket = ref<WebSocket | null>(null)
const logConnectionStatus = reactive<{ text: string; type: StatusType }>({ text: '未连接', type: 'info' })
const logMessages = ref<string[]>([])
const currentLogFilter = ref('all')
const autoScroll = ref(true)
const logContainerRef = ref<HTMLDivElement | null>(null)

const filteredLogs = computed(() => {
  if (currentLogFilter.value === 'all') return logMessages.value
  return logMessages.value.filter((log) => log.toUpperCase().includes(currentLogFilter.value))
})

watch(filteredLogs, async () => {
  if (autoScroll.value) {
    await nextTick()
    const el = logContainerRef.value
    if (el) el.scrollTop = el.scrollHeight
  }
})

const connectWebSocket = () => {
  if (logWebSocket.value && logWebSocket.value.readyState === WebSocket.OPEN) {
    showStatus('WebSocket已经连接', 'info')
    return
  }

  try {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/auth/logs/stream`

    logConnectionStatus.text = '连接中...'
    logConnectionStatus.type = 'info'

    const ws = new WebSocket(wsUrl)
    logWebSocket.value = ws

    ws.onopen = () => {
      logConnectionStatus.text = '已连接'
      logConnectionStatus.type = 'success'
      showStatus('日志流连接成功', 'success')
      clearLogsDisplay()
    }

    ws.onmessage = (event) => {
      const logLine = event.data as string
      if (logLine.trim()) {
        logMessages.value = [...logMessages.value.slice(-999), logLine]
      }
    }

    ws.onclose = () => {
      logConnectionStatus.text = '连接断开'
      logConnectionStatus.type = 'error'
      showStatus('日志流连接断开', 'info')
    }

    ws.onerror = () => {
      logConnectionStatus.text = '连接错误'
      logConnectionStatus.type = 'error'
      showStatus('日志流连接错误', 'error')
    }
  } catch (error: unknown) {
    const err = error as Error
    showStatus(`创建WebSocket连接失败: ${err.message}`, 'error')
    logConnectionStatus.text = '连接失败'
    logConnectionStatus.type = 'error'
  }
}

const disconnectWebSocket = () => {
  if (logWebSocket.value) {
    logWebSocket.value.close()
    logWebSocket.value = null
  }
  logConnectionStatus.text = '未连接'
  logConnectionStatus.type = 'info'
}

const clearLogsDisplay = () => {
  logMessages.value = []
}

const downloadLogs = async () => {
  try {
    const response = await fetch('/auth/logs/download', { method: 'GET', headers: getAuthHeaders() })
    if (response.ok) {
      const contentDisposition = response.headers.get('Content-Disposition')
      let filename = 'gcli2api_logs.txt'
      if (contentDisposition) {
        const match = contentDisposition.match(/filename=(.+)/)
        if (match) filename = match[1] || filename
      }
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      window.URL.revokeObjectURL(url)
      showStatus(`日志文件下载成功: ${filename}`, 'success')
    } else {
      const errorText = await response.text()
      showStatus(`下载日志失败: ${errorText || '未知错误'}`, 'error')
    }
  } catch (error: unknown) {
    const err = error as Error
    showStatus(`下载日志时网络错误: ${err.message}`, 'error')
  }
}

const clearLogs = async () => {
  try {
    const response = await fetch('/auth/logs/clear', { method: 'POST', headers: getAuthHeaders() })
    const data = await response.json()
    if (response.ok) {
      clearLogsDisplay()
      showStatus(data.message || '日志已清空', 'success')
    } else {
      showStatus(`清空日志失败: ${data.detail || data.error || '未知错误'}`, 'error')
    }
  } catch (error: unknown) {
    const err = error as Error
    clearLogsDisplay()
    showStatus(`清空日志时网络错误: ${err.message}`, 'error')
  }
}

// Lifecycle
watch(activeTab, (tab) => {
  if (tab === 'manage') refreshCredsStatus()
  if (tab === 'config' && !hasLoadedConfig.value) loadConfig()
  if (tab === 'logs') connectWebSocket()
})

watch(getAllProjectsCreds, handleGetAllProjectsChange)

onMounted(async () => {
  const logged = await autoLogin()
  if (!logged) {
    showStatus('请输入密码登录', 'info')
  }
  startCooldownTimer()
})

onBeforeUnmount(() => {
  stopCooldownTimer()
  disconnectWebSocket()
})

// Tab 辅助方法，避免模板中的类型比较告警
const setActiveTab = (tab: TabName) => {
  activeTab.value = tab
}
const isActiveTab = (tab: TabName) => activeTab.value === tab
</script>

<template>
  <div class="min-h-screen bg-gray-100 px-4 py-8">
    <div class="panel-container">
      <div v-if="!isLoggedIn" class="login-form text-center">
        <h1 class="text-2xl font-bold mb-4">GCLI2API 管理面板</h1>
        <p class="mb-4 text-gray-600">请输入访问密码：</p>
        <input
          v-model="loginPassword"
          type="password"
          class="login-input"
          placeholder="输入密码"
          @keypress="handlePasswordEnter"
        />
        <button class="btn" @click="login">登录</button>
      </div>

      <div v-else class="space-y-4">
        <div class="flex items-center justify-between">
          <h1 class="text-2xl font-bold">GCLI2API 管理面板</h1>
          <button class="btn danger" @click="logout">退出登录</button>
        </div>

        <div class="tabs">
          <button class="tab" :class="{ active: isActiveTab('oauth') }" @click="setActiveTab('oauth')">OAuth</button>
          <button class="tab" :class="{ active: isActiveTab('upload') }" @click="setActiveTab('upload')">上传</button>
          <button class="tab" :class="{ active: isActiveTab('manage') }" @click="setActiveTab('manage')">管理</button>
          <button class="tab" :class="{ active: isActiveTab('config') }" @click="setActiveTab('config')">配置</button>
          <button class="tab" :class="{ active: isActiveTab('logs') }" @click="setActiveTab('logs')">日志</button>
          <button class="tab" :class="{ active: isActiveTab('about') }" @click="setActiveTab('about')">项目信息</button>
        </div>

        <OAuthTab
          v-if="activeTab === 'oauth'"
          :auth-token="authToken"
          :project-id="projectId"
          :get-all-projects-creds="getAllProjectsCreds"
          :auth-url="authUrl"
          :auth-url-visible="authUrlVisible"
          :credentials-content="credentialsContent"
          :credentials-visible="credentialsVisible"
          :auth-in-progress="authInProgress"
          :project-id-open="projectIdOpen"
          :callback-url-open="callbackUrlOpen"
          :callback-url="callbackUrl"
          :current-project-id="currentProjectId"
          @update:projectId="(v) => (projectId = v)"
          @update:getAllProjectsCreds="(v) => (getAllProjectsCreds = v)"
          @toggleProjectIdOpen="toggleProjectIdSection"
          @toggleCallbackUrlOpen="toggleCallbackUrlSection"
          @startAuth="startAuth"
          @getCredentials="getCredentials"
          @processCallbackUrl="(v) => { callbackUrl = v; processCallbackUrl() }"
        />

        <UploadTab
          v-if="activeTab === 'upload'"
          :files="uploadSelectedFiles"
          :progress-visible="uploadProgress.visible"
          :progress-percent="uploadProgress.percent"
          @triggerFileDialog="triggerFileDialog"
          @addFiles="addFiles"
          @removeFile="removeFile"
          @clearFiles="clearFiles"
          @uploadFiles="uploadFiles"
        />

        <ManageTab
          v-if="activeTab === 'manage'"
          :loading="credsLoading"
          :creds="credsList"
          :total="totalCredsCount"
          :page-size="pageSize"
          :current-page="currentPage"
          :status-filter="currentStatusFilter"
          :selected="selectedCredFiles"
          @refresh="refreshCredsStatus"
          @changePage="changePage"
          @changePageSize="(size) => { pageSize = size; changePageSize() }"
          @applyStatusFilter="(v) => { currentStatusFilter = v; applyStatusFilter() }"
          @toggleDetails="toggleCredDetails"
          @action="credAction"
          @download="downloadCred"
          @downloadAll="downloadAllCreds"
          @toggleFile="toggleFileSelection"
          @toggleAll="toggleSelectAll"
          @batch="batchAction"
          @fetchEmail="fetchUserEmail"
          @refreshAllEmails="refreshAllEmails"
        />

        <ConfigTab
          v-if="activeTab === 'config'"
          :loading="configLoading"
          :form="configForm"
          :env-locked="envLockedFields"
          @save="saveConfig"
          @useMirror="useMirrorUrls"
          @useOfficial="restoreOfficialUrls"
        />

        <LogsTab
          v-if="activeTab === 'logs'"
          :connection-text="logConnectionStatus.text"
          :connection-type="logConnectionStatus.type"
          :logs="filteredLogs"
          :filter="currentLogFilter"
          :auto-scroll="autoScroll"
          @connect="connectWebSocket"
          @disconnect="disconnectWebSocket"
          @clearDisplay="clearLogsDisplay"
          @download="downloadLogs"
          @clear="clearLogs"
          @update:filter="(v) => (currentLogFilter = v)"
          @update:autoScroll="(v) => (autoScroll = v)"
        />

        <AboutTab v-if="activeTab === 'about'" />
      </div>

      <div v-if="statusBanner.message" id="statusSection" class="status mt-4" :class="statusBanner.type">
        {{ statusBanner.message }}
      </div>

      <div class="footer-box">
        <p class="text-sm text-gray-700">GitHub: <a href="https://github.com/su-kaka/gcli2api" target="_blank" class="text-blue-600 hover:underline">https://github.com/su-kaka/gcli2api</a></p>
        <p class="text-sm text-red-600 font-semibold">⚠️ 禁止商业用途和倒卖 - 仅供学习使用 ⚠️</p>
      </div>
    </div>
  </div>
</template>
