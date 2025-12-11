<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

type StatusType = 'info' | 'success' | 'error'
type TabName = 'oauth' | 'upload' | 'manage' | 'config' | 'logs' | 'about'

type CredInfo = {
  filename: string
  status: {
    disabled: boolean
    error_codes?: number[]
    last_success?: string
  }
  user_email?: string
  cooldown_status?: string | null
  cooldown_remaining_seconds?: number
  cooldown_until?: number | null
  contentText?: string
  contentLoaded?: boolean
  contentLoading?: boolean
  expanded?: boolean
}

type ConfigForm = {
  host: string
  port: number | null
  configApiPassword: string
  configPanelPassword: string
  configPassword: string
  credentialsDir: string
  proxy: string
  codeAssistEndpoint: string
  oauthProxyUrl: string
  googleapisProxyUrl: string
  resourceManagerApiUrl: string
  serviceUsageApiUrl: string
  autoBanEnabled: boolean
  autoBanErrorCodes: string
  callsPerRotation: number | null
  retry429Enabled: boolean
  retry429MaxRetries: number | null
  retry429Interval: number | null
  compatibilityModeEnabled: boolean
  returnThoughtsToFrontend: boolean
  antiTruncationMaxAttempts: number | null
}

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
const uploadAreaActive = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)
const triggerFileDialog = () => {
  fileInputRef.value?.click()
}

const handleFileSelect = (event: Event) => {
  const target = event.target as HTMLInputElement
  const files = Array.from(target.files || [])
  addFiles(files)
  target.value = ''
}

const onDropFiles = (event: DragEvent) => {
  const files = Array.from(event.dataTransfer?.files || [])
  addFiles(files)
  uploadAreaActive.value = false
}

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

