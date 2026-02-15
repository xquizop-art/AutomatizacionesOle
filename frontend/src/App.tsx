/**
 * App principal del dashboard de trading.
 */

import { useCallback } from 'react'
import { Activity, Github } from 'lucide-react'
import { useWebSocket } from './hooks/useWebSocket'
import { usePolling } from './hooks/usePolling'
import { getEngineStatus } from './services/api'
import type { EngineStatus } from './types'
import Dashboard from './components/Dashboard'

export default function App() {
  const { status: wsStatus, events } = useWebSocket()

  const fetchEngine = useCallback(() => getEngineStatus(), [])
  const { data: engineStatus } = usePolling<EngineStatus>({
    fetcher: fetchEngine,
    interval: 10_000,
  })

  const engineRunning = engineStatus?.engine_status === 'running'

  return (
    <div className="min-h-screen bg-dark-950">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-dark-900/80 backdrop-blur-md border-b border-dark-800">
        <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-14">
            {/* Logo + Title */}
            <div className="flex items-center gap-3">
              <div className="bg-gradient-to-br from-blue-500 to-blue-700 rounded-lg p-1.5">
                <Activity className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="text-sm font-bold text-white tracking-tight">
                  AutomatizacionesOle
                </h1>
                <p className="text-[10px] text-dark-400 -mt-0.5">
                  Trading Dashboard
                </p>
              </div>
            </div>

            {/* Right side info */}
            <div className="flex items-center gap-4">
              {/* Engine status */}
              <div className="flex items-center gap-2 text-xs">
                <span
                  className={
                    engineRunning
                      ? 'w-2 h-2 rounded-full bg-emerald-400 animate-pulse'
                      : 'w-2 h-2 rounded-full bg-dark-600'
                  }
                />
                <span className="text-dark-300">
                  Engine:{' '}
                  <span
                    className={
                      engineRunning ? 'text-emerald-400' : 'text-dark-500'
                    }
                  >
                    {engineStatus?.engine_status ?? 'unknown'}
                  </span>
                </span>
              </div>

              {/* Cycles counter */}
              {engineStatus && (
                <span className="text-xs text-dark-500 hidden sm:inline">
                  {engineStatus.total_cycles} cycles ·{' '}
                  {engineStatus.total_orders_submitted} orders
                </span>
              )}

              {/* WS connections */}
              {engineStatus && (
                <span className="text-xs text-dark-500 hidden md:inline">
                  {engineStatus.websocket_connections} WS conn
                </span>
              )}

              <a
                href="http://localhost:8000/docs"
                target="_blank"
                rel="noopener noreferrer"
                className="btn-ghost text-xs py-1 px-2"
                title="API Docs"
              >
                <Github className="w-3.5 h-3.5" />
                API
              </a>
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <Dashboard wsStatus={wsStatus} wsEvents={events} />
      </main>

      {/* Footer */}
      <footer className="border-t border-dark-800 mt-8">
        <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <p className="text-xs text-dark-600 text-center">
            AutomatizacionesOle Trading Bot · Alpaca Markets ·{' '}
            {new Date().getFullYear()}
          </p>
        </div>
      </footer>
    </div>
  )
}
