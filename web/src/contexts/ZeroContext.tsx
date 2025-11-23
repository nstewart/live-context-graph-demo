/**
 * Zero Context
 * Provides WebSocket connection to Zero server for real-time data sync
 */

import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react'

interface ZeroContextType {
  socket: WebSocket | null
  connected: boolean
  subscribe: (collection: string) => void
  unsubscribe: (collection: string) => void
  data: Map<string, any[]>
  error: Error | null
}

const ZeroContext = createContext<ZeroContextType | null>(null)

export function useZeroContext() {
  const context = useContext(ZeroContext)
  if (!context) {
    throw new Error('useZeroContext must be used within a ZeroProvider')
  }
  return context
}

interface ZeroProviderProps {
  children: ReactNode
  url?: string
}

export function ZeroProvider({ children, url: customUrl }: ZeroProviderProps) {
  // Browser runs on host, connects directly to localhost
  const defaultUrl = import.meta.env.VITE_ZERO_URL || 'ws://localhost:8090'
  const url = customUrl || defaultUrl
  const [socket, setSocket] = useState<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)
  const [data, setData] = useState<Map<string, any[]>>(new Map())
  const [error, setError] = useState<Error | null>(null)
  const [subscriptions, setSubscriptions] = useState<Set<string>>(new Set())

  useEffect(() => {
    console.log(`[Zero] Connecting to Zero server at ${url}`)
    const ws = new WebSocket(url)

    ws.onopen = () => {
      console.log('[Zero] ✅ Connected to Zero server')
      setConnected(true)
      setError(null)
    }

    ws.onclose = (event) => {
      console.log('[Zero] 🔌 Disconnected from Zero server')
      console.log('  Close code:', event.code)
      console.log('  Close reason:', event.reason || '(no reason provided)')
      console.log('  Was clean:', event.wasClean)
      setConnected(false)
    }

    ws.onerror = (event) => {
      console.error('[Zero] ❌ WebSocket error:', event)
      console.error('  URL:', url)
      console.error('  ReadyState:', ws.readyState, '(0=CONNECTING, 1=OPEN, 2=CLOSING, 3=CLOSED)')
      setError(new Error('WebSocket connection error'))
    }

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data)
        console.log('[Zero] 📥 Received message:', message.type)
        handleMessage(message)
      } catch (err) {
        console.error('[Zero] ❌ Error parsing message:', err)
      }
    }

    setSocket(ws)

    return () => {
      console.log('[Zero] 🧹 Cleaning up WebSocket connection')
      ws.close()
    }
  }, [url])

  const handleMessage = useCallback((message: any) => {
    switch (message.type) {
      case 'connected':
        console.log('Server acknowledged connection, collections:', message.collections)
        break

      case 'initial-state':
        console.log(`Received initial state for ${message.collection}:`, message.data?.length, 'items')
        setData(prev => {
          const next = new Map(prev)
          next.set(message.collection, message.data || [])
          return next
        })
        break

      case 'changes':
        console.log(`Received ${message.changes?.length} changes`)
        // Apply changes to data
        message.changes?.forEach((change: any) => {
          setData(prev => {
            const next = new Map(prev)
            const collection = change.collection
            const currentData = next.get(collection) || []

            switch (change.operation) {
              case 'insert':
              case 'update':
                // Find existing item or add new one
                const existingIndex = currentData.findIndex((item: any) => item.id === change.data.id)
                if (existingIndex >= 0) {
                  currentData[existingIndex] = change.data
                } else {
                  currentData.push(change.data)
                }
                break

              case 'delete':
                const deleteIndex = currentData.findIndex((item: any) => item.id === change.data.id)
                if (deleteIndex >= 0) {
                  currentData.splice(deleteIndex, 1)
                }
                break
            }

            next.set(collection, [...currentData])
            return next
          })
        })
        break

      default:
        console.log('Unknown message type:', message.type)
    }
  }, [])

  const subscribe = useCallback((collection: string) => {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      console.warn(`[Zero] ⚠️ Cannot subscribe to ${collection}, socket not connected (state: ${socket?.readyState})`)
      return
    }

    if (subscriptions.has(collection)) {
      console.log(`[Zero] ℹ️ Already subscribed to ${collection}`)
      return
    }

    console.log(`[Zero] 📤 Subscribing to ${collection}`)
    socket.send(JSON.stringify({ type: 'subscribe', collection }))
    setSubscriptions(prev => new Set(prev).add(collection))
  }, [socket, subscriptions])

  const unsubscribe = useCallback((collection: string) => {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return
    }

    console.log(`Unsubscribing from ${collection}`)
    socket.send(JSON.stringify({ type: 'unsubscribe', collection }))
    setSubscriptions(prev => {
      const next = new Set(prev)
      next.delete(collection)
      return next
    })
  }, [socket])

  const value: ZeroContextType = {
    socket,
    connected,
    subscribe,
    unsubscribe,
    data,
    error,
  }

  return <ZeroContext.Provider value={value}>{children}</ZeroContext.Provider>
}