const formatFileSize = (bytes: number) => {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`
  return `${Math.round(bytes / (1024 * 1024))} MB`
}

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

const statsData = computed(() => {
  const normal = credsList.value.filter((c) => !c.status.disabled).length
  const disabled = credsList.value.filter((c) => c.status.disabled).length
  return { total: totalCredsCount.value, normal, disabled }
})

const totalPages = computed(() => Math.max(1, Math.ceil(totalCredsCount.value / pageSize.value)))
const paginationText = computed(() => {
  const startItem = (currentPage.value - 1) * pageSize.value + 1
  const endItem = Math.min(currentPage.value * pageSize.value, totalCredsCount.value)
  return `第 ${currentPage.value} 页，共 ${totalPages.value} 页 (显示 ${startItem}-${endItem}，共 ${totalCredsCount.value} 项)`
})

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

const deleteCred = async (filename: string) => {
  if (!confirm(`确定要删除凭证文件吗？\n${filename}`)) return
  await credAction(filename, 'delete')
}

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

const formatCooldown = (remainingSeconds?: number) => {
  if (!remainingSeconds) return ''
  const hours = Math.floor(remainingSeconds / 3600)
  const minutes = Math.floor((remainingSeconds % 3600) / 60)
  const seconds = remainingSeconds % 60
  if (hours > 0) return `${hours}h ${minutes}m ${seconds}s`
  if (minutes > 0) return `${minutes}m ${seconds}s`
  return `${seconds}s`
}

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
          <button class="tab" :class="{ active: activeTab === 'oauth' }" @click="activeTab = 'oauth'">OAuth认证</button>
          <button class="tab" :class="{ active: activeTab === 'upload' }" @click="activeTab = 'upload'">批量上传</button>
          <button class="tab" :class="{ active: activeTab === 'manage' }" @click="activeTab = 'manage'">文件管理</button>
          <button class="tab" :class="{ active: activeTab === 'config' }" @click="activeTab = 'config'">配置管理</button>
          <button class="tab" :class="{ active: activeTab === 'logs' }" @click="activeTab = 'logs'">实时日志</button>
          <button class="tab" :class="{ active: activeTab === 'about' }" @click="activeTab = 'about'">项目信息</button>
        </div>

        <!-- OAuth Tab -->
        <section v-show="activeTab === 'oauth'" class="tab-content active">
          <div class="status success mb-4">
            <strong>✨ 自动化优化：</strong> 系统现在会在认证成功后自动为您的项目启用必需的API服务
            <ul class="ml-6 list-disc text-sm text-green-900">
              <li><strong>Gemini Cloud Assist API</strong></li>
              <li><strong>Gemini for Google Cloud API</strong></li>
            </ul>
            <p class="mt-2 text-green-800 text-sm">无需手动启用API，系统会自动处理这些配置步骤，让认证流程更加顺畅。</p>
          </div>

          <div class="form-group">
            <div class="toggle-row" @click="toggleProjectIdSection">
              <span class="font-semibold text-gray-700">📁 高级选项：Google Cloud Project ID (不用管，直接点击获取链接即可)</span>
              <span class="text-gray-500">{{ projectIdOpen ? '▼' : '▶' }}</span>
            </div>
            <div v-show="projectIdOpen" class="advanced-box">
              <label for="projectId" class="font-semibold text-gray-700">Google Cloud Project ID (可选):</label>
              <input
                id="projectId"
                v-model="projectId"
                type="text"
                class="input"
                placeholder="留空将尝试自动检测，或手动输入项目ID"
              />
              <small class="text-gray-600 text-xs">💡 提示：如果你不懂这是什么，可以留空此字段让系统自动检测项目ID</small>
            </div>
          </div>

          <div class="form-group">
            <div class="batch-box">
              <div class="flex items-center gap-3">
                <input id="getAllProjectsCreds" v-model="getAllProjectsCreds" type="checkbox" class="scale-125" />
                <label for="getAllProjectsCreds" class="font-semibold text-green-700 cursor-pointer">🌐 为当前账号所有项目获取凭证</label>
              </div>
              <div class="text-sm text-green-800 mt-2 leading-relaxed">
                <strong>说明：</strong>勾选此选项后，系统会自动检测当前Google账号下的所有项目，并发处理为每个项目生成独立的认证文件。
              </div>
              <div v-show="getAllProjectsCreds" class="note-box mt-2">✨ <strong>批量并发认证模式已启用</strong> - 认证完成后将并发为所有可访问的项目生成凭证文件</div>
            </div>
          </div>

          <button class="btn" @click="startAuth">获取认证链接</button>

          <div v-show="authUrlVisible" class="mt-4">
            <h3 class="font-semibold">认证链接：</h3>
            <div class="auth-url">
              <a :href="authUrl" target="_blank" class="break-all text-blue-600 hover:underline">{{ authUrl }}</a>
            </div>
            <div class="status info">
              <strong>重要说明：</strong>
              <ol class="list-decimal ml-5 text-sm text-blue-900">
                <li>点击上方认证链接，会在新窗口中打开Google OAuth页面</li>
                <li>完成Google账号登录和授权</li>
                <li>授权成功后会跳转到localhost:8080显示成功页面</li>
                <li>关闭OAuth窗口，返回本页面</li>
                <li>点击下方"获取认证文件"按钮完成流程</li>
              </ol>
            </div>

            <div class="shortcut-box">
              <div class="flex items-center justify-between cursor-pointer" @click="toggleCallbackUrlSection">
                <span class="font-semibold text-blue-700">🚀 无法回源？试试快捷方式</span>
                <span class="text-gray-500">{{ callbackUrlOpen ? '▲' : '▼' }}</span>
              </div>
              <div v-show="callbackUrlOpen" class="space-y-3 text-sm text-gray-700">
                <div class="alert-yellow">
                  <div class="font-semibold text-yellow-800 mb-1">📚 适用场景：</div>
                  <ul class="list-disc ml-4 text-yellow-800">
                    <li>云服务器、VPS等非本地环境</li>
                    <li>防火墙阻止了8080端口访问</li>
                    <li>网络环境无法正常回源到localhost</li>
                    <li>Docker容器内运行，端口映射问题</li>
                  </ul>
                </div>
                <div class="text-gray-700 leading-relaxed">
                  <strong class="text-blue-700">🔍 什么是回调URL？</strong>
                  <br />完成Google OAuth授权后，浏览器地址栏显示的完整URL。
                </div>
                <input
                  v-model="callbackUrl"
                  type="url"
                  class="input"
                  placeholder="粘贴完整的回调URL，例如：http://localhost:8080/?state=xxx&code=xxx&scope=xxx..."
                />
                <button class="btn success" @click="processCallbackUrl">从回调URL获取凭证</button>
              </div>
            </div>

            <button class="btn" @click="getCredentials">获取认证文件</button>
          </div>

          <div v-show="credentialsVisible" class="mt-4">
            <h3 class="font-semibold">认证文件内容：</h3>
            <div class="credentials whitespace-pre-wrap text-xs">{{ credentialsContent }}</div>
          </div>
        </section>

        <!-- Upload Tab -->
        <section v-show="activeTab === 'upload'" class="tab-content active">
          <h3 class="text-lg font-semibold">批量上传认证文件</h3>
          <p class="text-gray-600">支持上传多个JSON格式的认证文件到服务器</p>

          <div
            class="upload-area"
            :class="{ dragover: uploadAreaActive }"
            @click="triggerFileDialog"
            @dragover.prevent="uploadAreaActive = true"
            @dragleave.prevent="uploadAreaActive = false"
            @drop.prevent="onDropFiles"
          >
            <p>点击选择文件或拖拽文件到此区域</p>
            <p class="text-sm text-gray-600">支持 .json 和 .zip 格式文件</p>
            <p class="text-xs text-gray-500">ZIP文件会自动解压提取其中的JSON凭证</p>
          </div>

          <input ref="fileInputRef" type="file" class="hidden" multiple accept=".json,.zip" @change="handleFileSelect" />

          <div v-show="uploadSelectedFiles.length" class="mt-4 space-y-2">
            <h4 class="font-semibold">选择的文件：</h4>
            <div class="file-list">
              <div v-for="(file, index) in uploadSelectedFiles" :key="file.name + index" class="file-item">
                <div>
                  <span class="file-name">{{ file.name }}</span>
                  <span class="file-size">({{ formatFileSize(file.size) }})</span>
                </div>
                <button class="remove-btn" @click="removeFile(index)">删除</button>
              </div>
            </div>
            <div class="flex gap-2 flex-wrap">
              <button class="btn" @click="uploadFiles">上传文件</button>
              <button class="btn secondary" @click="clearFiles">清空列表</button>
            </div>
          </div>

          <div v-show="uploadProgress.visible" class="upload-progress mt-4">
            <h4 class="font-semibold">上传进度：</h4>
            <div class="progress-bar">
              <div class="progress-fill" :style="{ width: `${Math.round(uploadProgress.percent)}%` }"></div>
            </div>
            <p>{{ Math.round(uploadProgress.percent) }}%</p>
          </div>
        </section>

        <!-- Manage Tab -->
        <section v-show="activeTab === 'manage'" class="tab-content active">
          <h3 class="text-lg font-semibold">凭证文件管理</h3>
          <p class="text-gray-600">管理所有认证文件，查看状态和执行操作</p>

          <div class="stats-container">
            <div class="stat-item total">
              <span class="stat-number">{{ statsData.total }}</span>
              <span class="stat-label">总计</span>
            </div>
            <div class="stat-item normal">
              <span class="stat-number">{{ statsData.normal }}</span>
              <span class="stat-label">正常</span>
            </div>
            <div class="stat-item disabled">
              <span class="stat-number">{{ statsData.disabled }}</span>
              <span class="stat-label">禁用</span>
            </div>
          </div>

          <div class="manage-actions">
            <button class="refresh-btn" @click="refreshCredsStatus">刷新状态</button>
            <button class="download-all-btn" @click="downloadAllCreds">打包下载所有文件</button>
          </div>

          <div class="batch-controls">
            <h4 class="font-semibold">批量操作</h4>
            <div class="batch-actions">
              <div class="checkbox-container">
                <input
                  id="selectAllCheckbox"
                  type="checkbox"
                  class="select-all-checkbox"
                  :checked="selectedCredFiles.size === credsList.length && credsList.length > 0"
                  @change="toggleSelectAll(($event.target as HTMLInputElement).checked)"
                />
                <label for="selectAllCheckbox">全选</label>
              </div>
              <span class="selected-count">已选择 {{ selectedCredFiles.size }} 项</span>
              <button class="batch-btn batch-enable" :disabled="!selectedCredFiles.size" @click="batchAction('enable')">批量启用</button>
              <button class="batch-btn batch-disable" :disabled="!selectedCredFiles.size" @click="batchAction('disable')">批量禁用</button>
              <button class="batch-btn batch-delete" :disabled="!selectedCredFiles.size" @click="batchAction('delete')">批量删除</button>
              <button class="batch-btn batch-email" @click="refreshAllEmails">刷新所有邮箱</button>
            </div>
          </div>

          <div class="filter-container">
            <label for="statusFilter">凭证状态：</label>
            <select id="statusFilter" v-model="currentStatusFilter" class="filter-select" @change="applyStatusFilter">
              <option value="all">全部凭证</option>
              <option value="enabled">仅启用</option>
              <option value="disabled">仅禁用</option>
            </select>

            <label for="pageSizeSelect" class="ml-4">每页显示：</label>
            <select id="pageSizeSelect" v-model.number="pageSize" class="page-size-select" @change="changePageSize">
              <option :value="20">20</option>
              <option :value="50">50</option>
              <option :value="100">100</option>
            </select>
          </div>

          <div id="credsListSection">
            <div v-show="credsLoading" class="loading">正在加载凭证文件...</div>
            <div v-if="!credsLoading && credsList.length === 0" class="text-center text-gray-600">暂无凭证文件</div>

            <div v-else class="space-y-3">
              <div v-for="cred in credsList" :key="cred.filename" class="cred-card" :class="{ disabled: cred.status.disabled }">
                <div class="cred-header">
                  <div class="flex items-start gap-3">
                    <input
                      type="checkbox"
                      class="file-checkbox"
                      :checked="selectedCredFiles.has(cred.filename)"
                      @change="toggleFileSelection(cred.filename)"
                    />
                    <div>
                      <div class="cred-filename">{{ cred.filename }}</div>
                      <div class="cred-email" :class="cred.user_email ? 'text-gray-600' : 'text-gray-400 italic'">
                        {{ cred.user_email || '未获取邮箱' }}
                      </div>
                    </div>
                  </div>
                  <div class="cred-status">
                    <span class="status-badge" :class="cred.status.disabled ? 'disabled' : 'enabled'">
                      {{ cred.status.disabled ? '已禁用' : '已启用' }}
                    </span>
                    <span v-if="cred.status.error_codes?.length" class="error-codes">错误码: {{ cred.status.error_codes.join(', ') }}</span>
                    <span v-else class="status-badge" style="background-color: #28a745; color: white;">无错误</span>
                    <span
                      v-if="cred.cooldown_status === 'cooling' && cred.cooldown_remaining_seconds"
                      class="cooldown-badge"
                      :title="cred.cooldown_until ? `冷却截止时间: ${new Date((cred.cooldown_until || 0) * 1000).toLocaleString('zh-CN')}` : ''"
                    >
                      🕐 冷却中: {{ formatCooldown(cred.cooldown_remaining_seconds) }}
                    </span>
                  </div>
                </div>

                <div class="cred-actions">
                  <button
                    class="cred-btn"
                    :class="cred.status.disabled ? 'enable' : 'disable'"
                    @click="credAction(cred.filename, cred.status.disabled ? 'enable' : 'disable')"
                  >
                    {{ cred.status.disabled ? '启用' : '禁用' }}
                  </button>
                  <button class="cred-btn view" @click="toggleCredDetails(cred)">{{ cred.expanded ? '收起' : '查看内容' }}</button>
                  <button class="cred-btn download" @click="downloadCred(cred.filename)">下载</button>
                  <button class="cred-btn email" @click="fetchUserEmail(cred.filename)">查看账号邮箱</button>
                  <button class="cred-btn delete" @click="deleteCred(cred.filename)">删除</button>
                </div>

                <div class="cred-details" :class="{ show: cred.expanded }">
                  <div class="cred-content">
                    <template v-if="cred.contentLoading">正在加载文件内容...</template>
                    <template v-else>{{ cred.contentText || '点击"查看内容"按钮加载文件详情...' }}</template>
                  </div>
                </div>
              </div>
            </div>

            <div v-show="totalPages > 1" class="pagination-container">
              <button class="pagination-btn" :disabled="currentPage <= 1" @click="changePage(-1)">上一页</button>
              <div class="pagination-info">{{ paginationText }}</div>
              <button class="pagination-btn" :disabled="currentPage >= totalPages" @click="changePage(1)">下一页</button>
            </div>
          </div>
        </section>

        <!-- Config Tab -->
        <section v-show="activeTab === 'config'" class="tab-content active">
          <h3 class="text-lg font-semibold">配置管理</h3>
          <p class="text-gray-600">管理系统配置参数，修改后立即生效</p>

          <div class="manage-actions">
            <button class="refresh-btn" @click="loadConfig">刷新配置</button>
            <button class="btn" @click="saveConfig">保存配置</button>
          </div>

          <div id="configSection">
            <div v-show="configLoading" class="loading">正在加载配置...</div>
            <div v-show="!configLoading" id="configForm" class="space-y-4">
              <div class="config-group">
                <h4>服务器配置</h4>
                <div class="form-group">
                  <label for="host">服务器主机地址:</label>
                  <input id="host" v-model="configForm.host" :disabled="isFieldLocked('host')" type="text" class="config-input" />
                  <small class="config-note">服务器监听的主机地址，0.0.0.0表示监听所有接口</small>
                </div>
                <div class="form-group">
                  <label for="port">服务器端口:</label>
                  <input id="port" v-model.number="configForm.port" :disabled="isFieldLocked('port')" type="number" min="1" max="65535" class="config-input" />
                  <small class="config-note">服务器监听的端口号，修改后需要重启服务器</small>
                </div>
                <div class="form-group">
                  <label for="configApiPassword">API访问密码:</label>
                  <input id="configApiPassword" v-model="configForm.configApiPassword" :disabled="isFieldLocked('api_password')" type="text" class="config-input" />
                  <small class="config-note">聊天API访问密码，用于OpenAI和Gemini API端点的认证</small>
                </div>
                <div class="form-group">
                  <label for="configPanelPassword">控制面板密码:</label>
                  <input id="configPanelPassword" v-model="configForm.configPanelPassword" :disabled="isFieldLocked('panel_password')" type="text" class="config-input" />
                  <small class="config-note">控制面板访问密码，用于web界面登录认证</small>
                </div>
                <div class="form-group">
                  <label for="configPassword">通用密码:</label>
                  <input id="configPassword" v-model="configForm.configPassword" :disabled="isFieldLocked('password')" type="text" class="config-input" />
                  <small class="config-note">（兼容性保留）设置后将覆盖上述两个密码，留空则使用分开的密码设置</small>
                </div>
              </div>

              <div class="config-group">
                <h4>基础配置</h4>
                <div class="form-group">
                  <label for="credentialsDir">凭证目录路径:</label>
                  <input id="credentialsDir" v-model="configForm.credentialsDir" :disabled="isFieldLocked('credentials_dir')" type="text" class="config-input" />
                  <small class="config-note">存储认证文件的目录路径</small>
                </div>
                <div class="form-group">
                  <label for="proxy">代理设置:</label>
                  <input id="proxy" v-model="configForm.proxy" :disabled="isFieldLocked('proxy')" type="text" class="config-input" placeholder="例如: http://proxy:8080 或 socks5://proxy:1080" />
                  <small class="config-note">HTTP/HTTPS/SOCKS5Endpoint，留空表示不使用代理</small>
                </div>
              </div>

              <div class="config-group">
                <h4>端点配置</h4>
                <div class="form-group">
                  <div class="flex flex-wrap gap-2 mb-3">
                    <button type="button" class="btn success" @click="useMirrorUrls">🚀 一键使用镜像网址</button>
                    <button type="button" class="btn info" @click="restoreOfficialUrls">🔄 还原官方端点</button>
                  </div>
                  <small class="config-note">镜像网址主要解决墙内无法访问官方端点的问题，部分地区可能无法使用</small>
                </div>
                <div class="form-group">
                  <label for="codeAssistEndpoint">Code Assist Endpoint:</label>
                  <input id="codeAssistEndpoint" v-model="configForm.codeAssistEndpoint" :disabled="isFieldLocked('code_assist_endpoint')" type="text" class="config-input" />
                </div>
                <div class="form-group">
                  <label for="oauthProxyUrl">OAuth Endpoint:</label>
                  <input id="oauthProxyUrl" v-model="configForm.oauthProxyUrl" :disabled="isFieldLocked('oauth_proxy_url')" type="text" class="config-input" />
                </div>
                <div class="form-group">
                  <label for="googleapisProxyUrl">Google APIs Endpoint:</label>
                  <input id="googleapisProxyUrl" v-model="configForm.googleapisProxyUrl" :disabled="isFieldLocked('googleapis_proxy_url')" type="text" class="config-input" />
                </div>
                <div class="form-group">
                  <label for="resourceManagerApiUrl">Resource Manager API Endpoint:</label>
                  <input id="resourceManagerApiUrl" v-model="configForm.resourceManagerApiUrl" :disabled="isFieldLocked('resource_manager_api_url')" type="text" class="config-input" />
                </div>
                <div class="form-group">
                  <label for="serviceUsageApiUrl">Service Usage API Endpoint:</label>
                  <input id="serviceUsageApiUrl" v-model="configForm.serviceUsageApiUrl" :disabled="isFieldLocked('service_usage_api_url')" type="text" class="config-input" />
                </div>
              </div>

              <div class="config-group">
                <h4>自动封禁配置</h4>
                <div class="form-group flex items-center gap-2">
                  <input id="autoBanEnabled" v-model="configForm.autoBanEnabled" type="checkbox" class="config-checkbox" />
                  <label for="autoBanEnabled">启用自动封禁</label>
                </div>
                <small class="config-note">遇到指定错误码时自动禁用凭证</small>
                <div class="form-group">
                  <label for="autoBanErrorCodes">自动封禁错误码:</label>
                  <input id="autoBanErrorCodes" v-model="configForm.autoBanErrorCodes" type="text" class="config-input" placeholder="例如: 400,403" />
                  <small class="config-note">用逗号分隔的错误码列表</small>
                </div>
              </div>

              <div class="config-group">
                <h4>429重试配置</h4>
                <div class="form-group flex items-center gap-2">
                  <input id="retry429Enabled" v-model="configForm.retry429Enabled" type="checkbox" class="config-checkbox" />
                  <label for="retry429Enabled">启用429重试</label>
                </div>
                <small class="config-note">遇到429错误时自动重试</small>
                <div class="form-group">
                  <label for="retry429MaxRetries">429重试次数:</label>
                  <input id="retry429MaxRetries" v-model.number="configForm.retry429MaxRetries" type="number" min="1" max="50" class="config-input" />
                </div>
                <div class="form-group">
                  <label for="retry429Interval">429重试间隔(秒):</label>
                  <input id="retry429Interval" v-model.number="configForm.retry429Interval" type="number" min="0.01" max="10" step="0.01" class="config-input" />
                </div>
              </div>

              <div class="config-group">
                <h4>兼容性配置</h4>
                <div class="form-group flex items-center gap-2">
                  <input id="compatibilityModeEnabled" v-model="configForm.compatibilityModeEnabled" type="checkbox" class="config-checkbox" />
                  <label for="compatibilityModeEnabled">启用兼容性模式</label>
                </div>
                <div class="config-info warning">启用后所有system消息转换成user，停用system_instructions。</div>
                <div class="form-group flex items-center gap-2">
                  <input id="returnThoughtsToFrontend" v-model="configForm.returnThoughtsToFrontend" type="checkbox" class="config-checkbox" />
                  <label for="returnThoughtsToFrontend">返回思维链到前端</label>
                </div>
                <div class="config-info info">启用后可以看到模型的思考过程；禁用后仅显示最终回答。</div>
              </div>

              <div class="config-group">
                <h4>抗截断配置</h4>
                <div class="form-group">
                  <label for="antiTruncationMaxAttempts">抗截断最大重试次数:</label>
                  <input id="antiTruncationMaxAttempts" v-model.number="configForm.antiTruncationMaxAttempts" type="number" min="1" max="10" class="config-input" />
                  <small class="config-note">当检测到输出截断时的最大续传尝试次数</small>
                </div>
              </div>
            </div>
          </div>
        </section>

        <!-- Logs Tab -->
        <section v-show="activeTab === 'logs'" class="tab-content active">
          <h3 class="text-lg font-semibold">实时日志</h3>
          <p class="text-gray-600">查看系统实时日志输出，支持日志筛选和自动滚动</p>

          <div class="manage-actions flex-wrap">
            <button class="refresh-btn" @click="connectWebSocket">连接日志流</button>
            <button class="btn danger" @click="disconnectWebSocket">断开连接</button>
            <button class="btn success" @click="downloadLogs">下载日志</button>
            <button class="btn secondary" @click="clearLogs">清空日志</button>
          </div>

          <div class="filter-container flex-wrap items-center">
            <label for="logLevelFilter">日志级别筛选：</label>
            <select id="logLevelFilter" v-model="currentLogFilter" class="filter-select">
              <option value="all">全部</option>
              <option value="ERROR">错误</option>
              <option value="WARNING">警告</option>
              <option value="INFO">信息</option>
              <option value="DEBUG">调试</option>
            </select>
            <label class="flex items-center gap-2">
              <input v-model="autoScroll" type="checkbox" />
              自动滚动到底部
            </label>
          </div>

          <div class="status" :class="logConnectionStatus.type">
            <strong>连接状态：</strong> <span>{{ logConnectionStatus.text }}</span>
          </div>

          <div
            ref="logContainerRef"
            class="bg-[#1e1e1e] text-white font-mono text-xs h-[600px] overflow-y-auto border border-[#333] rounded-md p-4 whitespace-pre-wrap break-words"
          >
            <div v-if="filteredLogs.length === 0">等待连接日志流...</div>
            <div v-else>{{ filteredLogs.join('\n') }}</div>
          </div>
        </section>

        <!-- About Tab -->
        <section v-show="activeTab === 'about'" class="tab-content active space-y-4">
          <h3 class="text-lg font-semibold">项目信息</h3>
          <p class="text-gray-600">关于GCLI2API项目的详细信息和支持方式</p>

          <div class="info-card primary">
            <h4>📋 项目简介</h4>
            <p>GCLI2API是一个将Google Gemini API转换为OpenAI 和GEMINI API格式的代理工具，支持多账户管理、自动轮换、实时日志监控等功能。</p>
            <p><strong>🔗 项目地址：</strong> <a href="https://github.com/su-kaka/gcli2api" target="_blank" class="text-blue-600 hover:underline">GitHub - su-kaka/gcli2api</a></p>
            <p class="text-red-600 font-semibold">⚠️ 禁止商业用途和倒卖 - 仅供学习使用</p>
          </div>

          <div class="info-card info">
            <h4>✨ 主要功能</h4>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <p><strong>🔄 多账户管理：</strong> 支持批量上传和管理多个Google账户</p>
                <p><strong>⚡ 自动轮换：</strong> 智能轮换账户，避免单账户限额</p>
                <p><strong>📊 实时监控：</strong> 使用统计、错误监控、实时日志</p>
              </div>
              <div>
                <p><strong>🛡️ 安全可靠：</strong> OAuth2认证、自动封禁异常账户</p>
                <p><strong>🎛️ 配置灵活：</strong> 支持热更新配置、代理设置</p>
                <p><strong>📱 界面友好：</strong> 响应式设计、移动端适配</p>
              </div>
            </div>
          </div>

          <div class="donate-card">
            <h4>💝 支持项目发展</h4>
            <p>如果这个项目对您有帮助，欢迎通过币安扫码捐赠支持项目的持续发展！</p>
            <div class="inline-block bg-white p-4 rounded-xl shadow-md">
              <img src="/docs/币安.jpg" alt="币安捐赠二维码" class="w-48 h-48 rounded-lg mx-auto" />
              <p class="text-gray-700 mt-2 font-semibold text-center">扫码币安捐赠</p>
            </div>
          </div>

          <div class="info-card info text-center">
            <h4>💬 交流群</h4>
            <p>欢迎加入 QQ 群交流讨论！</p>
            <p class="text-xl font-bold text-blue-600">QQ 群号：937681997</p>
            <div class="inline-block bg-white p-4 rounded-xl shadow-md mt-3">
              <img src="/docs/qq群.jpg" alt="QQ群二维码" class="w-48 h-48 rounded-lg mx-auto" />
              <p class="text-gray-700 mt-2 font-semibold">扫码加入QQ群</p>
            </div>
          </div>

          <div class="info-card muted">
            <h4>📞 联系我们</h4>
            <p>• 问题反馈：通过GitHub Issues提交问题和建议</p>
            <p>• 功能请求：在GitHub Discussions中讨论新功能</p>
            <p>• 代码贡献：欢迎提交Pull Request改进项目</p>
            <p>• 文档完善：帮助改进项目文档和使用指南</p>
          </div>
        </section>
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
