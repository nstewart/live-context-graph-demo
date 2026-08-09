import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, waitFor } from '@testing-library/react'
import VectorSearchPage from './VectorSearchPage'
import { searchApi, queryStatsApi } from '../api/client'

// VectorPipelineCard pulls in heavy search/chart deps; stub it out.
vi.mock('../components/VectorPipelineCard', () => ({
  VectorPipelineCard: () => <div data-testid="vector-pipeline-card" />,
}))

// ReferenceArchitectureCard pulls in reactflow + dagre; stub it out.
vi.mock('../components/ReferenceArchitectureCard', () => ({
  ReferenceArchitectureCard: () => <div data-testid="reference-architecture-card" />,
}))

vi.mock('../components/WhatAreTriplesCard', () => ({
  WhatAreTriplesCard: ({ selectedOrderId }: { selectedOrderId: string }) => (
    <div data-testid="triples-card" data-order={selectedOrderId} />
  ),
}))

vi.mock('@rocicorp/zero/react', () => ({
  useZero: () => ({
    query: { orders_with_lines_mv: { where: () => ({ __query: true }) } },
  }),
  useQuery: () => [[]],
}))

vi.mock('../api/client', () => ({
  searchApi: {
    forceMergeSearchIndex: vi.fn(() => Promise.resolve({ data: { triggered: true } })),
  },
  queryStatsApi: {
    getOrders: vi.fn(() => Promise.resolve({ data: [] })),
  },
}))

const forceMerge = vi.mocked(searchApi.forceMergeSearchIndex)
const getOrders = vi.mocked(queryStatsApi.getOrders)

describe('VectorSearchPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getOrders.mockResolvedValue({ data: [] } as never)
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

  it('shows the writes card, then the architecture, above the pipeline', () => {
    const { getByTestId, container } = render(<VectorSearchPage />)
    expect(getByTestId('triples-card')).toBeInTheDocument()
    expect(getByTestId('reference-architecture-card')).toBeInTheDocument()

    // Writes come before the architecture diagram, both before the pipeline
    const order = Array.from(container.querySelectorAll('[data-testid]')).map((el) =>
      el.getAttribute('data-testid')
    )
    expect(order).toEqual([
      'triples-card',
      'reference-architecture-card',
      'vector-pipeline-card',
    ])
  })

  it('selects the first order for the triples card', async () => {
    getOrders.mockResolvedValue({
      data: [
        { order_id: 'order:1', order_number: 'ORD-001' },
        { order_id: 'order:2', order_number: 'ORD-002' },
      ],
    } as never)
    const { getByTestId } = render(<VectorSearchPage />)
    await waitFor(() =>
      expect(getByTestId('triples-card')).toHaveAttribute('data-order', 'order:1')
    )
  })

  it('still renders the page when the order lookup fails', async () => {
    getOrders.mockRejectedValue(new Error('api down'))
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { getByTestId } = render(<VectorSearchPage />)
    await waitFor(() => expect(getOrders).toHaveBeenCalled())
    expect(getByTestId('vector-pipeline-card')).toBeInTheDocument()
    error.mockRestore()
  })
})
