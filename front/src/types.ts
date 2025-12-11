export type StatusType = 'info' | 'success' | 'error'

export type TabName = 'oauth' | 'upload' | 'manage' | 'config' | 'logs' | 'about'

export type CredInfo = {
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

export type ConfigForm = {
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