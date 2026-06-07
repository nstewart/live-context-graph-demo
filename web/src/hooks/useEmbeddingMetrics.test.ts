import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { useEmbeddingMetrics } from './useEmbeddingMetrics'

vi.mock('../api/client', () => ({
  searchApi: { embeddingMetrics: vi.fn() },
}))

import { searchApi } from '../api/client'

describe('useEmbeddingMetrics', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('returns metrics from the API on the first poll', async () => {
    ;(searchApi.embeddingMetrics as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { computed: 10, skipped: 90, possible: 100, skip_ratio: 0.9, available: true },
    })

    const { result } = renderHook(() => useEmbeddingMetrics(true))

    await waitFor(() => expect(result.current?.available).toBe(true))
    expect(result.current?.skipped).toBe(90)
  })

  it('does not poll when disabled', () => {
    renderHook(() => useEmbeddingMetrics(false))
    expect(searchApi.embeddingMetrics).not.toHaveBeenCalled()
  })
})
