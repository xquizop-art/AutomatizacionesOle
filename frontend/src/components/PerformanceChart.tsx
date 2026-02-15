/**
 * Grafico de equity curve y rendimiento.
 * Usa Recharts para visualizar la curva de equity y P&L diario.
 */

import { useCallback, useState } from 'react'
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
} from 'recharts'
import { BarChart3, TrendingUp } from 'lucide-react'
import { clsx } from 'clsx'
import { usePolling } from '../hooks/usePolling'
import { getEquityCurve } from '../services/api'
import type { EquityCurve } from '../types'

type ChartView = 'equity' | 'pnl'

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
}

function formatUsd(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(value)
}

interface CustomTooltipProps {
  active?: boolean
  payload?: Array<{ value: number; dataKey: string }>
  label?: string
}

function EquityTooltip({ active, payload, label }: CustomTooltipProps) {
  if (!active || !payload?.length || !label) return null

  return (
    <div className="bg-dark-800 border border-dark-700 rounded-lg px-3 py-2 shadow-xl text-xs">
      <p className="text-dark-400 mb-1">
        {formatDate(label)} {formatTime(label)}
      </p>
      {payload.map((item) => (
        <p key={item.dataKey} className="text-white font-medium">
          {item.dataKey === 'equity' ? 'Equity' : 'P&L'}:{' '}
          <span
            className={clsx(
              item.dataKey === 'total_pnl' &&
                (item.value >= 0 ? 'text-emerald-400' : 'text-red-400'),
            )}
          >
            {formatUsd(item.value)}
          </span>
        </p>
      ))}
    </div>
  )
}

export default function PerformanceChart() {
  const [view, setView] = useState<ChartView>('equity')

  const fetchCurve = useCallback(() => getEquityCurve(undefined, 500), [])

  const { data: curve, loading } = usePolling<EquityCurve>({
    fetcher: fetchCurve,
    interval: 15_000,
  })

  const points = curve?.points ?? []
  const hasData = points.length > 0

  return (
    <div className="card">
      <div className="card-header flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-blue-400" />
          Performance
        </h2>
        <div className="flex gap-1">
          <button
            onClick={() => setView('equity')}
            className={clsx(
              'px-3 py-1 rounded-md text-xs font-medium transition-colors',
              view === 'equity'
                ? 'bg-blue-600 text-white'
                : 'text-dark-400 hover:text-white hover:bg-dark-700',
            )}
          >
            Equity Curve
          </button>
          <button
            onClick={() => setView('pnl')}
            className={clsx(
              'px-3 py-1 rounded-md text-xs font-medium transition-colors',
              view === 'pnl'
                ? 'bg-blue-600 text-white'
                : 'text-dark-400 hover:text-white hover:bg-dark-700',
            )}
          >
            <BarChart3 className="w-3 h-3 inline mr-1" />
            Daily P&L
          </button>
        </div>
      </div>

      <div className="card-body">
        {loading && !hasData ? (
          <div className="h-[300px] flex items-center justify-center text-dark-500">
            <div className="animate-spin w-6 h-6 border-2 border-dark-600 border-t-blue-500 rounded-full" />
          </div>
        ) : !hasData ? (
          <div className="h-[300px] flex items-center justify-center text-dark-500">
            <div className="text-center">
              <BarChart3 className="w-8 h-8 mx-auto mb-2 opacity-50" />
              <p className="text-sm">No performance data yet</p>
              <p className="text-xs mt-1">
                Data will appear once the engine runs
              </p>
            </div>
          </div>
        ) : view === 'equity' ? (
          <ResponsiveContainer width="100%" height={300}>
            <AreaChart data={points}>
              <defs>
                <linearGradient id="equityGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                  <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2d35" />
              <XAxis
                dataKey="timestamp"
                tickFormatter={formatDate}
                stroke="#4c4e56"
                tick={{ fontSize: 11 }}
                axisLine={false}
              />
              <YAxis
                tickFormatter={(v) => formatUsd(v)}
                stroke="#4c4e56"
                tick={{ fontSize: 11 }}
                axisLine={false}
                width={80}
              />
              <Tooltip content={<EquityTooltip />} />
              <Area
                type="monotone"
                dataKey="equity"
                stroke="#3b82f6"
                strokeWidth={2}
                fill="url(#equityGrad)"
                dot={false}
                activeDot={{ r: 4, fill: '#3b82f6' }}
              />
            </AreaChart>
          </ResponsiveContainer>
        ) : (
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={points}>
              <CartesianGrid strokeDasharray="3 3" stroke="#2a2d35" />
              <XAxis
                dataKey="timestamp"
                tickFormatter={formatDate}
                stroke="#4c4e56"
                tick={{ fontSize: 11 }}
                axisLine={false}
              />
              <YAxis
                tickFormatter={(v) => formatUsd(v)}
                stroke="#4c4e56"
                tick={{ fontSize: 11 }}
                axisLine={false}
                width={80}
              />
              <Tooltip content={<EquityTooltip />} />
              <Bar dataKey="daily_pnl" radius={[3, 3, 0, 0]}>
                {points.map((entry, idx) => (
                  <Cell
                    key={idx}
                    fill={entry.daily_pnl >= 0 ? '#22c55e' : '#ef4444'}
                    fillOpacity={0.8}
                  />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  )
}
