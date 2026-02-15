/**
 * Tabla de operaciones ejecutadas.
 * Filtros por estrategia, fecha, simbolo, resultado.
 */

import { useCallback, useState } from 'react'
import {
  ArrowUpRight,
  ArrowDownRight,
  ChevronLeft,
  ChevronRight,
  Filter,
  ListOrdered,
} from 'lucide-react'
import { clsx } from 'clsx'
import { usePolling } from '../hooks/usePolling'
import { getTrades, type TradeFilters } from '../services/api'
import type { TradeList, Trade } from '../types'

function formatUsd(value: number | null): string {
  if (value == null) return '--'
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
  }).format(value)
}

function formatDateTime(iso: string | null): string {
  if (!iso) return '--'
  const d = new Date(iso)
  return d.toLocaleString('en-US', {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function StatusBadge({ status }: { status: string }) {
  const styles: Record<string, string> = {
    filled: 'badge-green',
    pending: 'badge-yellow',
    submitted: 'badge-blue',
    rejected: 'badge-red',
    error: 'badge-red',
    cancelled: 'badge-gray',
  }

  return (
    <span className={clsx('badge', styles[status] ?? 'badge-gray')}>
      {status}
    </span>
  )
}

function SideBadge({ side }: { side: string }) {
  const isBuy = side === 'buy'
  return (
    <span
      className={clsx(
        'inline-flex items-center gap-0.5 text-xs font-semibold',
        isBuy ? 'text-emerald-400' : 'text-red-400',
      )}
    >
      {isBuy ? (
        <ArrowUpRight className="w-3.5 h-3.5" />
      ) : (
        <ArrowDownRight className="w-3.5 h-3.5" />
      )}
      {side.toUpperCase()}
    </span>
  )
}

function PnlCell({ value }: { value: number | null }) {
  if (value == null) return <span className="text-dark-500">--</span>
  return (
    <span
      className={clsx(
        'font-mono text-xs font-medium',
        value > 0 && 'text-emerald-400',
        value < 0 && 'text-red-400',
        value === 0 && 'text-dark-400',
      )}
    >
      {value > 0 ? '+' : ''}
      {formatUsd(value)}
    </span>
  )
}

function TradeRow({ trade }: { trade: Trade }) {
  return (
    <tr className="border-b border-dark-800 hover:bg-dark-800/50 transition-colors">
      <td className="px-4 py-3 text-xs text-dark-400 font-mono">
        {trade.id}
      </td>
      <td className="px-4 py-3 text-xs text-dark-200">
        {formatDateTime(trade.created_at)}
      </td>
      <td className="px-4 py-3">
        <span className="text-xs font-medium text-blue-400">
          {trade.strategy_name}
        </span>
      </td>
      <td className="px-4 py-3">
        <span className="px-2 py-0.5 bg-dark-800 rounded text-xs font-mono text-white">
          {trade.symbol}
        </span>
      </td>
      <td className="px-4 py-3">
        <SideBadge side={trade.side} />
      </td>
      <td className="px-4 py-3 text-xs font-mono text-dark-200 text-right">
        {trade.filled_qty ?? trade.qty}
      </td>
      <td className="px-4 py-3 text-xs font-mono text-dark-200 text-right">
        {formatUsd(trade.filled_avg_price)}
      </td>
      <td className="px-4 py-3 text-right">
        <PnlCell value={trade.realized_pnl} />
      </td>
      <td className="px-4 py-3">
        <StatusBadge status={trade.status} />
      </td>
    </tr>
  )
}

export default function TradeTable() {
  const [page, setPage] = useState(1)
  const [filters, setFilters] = useState<TradeFilters>({
    page: 1,
    page_size: 20,
  })
  const [showFilters, setShowFilters] = useState(false)

  // Local filter state for the form
  const [filterStrategy, setFilterStrategy] = useState('')
  const [filterSymbol, setFilterSymbol] = useState('')
  const [filterSide, setFilterSide] = useState('')
  const [filterStatus, setFilterStatus] = useState('')

  const fetchTrades = useCallback(
    () => getTrades({ ...filters, page }),
    [filters, page],
  )

  const { data, loading } = usePolling<TradeList>({
    fetcher: fetchTrades,
    interval: 10_000,
  })

  function applyFilters() {
    setFilters({
      ...filters,
      strategy: filterStrategy || undefined,
      symbol: filterSymbol || undefined,
      side: filterSide || undefined,
      status: filterStatus || undefined,
    })
    setPage(1)
  }

  function clearFilters() {
    setFilterStrategy('')
    setFilterSymbol('')
    setFilterSide('')
    setFilterStatus('')
    setFilters({ page: 1, page_size: 20 })
    setPage(1)
  }

  const trades = data?.trades ?? []
  const totalPages = data?.total_pages ?? 1
  const total = data?.total ?? 0

  return (
    <div className="card">
      <div className="card-header flex items-center justify-between">
        <h2 className="text-sm font-semibold text-white flex items-center gap-2">
          <ListOrdered className="w-4 h-4 text-blue-400" />
          Trade History
          {total > 0 && (
            <span className="badge badge-gray ml-1">{total}</span>
          )}
        </h2>
        <button
          onClick={() => setShowFilters((v) => !v)}
          className={clsx(
            'btn-ghost text-xs',
            showFilters && 'bg-dark-700 text-white',
          )}
        >
          <Filter className="w-3.5 h-3.5" />
          Filters
        </button>
      </div>

      {/* Filters panel */}
      {showFilters && (
        <div className="px-5 py-3 border-b border-dark-700 bg-dark-900/50">
          <div className="flex flex-wrap gap-3 items-end">
            <div>
              <label className="text-xs text-dark-400 block mb-1">
                Strategy
              </label>
              <input
                type="text"
                value={filterStrategy}
                onChange={(e) => setFilterStrategy(e.target.value)}
                placeholder="All"
                className="bg-dark-800 border border-dark-700 rounded-md px-3 py-1.5 text-xs text-white w-32 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="text-xs text-dark-400 block mb-1">
                Symbol
              </label>
              <input
                type="text"
                value={filterSymbol}
                onChange={(e) => setFilterSymbol(e.target.value)}
                placeholder="All"
                className="bg-dark-800 border border-dark-700 rounded-md px-3 py-1.5 text-xs text-white w-24 focus:outline-none focus:ring-1 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="text-xs text-dark-400 block mb-1">Side</label>
              <select
                value={filterSide}
                onChange={(e) => setFilterSide(e.target.value)}
                className="bg-dark-800 border border-dark-700 rounded-md px-3 py-1.5 text-xs text-white w-24 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="">All</option>
                <option value="buy">Buy</option>
                <option value="sell">Sell</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-dark-400 block mb-1">
                Status
              </label>
              <select
                value={filterStatus}
                onChange={(e) => setFilterStatus(e.target.value)}
                className="bg-dark-800 border border-dark-700 rounded-md px-3 py-1.5 text-xs text-white w-28 focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                <option value="">All</option>
                <option value="filled">Filled</option>
                <option value="pending">Pending</option>
                <option value="rejected">Rejected</option>
                <option value="error">Error</option>
              </select>
            </div>
            <button onClick={applyFilters} className="btn-primary text-xs">
              Apply
            </button>
            <button onClick={clearFilters} className="btn-ghost text-xs">
              Clear
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-dark-700">
              <th className="px-4 py-3 text-xs font-medium text-dark-400 uppercase tracking-wider">
                #
              </th>
              <th className="px-4 py-3 text-xs font-medium text-dark-400 uppercase tracking-wider">
                Date
              </th>
              <th className="px-4 py-3 text-xs font-medium text-dark-400 uppercase tracking-wider">
                Strategy
              </th>
              <th className="px-4 py-3 text-xs font-medium text-dark-400 uppercase tracking-wider">
                Symbol
              </th>
              <th className="px-4 py-3 text-xs font-medium text-dark-400 uppercase tracking-wider">
                Side
              </th>
              <th className="px-4 py-3 text-xs font-medium text-dark-400 uppercase tracking-wider text-right">
                Qty
              </th>
              <th className="px-4 py-3 text-xs font-medium text-dark-400 uppercase tracking-wider text-right">
                Price
              </th>
              <th className="px-4 py-3 text-xs font-medium text-dark-400 uppercase tracking-wider text-right">
                P&L
              </th>
              <th className="px-4 py-3 text-xs font-medium text-dark-400 uppercase tracking-wider">
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {loading && trades.length === 0 ? (
              <tr>
                <td
                  colSpan={9}
                  className="px-4 py-12 text-center text-dark-500"
                >
                  <div className="animate-spin w-5 h-5 border-2 border-dark-600 border-t-blue-500 rounded-full mx-auto" />
                </td>
              </tr>
            ) : trades.length === 0 ? (
              <tr>
                <td
                  colSpan={9}
                  className="px-4 py-12 text-center text-dark-500 text-sm"
                >
                  No trades found
                </td>
              </tr>
            ) : (
              trades.map((trade) => (
                <TradeRow key={trade.id} trade={trade} />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="px-5 py-3 border-t border-dark-700 flex items-center justify-between">
          <span className="text-xs text-dark-400">
            Page {page} of {totalPages} ({total} trades)
          </span>
          <div className="flex gap-1">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="btn-ghost text-xs p-1.5"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="btn-ghost text-xs p-1.5"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
