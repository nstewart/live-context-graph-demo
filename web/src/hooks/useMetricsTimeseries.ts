import { useState, useEffect, useCallback, useRef } from 'react'
import { metricsApi, StoreTimeseriesPoint, SystemTimeseriesPoint } from '../api/client'

export interface StoreTimeseries {
  [storeId: string]: StoreTimeseriesPoint[]
}

export interface UseMetricsTimeseriesResult {
  storeTimeseries: StoreTimeseries
  systemTimeseries: SystemTimeseriesPoint[]
  isLoading: boolean
  error: string | null
  lastFetchTime: number | null
  refetch: () => Promise<void>
}

/**
 * Hook that polls the metrics timeseries API for sparkline data.
 *
 * This hook fetches time-bucketed metrics directly from Materialize via the API
 * because the timeseries views cannot be synced through Zero (Zero requires
 * UNIQUE indexes which Materialize doesn't support).
 *
 * The hook automatically polls at the specified interval and groups
 * store data by store_id for easy consumption in sparkline components.
 *
 * @param pollIntervalMs - Polling interval in milliseconds (default: 5000)
 * @param limit - Number of time windows to fetch (default: 10)
 */
export function useMetricsTimeseries(
  pollIntervalMs: number = 5000,
  limit: number = 10
): UseMetricsTimeseriesResult {
  const [storeTimeseries, setStoreTimeseries] = useState<StoreTimeseries>({})
  const [systemTimeseries, setSystemTimeseries] = useState<SystemTimeseriesPoint[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastFetchTime, setLastFetchTime] = useState<number | null>(null)
  const isMountedRef = useRef(true)

  const fetchTimeseries = useCallback(async () => {
    try {
      const response = await metricsApi.getTimeseries({ limit })

      if (!isMountedRef.current) return

      // Group store timeseries by store_id
      const grouped: StoreTimeseries = {}
      for (const point of response.data.store_timeseries) {
        if (!grouped[point.store_id]) {
          grouped[point.store_id] = []
        }
        grouped[point.store_id].push(point)
      }

      // Sort each store's data by window_end ascending (oldest first for sparklines)
      for (const storeId of Object.keys(grouped)) {
        grouped[storeId].sort((a, b) => a.window_end - b.window_end)
      }

      // Sort system timeseries by window_end ascending
      const sortedSystem = [...response.data.system_timeseries].sort(
        (a, b) => a.window_end - b.window_end
      )

      setStoreTimeseries(grouped)
      setSystemTimeseries(sortedSystem)
      setError(null)
      setLastFetchTime(Date.now())
    } catch (err) {
      if (!isMountedRef.current) return
      const message = err instanceof Error ? err.message : 'Failed to fetch timeseries data'
      setError(message)
      console.error('Failed to fetch metrics timeseries:', err)
    } finally {
      if (isMountedRef.current) {
        setIsLoading(false)
      }
    }
  }, [limit])

  useEffect(() => {
    isMountedRef.current = true

    // Initial fetch
    fetchTimeseries()

    // Set up polling interval
    const intervalId = setInterval(fetchTimeseries, pollIntervalMs)

    return () => {
      isMountedRef.current = false
      clearInterval(intervalId)
    }
  }, [fetchTimeseries, pollIntervalMs])

  return {
    storeTimeseries,
    systemTimeseries,
    isLoading,
    error,
    lastFetchTime,
    refetch: fetchTimeseries,
  }
}
