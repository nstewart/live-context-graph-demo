import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import VectorSearchPage from './VectorSearchPage'
import { searchApi } from '../api/client'

// VectorPipelineCard pulls in heavy search/chart deps; stub it out.
vi.mock('../components/VectorPipelineCard', () => ({
  VectorPipelineCard: () => <div data-testid="vector-pipeline-card" />,
}))

vi.mock('../api/client', () => ({
  searchApi: {
    forceMergeSearchIndex: vi.fn(() => Promise.resolve({ data: { triggered: true } })),
  },
}))

const forceMerge = vi.mocked(searchApi.forceMergeSearchIndex)

describe('VectorSearchPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('triggers a force-merge when the page loads', async () => {
    render(<VectorSearchPage />)
    await waitFor(() => {
      expect(forceMerge).toHaveBeenCalledTimes(1)
    })
  })

  it('still renders if the force-merge request rejects', async () => {
    forceMerge.mockRejectedValueOnce(new Error('network'))
    const { getByTestId } = render(<VectorSearchPage />)
    // The page must not crash on a failed/slow merge — it is fire-and-forget.
    expect(getByTestId('vector-pipeline-card')).toBeInTheDocument()
    await waitFor(() => expect(forceMerge).toHaveBeenCalled())
  })
})
