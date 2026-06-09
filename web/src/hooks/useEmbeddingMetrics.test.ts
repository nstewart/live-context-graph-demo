import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'

vi.mock('../api/client', () => ({ searchApi: { embeddingMetrics: vi.fn() } }))

import { searchApi } from '../api/client'
import { useEmbeddingMetrics } from './useEmbeddingMetrics'

const metrics = (over = {}) => ({
  computed: 10, skipped: 90, possible: 100, skip_ratio: 0.9, available: true, ...over,
})

describe('useEmbeddingMetrics', () => {
  beforeEach(() => vi.clearAllMocks())

  it('returns null until the first response, then the metrics', async () => {
    vi.mocked(searchApi.embeddingMetrics).mockResolvedValue({ data: metrics() } as never)
    const { result } = renderHook(() => useEmbeddingMetrics(true))
    expect(result.current).toBeNull()
    await waitFor(() => expect(result.current?.skipped).toBe(90))
  })

  it('does not poll when disabled', async () => {
    vi.mocked(searchApi.embeddingMetrics).mockResolvedValue({ data: metrics() } as never)
    const { result } = renderHook(() => useEmbeddingMetrics(false))
    await new Promise((r) => setTimeout(r, 30))
    expect(searchApi.embeddingMetrics).not.toHaveBeenCalled()
    expect(result.current).toBeNull()
  })

  it('keeps the last good value when a later poll fails', async () => {
    vi.mocked(searchApi.embeddingMetrics)
      .mockResolvedValueOnce({ data: metrics({ skipped: 5 }) } as never)
      .mockRejectedValue(new Error('connect down'))
    const { result } = renderHook(() => useEmbeddingMetrics(true))
    await waitFor(() => expect(result.current?.skipped).toBe(5))
    await new Promise((r) => setTimeout(r, 30))
    expect(result.current?.skipped).toBe(5) // not cleared by the failure
  })
})
