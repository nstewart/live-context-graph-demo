import { describe, it, expect, vi } from 'vitest'

// Capture the config passed to axios.create when the client module is imported.
vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
    })),
  },
}))

import axios from 'axios'
import { API_TIMEOUT_MS } from './client'

describe('apiClient configuration', () => {
  it('configures a request timeout so stalled requests reject instead of hanging', () => {
    expect(API_TIMEOUT_MS).toBeGreaterThan(0)
    expect(vi.mocked(axios.create)).toHaveBeenCalledWith(
      expect.objectContaining({ timeout: API_TIMEOUT_MS }),
    )
  })
})
