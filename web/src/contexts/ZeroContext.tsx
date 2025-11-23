/**
 * Zero Context
 * Provides WebSocket connection to Zero server for real-time data sync
 */

import { createContext, useContext, useEffect, useState, useCallback, useRef, ReactNode } from 'react'

interface ZeroContextType {
  socket: WebSocket | null
  connected: boolean
  subscribe: (collection: string) => void
  unsubscribe: (collection: string) => void
  data: Map<string, any[]>
  error: Error | null
}

const ZeroContext = createContext<ZeroContextType | null>(null)

// Module-level singleton WebSocket that persists across HMR reloads
let sharedSocket: WebSocket | null = null
let sharedSubscriptions: Set<string> = new Set()

// Vite HMR: Keep socket alive across module reloads
if (import.meta.hot) {
  import.meta.hot.dispose(() => {
    console.log('[Zero HMR] Module reloading, keeping socket alive')
    // Don't close the socket - we'll reuse it
  })
}

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
  const subscriptionsRef = useRef<Set<string>>(new Set()) // Track subscriptions without causing re-renders

  useEffect(() => {
    // Reuse existing socket if it's still open
    if (sharedSocket && (sharedSocket.readyState === WebSocket.OPEN || sharedSocket.readyState === WebSocket.CONNECTING)) {
      console.log('[Zero] Reusing existing WebSocket connection')
      setSocket(sharedSocket)
      setConnected(sharedSocket.readyState === WebSocket.OPEN)
      subscriptionsRef.current = sharedSubscriptions
      return () => {
        // Don't close shared socket on component unmount
        console.log('[Zero] Component unmounting, keeping shared socket alive')
      }
    }

    console.log(`[Zero] Creating new WebSocket connection to ${url}`)
    const ws = new WebSocket(url)
    sharedSocket = ws

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
      sharedSocket = null
      sharedSubscriptions.clear()
      subscriptionsRef.current.clear()
      setSubscriptions(new Set())
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
      // Only close if this is NOT the shared socket (shouldn't happen, but just in case)
      if (ws !== sharedSocket) {
        console.log('[Zero] 🧹 Closing non-shared WebSocket')
        ws.close()
      }
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

    // Check shared subscriptions to avoid duplicates across HMR reloads
    if (sharedSubscriptions.has(collection)) {
      console.log(`[Zero] ℹ️ Already subscribed to ${collection}`)
      return
    }

    // Update shared subscriptions (persists across HMR)
    sharedSubscriptions.add(collection)

    // Also update local ref and state
    subscriptionsRef.current.add(collection)
    setSubscriptions(prev => new Set(prev).add(collection))

    // Send subscription message
    console.log(`[Zero] 📤 Subscribing to ${collection}`)
    socket.send(JSON.stringify({ type: 'subscribe', collection }))
  }, [socket])

  const unsubscribe = useCallback((collection: string) => {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      return
    }

    // Check shared subscriptions
    if (!sharedSubscriptions.has(collection)) {
      return // Not subscribed
    }

    // Update shared subscriptions (persists across HMR)
    sharedSubscriptions.delete(collection)

    // Also update local ref and state
    subscriptionsRef.current.delete(collection)
    setSubscriptions(prev => {
      const next = new Set(prev)
      next.delete(collection)
      return next
    })

    // Send unsubscribe message
    console.log(`Unsubscribing from ${collection}`)
    socket.send(JSON.stringify({ type: 'unsubscribe', collection }))
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
