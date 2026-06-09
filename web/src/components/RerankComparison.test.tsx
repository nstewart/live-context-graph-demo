import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'

vi.mock('../api/client', () => ({ searchApi: { rerankedVectorSearch: vi.fn() } }))

import { searchApi } from '../api/client'
import { RerankComparison } from './RerankComparison'

const response = {
  data: {
    query: 'veggies',
    model: 'Xenova/ms-marco-MiniLM-L-6-v2',
    limit: 8,
    timings: { embed_ms: 30, recall_ms: 12, feature_fetch_ms: 4, rerank_ms: 88 },
    results: [
      // already in reranked (new_rank) order
      { order_id: 'order:FM-000221', order_number: 'FM-000221', status: 'CREATED',
        knn_score: 0.663, original_rank: 5,
        doc: 'Order FM-000221, status CREATED. Items: Carrots Organic Bunch (Produce, $1.80, in stock)',
        matched_text: 'Carrots Organic Bunch (Produce)',
        rerank_score: 3.83, new_rank: 1, delta: 4 },
      { order_id: 'order:FM-000472', order_number: 'FM-000472', status: 'PICKING',
        knn_score: 0.670, original_rank: 1,
        doc: 'Order FM-000472, status PICKING. Items: Veggie Straws 7oz (Snacks, $4.29, in stock)',
        matched_text: 'Veggie Straws 7oz (Snacks)',
        rerank_score: 0.11, new_rank: 5, delta: -4 },
    ],
  },
}

describe('RerankComparison', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders nothing without a query', () => {
    const { container } = render(<RerankComparison query="" />)
    expect(container).toBeEmptyDOMElement()
    expect(searchApi.rerankedVectorSearch).not.toHaveBeenCalled()
  })

  it('shows candidates in reranked order with rank deltas, timings, and the doc', async () => {
    vi.mocked(searchApi.rerankedVectorSearch).mockResolvedValue(response as any)
    render(<RerankComparison query="veggies" />)

    await waitFor(() => expect(screen.getByText('#FM-000221')).toBeInTheDocument())

    // both candidates rendered, with their reranked positions and deltas
    expect(screen.getByText('#FM-000472')).toBeInTheDocument()
    expect(screen.getByText('▲4')).toBeInTheDocument()   // FM-000221 moved up 4
    expect(screen.getByText('▼4')).toBeInTheDocument()   // FM-000472 moved down 4

    // provenance split: [MZ] = the doc the model scored (live), [index] = what kNN matched
    expect(screen.getByText(/Order FM-000221, status CREATED\. Items: Carrots Organic Bunch \(Produce, \$1.80, in stock\)/)).toBeInTheDocument()
    expect(screen.getByText(/matched: Carrots Organic Bunch \(Produce\)/)).toBeInTheDocument()
    expect(screen.getAllByText('MZ')).toHaveLength(2)      // one per candidate
    expect(screen.getAllByText('index')).toHaveLength(2)

    // stacked latency bar: total + the four stage labels in the legend
    expect(screen.getByText('response latency')).toBeInTheDocument()
    expect(screen.getByText('134 ms')).toBeInTheDocument() // 30 + 12 + 4 + 88
    expect(screen.getByText('embed query')).toBeInTheDocument()
    expect(screen.getByText('kNN recall')).toBeInTheDocument()
    expect(screen.getByText('features from MZ')).toBeInTheDocument()
    expect(screen.getByText('cross-encoder')).toBeInTheDocument()
    expect(searchApi.rerankedVectorSearch).toHaveBeenCalledWith('veggies')
  })

  it('shows an error state when the rerank call fails', async () => {
    vi.mocked(searchApi.rerankedVectorSearch).mockRejectedValue(new Error('down'))
    render(<RerankComparison query="veggies" />)
    await waitFor(() => expect(screen.getByText(/Rerank unavailable/i)).toBeInTheDocument())
  })
})
