/**
 * Hook para conexion WebSocket.
 * Recibe datos en tiempo real del backend (trades, senales).
 */

import { useEffect, useRef, useState, useCallback } from 'react'
import type { WSEvent } from '../types'

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error'

interface UseWebSocketOptions {
  /** Channels to subscribe to. Empty = all events. */
  channels?: string[]
  /** Auto-reconnect on disconnect (default true) */
  autoReconnect?: boolean
  /** Max reconnect delay in ms (default 30000) */
  maxReconnectDelay?: number
  /** Called on every event */
  onEvent?: (event: WSEvent) => void
}

interface UseWebSocketReturn {
  status: ConnectionStatus
  lastEvent: WSEvent | null
  events: WSEvent[]
  send: (data: unknown) => void
  connect: () => void
  disconnect: () => void
}

export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    channels = [],
    autoReconnect = true,
    maxReconnectDelay = 30_000,
    onEvent,
  } = options

  const [status, setStatus] = useState<ConnectionStatus>('disconnected')
  const [lastEvent, setLastEvent] = useState<WSEvent | null>(null)
  const [events, setEvents] = useState<WSEvent[]>([])

  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>()
  const reconnectDelay = useRef(1000)
  const intentionalClose = useRef(false)
  const onEventRef = useRef(onEvent)

  // Keep callback ref up to date without triggering reconnections
  useEffect(() => {
    onEventRef.current = onEvent
  }, [onEvent])

  const connect = useCallback(() => {
    // Close any existing connection
    if (wsRef.current) {
      intentionalClose.current = true
      wsRef.current.close()
    }

    intentionalClose.current = false
    setStatus('connecting')

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = window.location.host
    const channelParam = channels.length > 0 ? `?channels=${channels.join(',')}` : ''
    const url = `${protocol}//${host}/ws/live${channelParam}`

    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      setStatus('connected')
      reconnectDelay.current = 1000 // reset on successful connect
    }

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as WSEvent
        setLastEvent(data)
        setEvents((prev) => {
          const next = [data, ...prev]
          // Keep max 200 events in memory
          return next.length > 200 ? next.slice(0, 200) : next
        })
        onEventRef.current?.(data)
      } catch {
        // Ignore non-JSON messages
      }
    }

    ws.onerror = () => {
      setStatus('error')
    }

    ws.onclose = () => {
      setStatus('disconnected')
      wsRef.current = null

      if (!intentionalClose.current && autoReconnect) {
        reconnectTimer.current = setTimeout(() => {
          reconnectDelay.current = Math.min(
            reconnectDelay.current * 2,
            maxReconnectDelay,
          )
          connect()
        }, reconnectDelay.current)
      }
    }
  }, [channels, autoReconnect, maxReconnectDelay])

  const disconnect = useCallback(() => {
    intentionalClose.current = true
    if (reconnectTimer.current) {
      clearTimeout(reconnectTimer.current)
    }
    wsRef.current?.close()
    wsRef.current = null
    setStatus('disconnected')
  }, [])

  const send = useCallback((data: unknown) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data))
    }
  }, [])

  // Connect on mount, disconnect on unmount
  useEffect(() => {
    connect()
    return () => disconnect()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { status, lastEvent, events, send, connect, disconnect }
}
