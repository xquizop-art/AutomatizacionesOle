/**
 * Cliente HTTP para comunicacion con el backend FastAPI.
 */

import type {
  Account,
  EquityCurve,
  EngineStatus,
  MarketStatus,
  Order,
  PerformanceMetrics,
  Position,
  Strategy,
  StrategyAction,
  StrategyRun,
  Trade,
  TradeList,
  TradeSummary,
} from '../types'

const BASE_URL = '/api'

// ── Helper ──────────────────────────────────────────────────────

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${BASE_URL}${path}`
  const res = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }))
    throw new ApiError(res.status, body.detail || res.statusText)
  }

  return res.json()
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

// ── Account ─────────────────────────────────────────────────────

export async function getAccount(): Promise<Account> {
  return request<Account>('/account')
}

export async function getPositions(): Promise<Position[]> {
  return request<Position[]>('/account/positions')
}

export async function getOrders(
  status = 'all',
  limit = 50,
): Promise<Order[]> {
  return request<Order[]>(`/account/orders?status=${status}&limit=${limit}`)
}

export async function getMarketStatus(): Promise<MarketStatus> {
  return request<MarketStatus>('/account/market')
}

// ── Strategies ──────────────────────────────────────────────────

export async function getStrategies(): Promise<Strategy[]> {
  return request<Strategy[]>('/strategies')
}

export async function getActiveStrategies(): Promise<string[]> {
  return request<string[]>('/strategies/active')
}

export async function getStrategy(name: string): Promise<Strategy> {
  return request<Strategy>(`/strategies/${encodeURIComponent(name)}`)
}

export async function startStrategy(name: string): Promise<StrategyAction> {
  return request<StrategyAction>(
    `/strategies/${encodeURIComponent(name)}/start`,
    { method: 'POST' },
  )
}

export async function stopStrategy(name: string): Promise<StrategyAction> {
  return request<StrategyAction>(
    `/strategies/${encodeURIComponent(name)}/stop`,
    { method: 'POST' },
  )
}

export async function updateStrategyParams(
  name: string,
  parameters: Record<string, unknown>,
): Promise<{ name: string; parameters: Record<string, unknown>; message: string }> {
  return request(`/strategies/${encodeURIComponent(name)}/params`, {
    method: 'PUT',
    body: JSON.stringify({ parameters }),
  })
}

// ── Trades ──────────────────────────────────────────────────────

export interface TradeFilters {
  strategy?: string
  symbol?: string
  side?: string
  status?: string
  since?: string
  until?: string
  page?: number
  page_size?: number
}

export async function getTrades(filters: TradeFilters = {}): Promise<TradeList> {
  const params = new URLSearchParams()
  for (const [key, val] of Object.entries(filters)) {
    if (val !== undefined && val !== null && val !== '') {
      params.set(key, String(val))
    }
  }
  const qs = params.toString()
  return request<TradeList>(`/trades${qs ? `?${qs}` : ''}`)
}

export async function getTrade(id: number): Promise<Trade> {
  return request<Trade>(`/trades/${id}`)
}

export async function getTradesSummary(
  filters: { strategy?: string; symbol?: string; since?: string } = {},
): Promise<TradeSummary> {
  const params = new URLSearchParams()
  for (const [key, val] of Object.entries(filters)) {
    if (val) params.set(key, val)
  }
  const qs = params.toString()
  return request<TradeSummary>(`/trades/summary${qs ? `?${qs}` : ''}`)
}

// ── Performance ─────────────────────────────────────────────────

export async function getPerformance(): Promise<PerformanceMetrics> {
  return request<PerformanceMetrics>('/performance')
}

export async function getEngineStatus(): Promise<EngineStatus> {
  return request<EngineStatus>('/performance/engine-status')
}

export async function getStrategyPerformance(
  name: string,
): Promise<PerformanceMetrics> {
  return request<PerformanceMetrics>(
    `/performance/strategy/${encodeURIComponent(name)}`,
  )
}

export async function getEquityCurve(
  since?: string,
  limit = 500,
): Promise<EquityCurve> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (since) params.set('since', since)
  return request<EquityCurve>(`/performance/equity-curve?${params}`)
}

export async function getStrategyEquityCurve(
  name: string,
  since?: string,
  limit = 500,
): Promise<EquityCurve> {
  const params = new URLSearchParams({ limit: String(limit) })
  if (since) params.set('since', since)
  return request<EquityCurve>(
    `/performance/equity-curve/${encodeURIComponent(name)}?${params}`,
  )
}

export async function getStrategyRuns(
  filters: { status?: string; limit?: number } = {},
): Promise<StrategyRun[]> {
  const params = new URLSearchParams()
  if (filters.status) params.set('status', filters.status)
  if (filters.limit) params.set('limit', String(filters.limit))
  const qs = params.toString()
  return request<StrategyRun[]>(`/performance/strategy-runs${qs ? `?${qs}` : ''}`)
}
