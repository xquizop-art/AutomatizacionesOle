/**
 * Generic polling hook for periodic data fetching.
 */

import { useEffect, useRef, useState, useCallback } from 'react'

interface UsePollingOptions<T> {
  /** Async function to fetch data */
  fetcher: () => Promise<T>
  /** Polling interval in ms (default 5000) */
  interval?: number
  /** Start polling immediately (default true) */
  enabled?: boolean
}

interface UsePollingReturn<T> {
  data: T | null
  error: string | null
  loading: boolean
  refresh: () => Promise<void>
}

export function usePolling<T>({
  fetcher,
  interval = 5000,
  enabled = true,
}: UsePollingOptions<T>): UsePollingReturn<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const fetcherRef = useRef(fetcher)

  useEffect(() => {
    fetcherRef.current = fetcher
  }, [fetcher])

  const refresh = useCallback(async () => {
    try {
      const result = await fetcherRef.current()
      setData(result)
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error fetching data')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!enabled) return

    refresh()
    const id = setInterval(refresh, interval)
    return () => clearInterval(id)
  }, [enabled, interval, refresh])

  return { data, error, loading, refresh }
}
