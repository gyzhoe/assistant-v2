/** Ticket data extracted from the WHD DOM */
export interface TicketData {
  subject: string
  description: string
  requesterName: string
  category: string
  status: string
  ticketUrl: string
}

/** Settings persisted to chrome.storage.sync */
export interface AppSettings {
  backendUrl: string
  defaultModel: string
  availableModels: string[]
  selectorOverrides: Partial<SelectorConfig>
  promptSuffix: string
  theme: 'light' | 'dark' | 'system'
}

/**
 * Security credentials stored in chrome.storage.local (device-only, never synced).
 * The apiToken must match the API_TOKEN env var set on the backend server.
 */
export interface LocalSecrets {
  apiToken: string
}

/** CSS selector config for WHD DOM fields */
export interface SelectorConfig {
  subject: string
  description: string
  requesterName: string
  category: string
  status: string
  techNotes: string
}

/** Generate API request */
export interface GenerateRequest {
  ticket_subject: string
  ticket_description: string
  requester_name: string
  category: string
  status: string
  model: string
  max_context_docs: number
  stream: boolean
}

/** Single retrieved context document */
export interface ContextDoc {
  content: string
  source: string
  score: number
  metadata: Record<string, unknown>
}

/** Generate API response */
export interface GenerateResponse {
  reply: string
  model_used: string
  context_docs: ContextDoc[]
  latency_ms: number
}

/** Health check response */
export interface HealthResponse {
  status: 'ok' | 'degraded'
  ollama_reachable: boolean
  chroma_ready: boolean
  chroma_doc_counts: Record<string, number>
  version: string
}
