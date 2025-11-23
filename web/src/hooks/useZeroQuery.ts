/**
 * useZeroQuery Hook
 * Provides React Query-like interface for real-time data from Zero server
 */

import { useEffect, useMemo } from 'react'
import { useZeroContext } from '../contexts/ZeroContext'

export interface UseZeroQueryOptions<T = any> {
  collection: string
  filter?: (item: T) => boolean
  enabled?: boolean
}

export interface UseZeroQueryResult<T = any> {
  data: T[] | undefined
  isLoading: boolean
  error: Error | null
  connected: boolean
}

export function useZeroQuery<T = any>(
  options: UseZeroQueryOptions<T>
): UseZeroQueryResult<T> {
  const { collection, filter, enabled = true } = options
  const { subscribe, unsubscribe, data, connected, error } = useZeroContext()

  // Subscribe to collection when component mounts, enabled changes, or connection is established
  useEffect(() => {
    if (!enabled) return
    if (!connected) return // Wait for connection before subscribing

    subscribe(collection)

    return () => {
      unsubscribe(collection)
    }
  }, [collection, enabled, connected, subscribe, unsubscribe])

  // Get data for this collection and apply filter if provided
  const filteredData = useMemo(() => {
    const collectionData = data.get(collection)
    if (!collectionData) return undefined

    if (filter) {
      return collectionData.filter(filter) as T[]
    }

    return collectionData as T[]
  }, [data, collection, filter])

  return {
    data: filteredData,
    isLoading: !connected || (connected && filteredData === undefined),
    error,
    connected,
  }
}

/**
 * Hook for orders collection with optional status filter
 */
export function useOrdersZero(statusFilter?: string) {
  return useZeroQuery({
    collection: 'orders',
    filter: statusFilter
      ? (order: any) => order.order_status === statusFilter
      : undefined,
  })
}

/**
 * Hook for stores collection
 */
export function useStoresZero() {
  return useZeroQuery({
    collection: 'stores',
  })
}

/**
 * Hook for couriers collection with optional status filter
 */
export function useCouriersZero(statusFilter?: string) {
  return useZeroQuery({
    collection: 'couriers',
    filter: statusFilter
      ? (courier: any) => courier.courier_status === statusFilter
      : undefined,
  })
}

/**
 * Hook for inventory collection
 */
export function useInventoryZero(storeId?: string) {
  return useZeroQuery({
    collection: 'inventory',
    filter: storeId
      ? (item: any) => item.store_id === storeId
      : undefined,
  })
}

/**
 * Hook for triples collection with optional subject filter
 */
export function useTriplesZero(subjectId?: string) {
  return useZeroQuery({
    collection: 'triples',
    filter: subjectId
      ? (triple: any) => triple.subject_id === subjectId
      : undefined,
  })
}
