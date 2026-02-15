// ── Account ─────────────────────────────────────────────────────

export interface Position {
  symbol: string
  qty: number
  side: string
  market_value: number
  avg_entry_price: number
  current_price: number
  unrealized_pl: number
  unrealized_plpc: number
}

export interface Account {
  account_id: string
  equity: number
  cash: number
  buying_power: number
  portfolio_value: number
  status: string
  open_positions: number
  positions: Position[]
  is_paper: boolean
}

export interface Order {
  order_id: string
  symbol: string
  side: string
  order_type: string
  qty: number
  time_in_force: string
  status: string
  filled_qty: number
  filled_avg_price: number | null
  limit_price: number | null
  stop_price: number | null
  created_at: string | null
  filled_at: string | null
}

export interface MarketStatus {
  is_open: boolean
  message: string
}

// ── Strategies ──────────────────────────────────────────────────

export interface Strategy {
  name: string
  description: string
  symbols: string[]
  timeframe: string
  parameters: Record<string, unknown>
  status: string
  last_run: string | null
  total_signals: number
  instantiated: boolean
}

export interface StrategyAction {
  name: string
  status: string
  message: string
  symbols: string[]
  timeframe: string
  run_id: number | null
}

// ── Trades ──────────────────────────────────────────────────────

export interface Trade {
  id: number
  strategy_name: string
  symbol: string
  side: string
  qty: number
  order_type: string
  time_in_force: string
  limit_price: number | null
  stop_price: number | null
  filled_avg_price: number | null
  filled_qty: number | null
  status: string
  alpaca_order_id: string | null
  signal: string | null
  realized_pnl: number | null
  commission: number | null
  notes: string | null
  created_at: string | null
  submitted_at: string | null
  filled_at: string | null
  total_value: number | null
}

export interface TradeList {
  trades: Trade[]
  total: number
  page: number
  page_size: number
  total_pages: number
}

export interface TradeSummary {
  total_trades: number
  filled_trades: number
  rejected_trades: number
  error_trades: number
  total_buy: number
  total_sell: number
  total_realized_pnl: number
  winning_trades: number
  losing_trades: number
  win_rate: number | null
  avg_pnl_per_trade: number | null
  best_trade_pnl: number | null
  worst_trade_pnl: number | null
  by_strategy: Record<string, { total: number; filled: number; pnl: number }>
  by_symbol: Record<string, { total: number; filled: number; pnl: number }>
}

// ── Performance ─────────────────────────────────────────────────

export interface PerformanceMetrics {
  total_pnl: number
  daily_pnl: number
  unrealized_pnl: number
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number | null
  sharpe_ratio: number | null
  max_drawdown: number | null
  max_drawdown_usd: number | null
  equity: number | null
  cash: number | null
  buying_power: number | null
}

export interface EquityCurvePoint {
  timestamp: string
  equity: number | null
  total_pnl: number
  daily_pnl: number
}

export interface EquityCurve {
  strategy_name: string | null
  points: EquityCurvePoint[]
  total_points: number
}

export interface StrategyRun {
  id: number
  strategy_name: string
  status: string
  symbols: string[]
  timeframe: string | null
  parameters: string | null
  last_signal: string | null
  error_message: string | null
  total_trades: number
  winning_trades: number
  losing_trades: number
  total_pnl: number
  win_rate: number | null
  started_at: string | null
  stopped_at: string | null
  created_at: string | null
}

export interface EngineStatus {
  engine_status: string
  started_at: string | null
  active_strategies: string[]
  total_strategies_available: number
  total_cycles: number
  total_orders_submitted: number
  risk_manager: Record<string, unknown>
  websocket_connections: number
}

// ── WebSocket Events ────────────────────────────────────────────

export type WSEventType =
  | 'connected'
  | 'engine_started'
  | 'engine_stopped'
  | 'strategy_started'
  | 'strategy_stopped'
  | 'strategy_error'
  | 'signal_generated'
  | 'order_submitted'
  | 'risk_rejected'
  | 'cycle_completed'
  | 'pong'
  | 'subscribed'
  | 'unsubscribed'
  | 'error'

export interface WSEvent {
  event: WSEventType
  timestamp?: string
  [key: string]: unknown
}

export interface WSOrderEvent extends WSEvent {
  event: 'order_submitted'
  strategy: string
  symbol: string
  side: string
  qty: number
  price: number | null
  order_id: string
  status: string
}

export interface WSSignalEvent extends WSEvent {
  event: 'signal_generated'
  strategy: string
  signals: Record<string, string>
}
