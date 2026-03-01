/** Shared API error with HTTP status code and optional response body */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: Record<string, unknown> = {}
  ) {
    super(`API error ${status}`)
    this.name = 'ApiError'
  }
}
