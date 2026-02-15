/**
 * Tarjeta de estrategia individual.
 * Muestra estado, parametros, boton start/stop.
 */

import { useState } from 'react'
import { Play, Square, Clock, Zap, Tag, BarChart3, Settings2 } from 'lucide-react'
import { clsx } from 'clsx'
import type { Strategy } from '../types'
import { startStrategy, stopStrategy } from '../services/api'

interface StrategyCardProps {
  strategy: Strategy
  onAction?: () => void
}

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { class: string; label: string }> = {
    running: { class: 'badge-green', label: 'Running' },
    stopped: { class: 'badge-gray', label: 'Stopped' },
    idle: { class: 'badge-gray', label: 'Idle' },
    error: { class: 'badge-red', label: 'Error' },
  }

  const c = config[status] || config.idle!

  return (
    <span className={clsx('badge', c.class)}>
      {status === 'running' && (
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 animate-pulse" />
      )}
      {c.label}
    </span>
  )
}

export default function StrategyCard({ strategy, onAction }: StrategyCardProps) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const isRunning = strategy.status === 'running'

  async function handleToggle() {
    setLoading(true)
    setError(null)
    try {
      if (isRunning) {
        await stopStrategy(strategy.name)
      } else {
        await startStrategy(strategy.name)
      }
      onAction?.()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Action failed')
    } finally {
      setLoading(false)
    }
  }

  const params = Object.entries(strategy.parameters)

  return (
    <div
      className={clsx(
        'card overflow-hidden transition-all duration-200 hover:border-dark-600',
        isRunning && 'border-emerald-500/30',
      )}
    >
      {/* Header */}
      <div className="card-header flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <div
            className={clsx(
              'p-1.5 rounded-lg',
              isRunning
                ? 'bg-emerald-500/10 text-emerald-400'
                : 'bg-dark-700 text-dark-400',
            )}
          >
            <BarChart3 className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <h3 className="text-sm font-semibold text-white truncate">
              {strategy.name}
            </h3>
            <p className="text-xs text-dark-400 truncate">
              {strategy.description}
            </p>
          </div>
        </div>
        <StatusBadge status={strategy.status} />
      </div>

      {/* Body */}
      <div className="card-body space-y-3">
        {/* Symbols */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <Tag className="w-3.5 h-3.5 text-dark-400 shrink-0" />
          {strategy.symbols.map((sym) => (
            <span
              key={sym}
              className="px-2 py-0.5 bg-dark-800 rounded text-xs font-mono text-dark-200"
            >
              {sym}
            </span>
          ))}
        </div>

        {/* Timeframe & Signals */}
        <div className="flex items-center gap-4 text-xs text-dark-400">
          <span className="inline-flex items-center gap-1">
            <Clock className="w-3.5 h-3.5" />
            {strategy.timeframe}
          </span>
          <span className="inline-flex items-center gap-1">
            <Zap className="w-3.5 h-3.5" />
            {strategy.total_signals} signals
          </span>
          {strategy.last_run && (
            <span className="inline-flex items-center gap-1 truncate">
              Last: {new Date(strategy.last_run).toLocaleTimeString()}
            </span>
          )}
        </div>

        {/* Parameters */}
        {params.length > 0 && (
          <div className="bg-dark-900/50 rounded-lg p-3 space-y-1">
            <div className="flex items-center gap-1.5 text-xs text-dark-400 mb-2">
              <Settings2 className="w-3 h-3" />
              Parameters
            </div>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1">
              {params.map(([key, val]) => (
                <div key={key} className="flex justify-between text-xs">
                  <span className="text-dark-400 truncate mr-2">{key}</span>
                  <span className="text-dark-200 font-mono">
                    {String(val)}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Error message */}
        {error && (
          <p className="text-xs text-red-400 bg-red-500/10 rounded px-2 py-1">
            {error}
          </p>
        )}

        {/* Action button */}
        <button
          onClick={handleToggle}
          disabled={loading}
          className={clsx(
            'w-full',
            isRunning ? 'btn-danger' : 'btn-success',
          )}
        >
          {loading ? (
            <span className="animate-spin w-4 h-4 border-2 border-white/30 border-t-white rounded-full" />
          ) : isRunning ? (
            <>
              <Square className="w-4 h-4" />
              Stop Strategy
            </>
          ) : (
            <>
              <Play className="w-4 h-4" />
              Start Strategy
            </>
          )}
        </button>
      </div>
    </div>
  )
}
