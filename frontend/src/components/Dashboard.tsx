/**
 * Vista principal del dashboard.
 * Resumen de cuenta, P&L global, estrategias activas.
 */

import { useCallback } from 'react'
import { usePolling } from '../hooks/usePolling'
import { getStrategies } from '../services/api'
import type { Strategy, WSEvent } from '../types'
import type { ConnectionStatus } from '../hooks/useWebSocket'
import AccountSummary from './AccountSummary'
import StrategyCard from './StrategyCard'
import PerformanceChart from './PerformanceChart'
import TradeTable from './TradeTable'
import LiveFeed from './LiveFeed'

interface DashboardProps {
  wsStatus: ConnectionStatus
  wsEvents: WSEvent[]
}

export default function Dashboard({ wsStatus, wsEvents }: DashboardProps) {
  const fetchStrategies = useCallback(() => getStrategies(), [])

  const { data: strategies, refresh: refreshStrategies } =
    usePolling<Strategy[]>({
      fetcher: fetchStrategies,
      interval: 8_000,
    })

  return (
    <div className="space-y-6">
      {/* Account summary bar */}
      <AccountSummary wsStatus={wsStatus} />

      {/* Performance chart + Live feed */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <PerformanceChart />
        </div>
        <div className="lg:col-span-1">
          <LiveFeed events={wsEvents} />
        </div>
      </div>

      {/* Strategies */}
      <div>
        <h2 className="text-sm font-semibold text-dark-300 uppercase tracking-wider mb-3">
          Strategies
        </h2>
        {strategies && strategies.length > 0 ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {strategies.map((s) => (
              <StrategyCard
                key={s.name}
                strategy={s}
                onAction={refreshStrategies}
              />
            ))}
          </div>
        ) : (
          <div className="card card-body text-center text-dark-500 py-8">
            <p className="text-sm">No strategies registered</p>
            <p className="text-xs mt-1">
              Add strategies in the backend to see them here
            </p>
          </div>
        )}
      </div>

      {/* Trade history */}
      <TradeTable />
    </div>
  )
}
