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
  const initialStateReceived = useRef<Set<string>>(new Set()) // Track which collections have received initial state
  const pendingChanges = useRef<Map<string, any[]>>(new Map()) // Queue changes until initial state is received
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null)
  const reconnectAttemptsRef = useRef(0)

  const connectWebSocket = useCallback(() => {
    // Clear any existing reconnect timeout
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current)
      reconnectTimeoutRef.current = null
    }

    // Reuse existing socket if it's still open
    if (sharedSocket && (sharedSocket.readyState === WebSocket.OPEN || sharedSocket.readyState === WebSocket.CONNECTING)) {
      console.log('[Zero] Reusing existing WebSocket connection')
      setSocket(sharedSocket)
      setConnected(sharedSocket.readyState === WebSocket.OPEN)
      subscriptionsRef.current = sharedSubscriptions
      return
    }

    console.log(`[Zero] Creating new WebSocket connection to ${url}`)
    const ws = new WebSocket(url)
    sharedSocket = ws

    ws.onopen = () => {
      console.log('[Zero] ✅ Connected to Zero server')
      setConnected(true)
      setError(null)
      reconnectAttemptsRef.current = 0 // Reset reconnect attempts on successful connection

      // Resubscribe to all collections that were previously subscribed
      sharedSubscriptions.forEach(collection => {
        console.log(`[Zero] 🔄 Resubscribing to ${collection} after reconnect`)
        ws.send(JSON.stringify({ type: 'subscribe', collection }))
      })
    }

    ws.onclose = (event) => {
      console.log('[Zero] 🔌 Disconnected from Zero server')
      console.log('  Close code:', event.code)
      console.log('  Close reason:', event.reason || '(no reason provided)')
      console.log('  Was clean:', event.wasClean)
      setConnected(false)
      sharedSocket = null

      // Don't clear subscriptions - we want to resubscribe on reconnect
      // sharedSubscriptions.clear()

      // Attempt to reconnect with exponential backoff
      const backoffDelay = Math.min(1000 * Math.pow(2, reconnectAttemptsRef.current), 10000) // Max 10 seconds
      reconnectAttemptsRef.current++
      console.log(`[Zero] 🔄 Reconnecting in ${backoffDelay}ms (attempt ${reconnectAttemptsRef.current})`)

      reconnectTimeoutRef.current = setTimeout(() => {
        console.log('[Zero] 🔄 Attempting to reconnect...')
        connectWebSocket()
      }, backoffDelay)
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
        console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
        console.log('🔔 [Zero] MESSAGE RECEIVED:', message.type)
        if (message.type === 'changes') {
          console.log(`   Changes count: ${message.changes?.length}`)
          if (message.changes?.length > 0) {
            message.changes.forEach((c: any, i: number) => {
              console.log(`   Change ${i + 1}: ${c.operation} ${c.collection}`, c.data.order_number || c.data.id)
            })
          }
        }
        console.log('━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━')
        handleMessage(message)
      } catch (err) {
        console.error('[Zero] ❌ Error parsing message:', err, event.data)
      }
    }

    setSocket(ws)
  }, [url])

  useEffect(() => {
    connectWebSocket()

    return () => {
      // Cleanup on unmount
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
        reconnectTimeoutRef.current = null
      }
      // Don't close shared socket on component unmount
      console.log('[Zero] Component unmounting, keeping shared socket alive')
    }
  }, [connectWebSocket])

  const handleMessage = useCallback((message: any) => {
    switch (message.type) {
      case 'connected':
        console.log('Server acknowledged connection, collections:', message.collections)
        break

      case 'initial-state':
        console.log(`Received initial state for ${message.collection}:`, message.data?.length, 'items')
        if (message.data?.length > 0) {
          console.log('First item from initial state:', message.data[0])
          console.log('First item ID field:', message.data[0].id)
        }

        // Mark that we've received initial state for this collection
        initialStateReceived.current.add(message.collection)

        setData(prev => {
          const next = new Map(prev)
          next.set(message.collection, message.data || [])

          // Apply any pending changes that arrived before initial state
          const pending = pendingChanges.current.get(message.collection)
          if (pending && pending.length > 0) {
            console.log(`Applying ${pending.length} pending changes that arrived before initial state`)

            // Process pending changes
            const currentData = [...(next.get(message.collection) || [])]
            pending.forEach((change: any) => {
              const changeId = change.data.id || change.data.order_id

              if (change.operation === 'insert' || change.operation === 'update') {
                const existingIndex = currentData.findIndex((item: any) => {
                  const itemId = item.id || item.order_id
                  return itemId === changeId
                })
                if (existingIndex >= 0) {
                  currentData[existingIndex] = change.data
                } else {
                  currentData.push(change.data)
                }
              } else if (change.operation === 'delete') {
                const deleteIndex = currentData.findIndex((item: any) => {
                  const itemId = item.id || item.order_id
                  return itemId === changeId
                })
                if (deleteIndex >= 0) {
                  currentData.splice(deleteIndex, 1)
                }
              }
            })

            next.set(message.collection, currentData)
            pendingChanges.current.delete(message.collection)
          }

          return next
        })
        break

      case 'changes':
        console.log(`Received ${message.changes?.length} changes`)
        console.error(`🚨 CHANGES MESSAGE RECEIVED! Count: ${message.changes?.length}`)
        document.title = `🔔 ${message.changes?.length} changes - ${Date.now()}`

        // Check if any changes are for collections that haven't received initial state yet
        const changesForUninitializedCollections = message.changes?.filter((change: any) =>
          !initialStateReceived.current.has(change.collection)
        )

        if (changesForUninitializedCollections?.length > 0) {
          console.log(`Queueing ${changesForUninitializedCollections.length} changes until initial state is received`)
          changesForUninitializedCollections.forEach((change: any) => {
            if (!pendingChanges.current.has(change.collection)) {
              pendingChanges.current.set(change.collection, [])
            }
            pendingChanges.current.get(change.collection)!.push(change)
          })
        }

        // Only apply changes for collections that have received initial state
        const changesToApply = message.changes?.filter((change: any) =>
          initialStateReceived.current.has(change.collection)
        )

        if (!changesToApply || changesToApply.length === 0) {
          break
        }

        // Apply ALL changes in a single state update to avoid race conditions
        setData(prev => {
          const next = new Map(prev)
          console.log(`⚙️ Before update: ${prev.get('orders')?.length || 0} orders`)

          // Group changes by collection
          const changesByCollection = new Map<string, any[]>()
          changesToApply.forEach((change: any) => {
            const collection = change.collection
            if (!changesByCollection.has(collection)) {
              changesByCollection.set(collection, [])
            }
            changesByCollection.get(collection)!.push(change)
          })

          // Apply all changes for each collection
          changesByCollection.forEach((changes, collection) => {
            // Get a COPY of the current data to avoid mutations
            const currentData = [...(next.get(collection) || [])]

            // Group changes by ID to handle Materialize differential updates
            // Materialize sends: INSERT (new state) + DELETE (old state) for updates
            const changesByItemId = new Map<string, { insert?: any; delete?: any }>()
            changes.forEach((change: any) => {
              const changeId = change.data.id || change.data.order_id
              if (!changesByItemId.has(changeId)) {
                changesByItemId.set(changeId, {})
              }
              const itemChanges = changesByItemId.get(changeId)!
              if (change.operation === 'insert' || change.operation === 'update') {
                itemChanges.insert = change
              } else if (change.operation === 'delete') {
                itemChanges.delete = change
              }
            })

            // Apply consolidated changes: if both INSERT and DELETE exist, only apply INSERT
            changesByItemId.forEach((itemChanges, changeId) => {
              if (itemChanges.insert) {
                // INSERT or UPDATE: apply the new state
                const change = itemChanges.insert
                console.log(`Applying ${change.operation} to ${collection}:`, changeId, change.data)

                const existingIndex = currentData.findIndex((item: any) => {
                  const itemId = item.id || item.order_id
                  return itemId === changeId
                })
                if (existingIndex >= 0) {
                  console.log(`  → Updating existing item at index ${existingIndex}`)
                  console.log(`     Old:`, currentData[existingIndex].order_status || currentData[existingIndex].status)
                  console.log(`     New:`, change.data.order_status || change.data.status)
                  currentData[existingIndex] = change.data
                } else {
                  console.log(`  → Adding new item (not found in ${currentData.length} items)`)
                  currentData.push(change.data)
                }

                // If there's also a DELETE, it's just the old state - ignore it
                if (itemChanges.delete) {
                  console.log(`  → Ignoring accompanying DELETE (Materialize differential update)`)
                }
              } else if (itemChanges.delete) {
                // Only DELETE without INSERT: actual deletion
                const change = itemChanges.delete
                console.log(`Applying delete to ${collection}:`, changeId)

                const deleteIndex = currentData.findIndex((item: any) => {
                  const itemId = item.id || item.order_id
                  return itemId === changeId
                })
                if (deleteIndex >= 0) {
                  console.log(`  → Deleting item at index ${deleteIndex}`)
                  currentData.splice(deleteIndex, 1)
                } else {
                  console.log(`  → Delete skipped (item not found)`)
                }
              }
            })

            next.set(collection, currentData)
            console.log(`⚙️ After update: ${next.get('orders')?.length || 0} orders in collection '${collection}'`)
          })

          return next
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
