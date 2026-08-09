import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

vi.mock('../api/client', () => ({
  queryStatsApi: { getViewDefinitions: vi.fn() },
}))

import { queryStatsApi } from '../api/client'
import { useViewDefinitions } from './useViewDefinitions'

const def = (name: string) => ({
  view_name: name,
  object_type: 'view',
  sql: `CREATE VIEW ${name} AS SELECT 1`,
})

const payload = (names: string[], expected = names.length) => ({
  data: {
    definitions: Object.fromEntries(names.map((n) => [n, def(n)])),
    cached_count: names.length,
    expected_count: expected,
  },
})

describe('useViewDefinitions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('prefetches once on mount and serves definitions from memory', async () => {
    vi.mocked(queryStatsApi.getViewDefinitions).mockResolvedValue(
      payload(['stores_flat', 'orders_flat_mv']) as never
    )
    const { result } = renderHook(() => useViewDefinitions())

    await waitFor(() => expect(result.current.get('stores_flat')).not.toBeNull())
    expect(result.current.get('stores_flat')?.sql).toContain('CREATE VIEW stores_flat')
    expect(queryStatsApi.getViewDefinitions).toHaveBeenCalledTimes(1)
  })

  it('returns null for a view that was not prefetched so the caller can fetch it', async () => {
    vi.mocked(queryStatsApi.getViewDefinitions).mockResolvedValue(
      payload(['stores_flat'], 2) as never
    )
    const { result } = renderHook(() => useViewDefinitions())

    await waitFor(() => expect(result.current.get('stores_flat')).not.toBeNull())
    expect(result.current.get('never_prefetched')).toBeNull()
  })

  it('caches a definition handed back from the fallback fetch', async () => {
    vi.mocked(queryStatsApi.getViewDefinitions).mockResolvedValue(payload([]) as never)
    const { result } = renderHook(() => useViewDefinitions())

    await waitFor(() => expect(queryStatsApi.getViewDefinitions).toHaveBeenCalled())
    expect(result.current.get('late_view')).toBeNull()

    result.current.set('late_view', def('late_view'))
    expect(result.current.get('late_view')?.sql).toContain('late_view')
  })

  it('retries a failed prefetch, then serves the definitions', async () => {
    vi.useFakeTimers()
    vi.mocked(queryStatsApi.getViewDefinitions)
      .mockRejectedValueOnce(new Error('api not up yet'))
      .mockResolvedValue(payload(['stores_flat']) as never)

    const { result } = renderHook(() => useViewDefinitions())

    await vi.waitFor(() => expect(queryStatsApi.getViewDefinitions).toHaveBeenCalledTimes(1))
    await vi.advanceTimersByTimeAsync(5000)
    await vi.waitFor(() => expect(result.current.get('stores_flat')).not.toBeNull())
  })

  it('gives up after the retry budget without throwing', async () => {
    vi.useFakeTimers()
    vi.mocked(queryStatsApi.getViewDefinitions).mockRejectedValue(new Error('backend down'))
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const { result } = renderHook(() => useViewDefinitions())

    await vi.advanceTimersByTimeAsync(30_000)
    // 3 attempts total, then it stops retrying — clicks still work via fallback
    expect(queryStatsApi.getViewDefinitions).toHaveBeenCalledTimes(3)
    expect(result.current.get('stores_flat')).toBeNull()
    warn.mockRestore()
  })

  it('does not fire a stray retry after unmount', async () => {
    vi.useFakeTimers()
    vi.mocked(queryStatsApi.getViewDefinitions).mockRejectedValue(new Error('backend down'))
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const { unmount } = renderHook(() => useViewDefinitions())
    await vi.waitFor(() => expect(queryStatsApi.getViewDefinitions).toHaveBeenCalledTimes(1))
    unmount()

    await vi.advanceTimersByTimeAsync(30_000)
    expect(queryStatsApi.getViewDefinitions).toHaveBeenCalledTimes(1)
    warn.mockRestore()
  })
})
