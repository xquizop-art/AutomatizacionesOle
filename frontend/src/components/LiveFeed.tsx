/**
 * Live event feed from WebSocket.
 * Shows real-time events: orders, signals, errors.
 */

import {
  Zap,
  ArrowUpRight,
  ArrowDownRight,
  AlertTriangle,
  Radio,
  ShieldAlert,
  RefreshCw,
} from 'lucide-react'
import { clsx } from 'clsx'
import type { WSEvent } from '../types'

interface LiveFeedProps {
  events: WSEvent[]
}

function formatTime(ts?: string): string {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function EventIcon({ event }: { event: string }) {
  switch (event) {
    case 'order_submitted':
      return <ArrowUpRight className="w-3.5 h-3.5 text-blue-400" />
    case 'signal_generated':
      return <Zap className="w-3.5 h-3.5 text-amber-400" />
    case 'strategy_started':
      return <Radio className="w-3.5 h-3.5 text-emerald-400" />
    case 'strategy_stopped':
      return <Radio className="w-3.5 h-3.5 text-dark-400" />
    case 'strategy_error':
      return <AlertTriangle className="w-3.5 h-3.5 text-red-400" />
    case 'risk_rejected':
      return <ShieldAlert className="w-3.5 h-3.5 text-red-400" />
    case 'cycle_completed':
      return <RefreshCw className="w-3.5 h-3.5 text-dark-500" />
    default:
      return <Zap className="w-3.5 h-3.5 text-dark-500" />
  }
}

function formatEventMessage(e: WSEvent): string {
  switch (e.event) {
    case 'order_submitted':
      return `Order: ${e.side as string} ${e.qty} ${e.symbol} @ ${e.price ?? 'market'} [${e.strategy}]`
    case 'signal_generated': {
      const signals = e.signals as Record<string, string>
      const parts = Object.entries(signals)
        .map(([sym, sig]) => `${sym}:${sig}`)
        .join(', ')
      return `Signal: ${parts} [${e.strategy}]`
    }
    case 'strategy_started':
      return `Strategy started: ${e.strategy}`
    case 'strategy_stopped':
      return `Strategy stopped: ${e.strategy}`
    case 'strategy_error':
      return `Error in ${e.strategy}: ${e.error}`
    case 'risk_rejected':
      return `Risk rejected: ${e.side} ${e.qty} ${e.symbol} - ${e.reason} [${e.strategy}]`
    case 'cycle_completed':
      return `Cycle: ${e.strategy} - ${e.orders_submitted ?? 0} orders`
    case 'engine_started':
      return `Engine started - ${e.strategies_available} strategies available`
    case 'engine_stopped':
      return `Engine stopped - ${e.total_cycles} cycles, ${e.total_orders} orders`
    case 'connected':
      return e.message as string || 'Connected to WebSocket'
    default:
      return `${e.event}: ${JSON.stringify(e)}`
  }
}

const EVENT_FILTER = new Set([
  'order_submitted',
  'signal_generated',
  'strategy_started',
  'strategy_stopped',
  'strategy_error',
  'risk_rejected',
  'engine_started',
  'engine_stopped',
  'connected',
])

export default function LiveFeed({ events }: LiveFeedProps) {
  const filtered = events.filter((e) => EVENT_FILTER.has(e.event)).slice(0, 50)

  return (
    <div className="card">
      <div className="card-header flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white flex items-center gap-2">
          <Radio className="w-4 h-4 text-emerald-400" />
          Live Feed
          {filtered.length > 0 && (
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          )}
        </h2>
      </div>
      <div className="max-h-[280px] overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="px-5 py-8 text-center text-dark-500 text-sm">
            No events yet. Events will appear when the engine is running.
          </div>
        ) : (
          <div className="divide-y divide-dark-800/50">
            {filtered.map((e, idx) => (
              <div
                key={idx}
                className={clsx(
                  'flex items-start gap-2.5 px-4 py-2.5 text-xs hover:bg-dark-800/30 transition-colors',
                  idx === 0 && 'bg-dark-800/20',
                )}
              >
                <div className="mt-0.5 shrink-0">
                  <EventIcon event={e.event} />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-dark-200 leading-relaxed break-words">
                    {formatEventMessage(e)}
                  </p>
                </div>
                <span className="text-dark-500 shrink-0 tabular-nums">
                  {formatTime(e.timestamp)}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
