/**
 * Resumen de cuenta Alpaca.
 * Balance, equity, buying power, posiciones.
 */

import { useCallback } from 'react'
import {
  DollarSign,
  TrendingUp,
  TrendingDown,
  Wallet,
  ShieldCheck,
  Activity,
  Wifi,
  WifiOff,
} from 'lucide-react'
import { clsx } from 'clsx'
import { usePolling } from '../hooks/usePolling'
import { getAccount, getMarketStatus, getPerformance } from '../services/api'
import type { Account, MarketStatus, PerformanceMetrics } from '../types'
import type { ConnectionStatus } from '../hooks/useWebSocket'

interface AccountSummaryProps {
  wsStatus: ConnectionStatus
}

function formatUsd(value: number | null | undefined): string {
  if (value == null) return '--'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
  }).format(value)
}

function formatPct(value: number | null | undefined): string {
  if (value == null) return '--'
  return `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`
}

interface StatCardProps {
  label: string
  value: string
  icon: React.ReactNode
  trend?: 'up' | 'down' | 'neutral'
  subValue?: string
}

function StatCard({ label, value, icon, trend, subValue }: StatCardProps) {
  return (
    <div className="card card-body flex items-start gap-3">
      <div
        className={clsx(
          'p-2 rounded-lg',
          trend === 'up' && 'bg-emerald-500/10 text-emerald-400',
          trend === 'down' && 'bg-red-500/10 text-red-400',
          (!trend || trend === 'neutral') && 'bg-blue-500/10 text-blue-400',
        )}
      >
        {icon}
      </div>
      <div className="min-w-0 flex-1">
        <p className="stat-label truncate">{label}</p>
        <p
          className={clsx(
            'stat-value mt-1',
            trend === 'up' && 'text-emerald-400',
            trend === 'down' && 'text-red-400',
          )}
        >
          {value}
        </p>
        {subValue && (
          <p className="text-xs text-dark-400 mt-0.5">{subValue}</p>
        )}
      </div>
    </div>
  )
}

export default function AccountSummary({ wsStatus }: AccountSummaryProps) {
  const fetchAccount = useCallback(() => getAccount(), [])
  const fetchMarket = useCallback(() => getMarketStatus(), [])
  const fetchPerf = useCallback(() => getPerformance(), [])

  const { data: account } = usePolling<Account>({
    fetcher: fetchAccount,
    interval: 10_000,
  })

  const { data: market } = usePolling<MarketStatus>({
    fetcher: fetchMarket,
    interval: 30_000,
  })

  const { data: perf } = usePolling<PerformanceMetrics>({
    fetcher: fetchPerf,
    interval: 8_000,
  })

  const pnlTrend =
    perf && perf.total_pnl > 0
      ? 'up'
      : perf && perf.total_pnl < 0
        ? 'down'
        : 'neutral'

  const dailyTrend =
    perf && perf.daily_pnl > 0
      ? 'up'
      : perf && perf.daily_pnl < 0
        ? 'down'
        : 'neutral'

  return (
    <div className="space-y-4">
      {/* Status bar */}
      <div className="flex items-center gap-4 flex-wrap text-xs">
        {/* Paper/Live mode */}
        {account && (
          <span
            className={clsx(
              'badge',
              account.is_paper ? 'badge-yellow' : 'badge-green',
            )}
          >
            <ShieldCheck className="w-3 h-3 mr-1" />
            {account.is_paper ? 'Paper Trading' : 'Live Trading'}
          </span>
        )}

        {/* Market status */}
        {market && (
          <span
            className={clsx(
              'badge',
              market.is_open ? 'badge-green' : 'badge-red',
            )}
          >
            <Activity className="w-3 h-3 mr-1" />
            {market.message}
          </span>
        )}

        {/* WebSocket */}
        <span
          className={clsx(
            'badge',
            wsStatus === 'connected' ? 'badge-green' : 'badge-red',
          )}
        >
          {wsStatus === 'connected' ? (
            <Wifi className="w-3 h-3 mr-1" />
          ) : (
            <WifiOff className="w-3 h-3 mr-1" />
          )}
          WS: {wsStatus}
        </span>

        {/* Win rate */}
        {perf?.win_rate != null && (
          <span className="badge badge-blue">
            Win Rate: {perf.win_rate.toFixed(1)}%
          </span>
        )}
      </div>

      {/* Stats grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard
          label="Equity"
          value={formatUsd(account?.equity)}
          icon={<DollarSign className="w-4 h-4" />}
          subValue={account ? `${account.open_positions} positions` : undefined}
        />
        <StatCard
          label="Cash"
          value={formatUsd(account?.cash)}
          icon={<Wallet className="w-4 h-4" />}
          subValue={
            account ? `BP: ${formatUsd(account.buying_power)}` : undefined
          }
        />
        <StatCard
          label="Total P&L"
          value={formatUsd(perf?.total_pnl)}
          icon={
            pnlTrend === 'up' ? (
              <TrendingUp className="w-4 h-4" />
            ) : (
              <TrendingDown className="w-4 h-4" />
            )
          }
          trend={pnlTrend}
          subValue={
            perf?.total_trades != null
              ? `${perf.total_trades} trades`
              : undefined
          }
        />
        <StatCard
          label="Daily P&L"
          value={formatUsd(perf?.daily_pnl)}
          icon={
            dailyTrend === 'up' ? (
              <TrendingUp className="w-4 h-4" />
            ) : (
              <TrendingDown className="w-4 h-4" />
            )
          }
          trend={dailyTrend}
        />
        <StatCard
          label="Sharpe Ratio"
          value={perf?.sharpe_ratio != null ? perf.sharpe_ratio.toFixed(2) : '--'}
          icon={<Activity className="w-4 h-4" />}
        />
        <StatCard
          label="Max Drawdown"
          value={
            perf?.max_drawdown != null ? formatPct(-perf.max_drawdown) : '--'
          }
          icon={<TrendingDown className="w-4 h-4" />}
          trend={perf?.max_drawdown != null && perf.max_drawdown > 0 ? 'down' : 'neutral'}
          subValue={
            perf?.max_drawdown_usd != null
              ? formatUsd(-perf.max_drawdown_usd)
              : undefined
          }
        />
      </div>
    </div>
  )
}
