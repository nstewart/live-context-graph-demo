import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { VectorPipelineCard } from './VectorPipelineCard'

// Mock the API client
vi.mock('../api/client', () => ({
  searchApi: {
    vectorSearchOrders: vi.fn(),
    // The embedding-metrics ticker polls this; return an unavailable payload so
    // the ticker stays hidden and existing assertions are unaffected.
    embeddingMetrics: vi.fn().mockResolvedValue({
      data: { computed: 0, skipped: 0, possible: 0, skip_ratio: 0, available: false },
    }),
  },
}))

// SearchIndexUpdates (rendered inside the expanded card) calls usePropagation,
// which requires a PropagationProvider. Stub the context so the card renders in
// isolation without the provider's :8083 polling.
vi.mock('../contexts/PropagationContext', () => ({
  usePropagation: () => ({ events: [] }),
  PropagationProvider: (props: any) => props.children,
}))

import { searchApi } from '../api/client'

// A 16-element stand-in for the 384-dim vector; embeddingFingerprint only needs
// the first 12 values, and re-embed detection keys off this fingerprint.
const EMBEDDING_A = Array.from({ length: 16 }, (_, i) => (i % 7) / 10 - 0.3)
const EMBEDDING_B = EMBEDDING_A.map((x) => -x) // different fingerprint => re-embed

const mockResponse = {
  data: {
    results: [
      {
        order_id: 'order:FM-1001',
        score: 0.92,
        embedding: EMBEDDING_A,
        embedding_text: 'Whole Milk (Dairy) | Bananas (Produce)',
        embedded_at: null,
        order_number: 'FM-1001',
        order_status: 'OUT_FOR_DELIVERY',
        customer_name: 'Alex Thompson',
        store_name: 'FreshMart Brooklyn',
        store_zone: 'Brooklyn',
        order_total_amount: 45.99,
        effective_updated_at: '2024-01-15T14:35:00Z',
      },
    ],
    query: 'dairy',
    total: 1,
  },
}

const emptyResponse = {
  data: {
    results: [],
    query: 'nothing',
    total: 0,
  },
}

describe('VectorPipelineCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Initial Render', () => {
    it('renders collapsed by default', () => {
      render(<VectorPipelineCard />)
      expect(screen.getByText('Vector Pipeline')).toBeInTheDocument()
      expect(screen.queryByPlaceholderText(/search/i)).not.toBeInTheDocument()
    })

    it('expands when header clicked', async () => {
      render(<VectorPipelineCard />)
      const headerButton = screen.getByRole('button', { name: /Vector Pipeline/i })
      fireEvent.click(headerButton)

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument()
      })
    })

    it('shows the search UI sections when expanded', async () => {
      render(<VectorPipelineCard />)
      fireEvent.click(screen.getByRole('button', { name: /Vector Pipeline/i }))

      await waitFor(() => {
        expect(screen.getByText('Hybrid Search')).toBeInTheDocument()
        expect(screen.getByText('Live order results')).toBeInTheDocument()
        expect(screen.getByRole('button', { name: 'dairy products' })).toBeInTheDocument()
      })
    })
  })

  describe('Search Functionality', () => {
    it('performs search on button click', async () => {
      vi.mocked(searchApi.vectorSearchOrders).mockResolvedValue(mockResponse as never)

      render(<VectorPipelineCard />)
      fireEvent.click(screen.getByRole('button', { name: /Vector Pipeline/i }))

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText(/search/i)
      const searchButton = screen.getByRole('button', { name: /^Search$/i })

      fireEvent.change(input, { target: { value: 'dairy products' } })
      fireEvent.click(searchButton)

      await waitFor(() => {
        expect(searchApi.vectorSearchOrders).toHaveBeenCalledWith('dairy products', 5, expect.any(Object))
      })
    })

    it('performs search on Enter key', async () => {
      vi.mocked(searchApi.vectorSearchOrders).mockResolvedValue(mockResponse as never)

      render(<VectorPipelineCard />)
      fireEvent.click(screen.getByRole('button', { name: /Vector Pipeline/i }))

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText(/search/i)
      fireEvent.change(input, { target: { value: 'organic produce' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      await waitFor(() => {
        expect(searchApi.vectorSearchOrders).toHaveBeenCalledWith('organic produce', 5, expect.any(Object))
      })
    })

    it('shows order card after search', async () => {
      vi.mocked(searchApi.vectorSearchOrders).mockResolvedValue(mockResponse as never)

      render(<VectorPipelineCard />)
      fireEvent.click(screen.getByRole('button', { name: /Vector Pipeline/i }))

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText(/search/i)
      fireEvent.change(input, { target: { value: 'dairy' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      await waitFor(() => {
        expect(screen.getByText('#FM-1001')).toBeInTheDocument()
        // customer_name is joined with store info in one node ("Alex … · FreshMart …")
        expect(screen.getByText(/Alex Thompson/)).toBeInTheDocument()
      })
    })

    it('shows similarity score', async () => {
      vi.mocked(searchApi.vectorSearchOrders).mockResolvedValue(mockResponse as never)

      render(<VectorPipelineCard />)
      fireEvent.click(screen.getByRole('button', { name: /Vector Pipeline/i }))

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText(/search/i)
      fireEvent.change(input, { target: { value: 'dairy' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      await waitFor(() => {
        expect(screen.getByText(/92\.0%/)).toBeInTheDocument()
      })
    })

    it('shows embedding text', async () => {
      vi.mocked(searchApi.vectorSearchOrders).mockResolvedValue(mockResponse as never)

      render(<VectorPipelineCard />)
      fireEvent.click(screen.getByRole('button', { name: /Vector Pipeline/i }))

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText(/search/i)
      fireEvent.change(input, { target: { value: 'dairy' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      await waitFor(() => {
        expect(
          screen.getByText('Whole Milk (Dairy) | Bananas (Produce)')
        ).toBeInTheDocument()
      })
    })

    it('shows loading state', async () => {
      vi.mocked(searchApi.vectorSearchOrders).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve(mockResponse as never), 100))
      )

      render(<VectorPipelineCard />)
      fireEvent.click(screen.getByRole('button', { name: /Vector Pipeline/i }))

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText(/search/i)
      fireEvent.change(input, { target: { value: 'dairy' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      expect(screen.getByText(/Searching\.\.\./i)).toBeInTheDocument()

      await waitFor(() => {
        expect(screen.queryByText(/Searching\.\.\./i)).not.toBeInTheDocument()
      })
    })

    it('shows error on failure', async () => {
      vi.mocked(searchApi.vectorSearchOrders).mockRejectedValue(new Error('Network error'))

      render(<VectorPipelineCard />)
      fireEvent.click(screen.getByRole('button', { name: /Vector Pipeline/i }))

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText(/search/i)
      fireEvent.change(input, { target: { value: 'dairy' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      await waitFor(() => {
        expect(screen.getByText(/unavailable|error|failed/i)).toBeInTheDocument()
      })
    })

    it('handles empty results gracefully', async () => {
      vi.mocked(searchApi.vectorSearchOrders).mockResolvedValue(emptyResponse as never)

      render(<VectorPipelineCard />)
      fireEvent.click(screen.getByRole('button', { name: /Vector Pipeline/i }))

      await waitFor(() => {
        expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText(/search/i)
      fireEvent.change(input, { target: { value: 'nothing' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      await waitFor(() => {
        expect(screen.getByText(/no results/i)).toBeInTheDocument()
      })
    })
  })

  describe('Re-embed detection', () => {
    // Replaces the old embedded_at-driven flash: the Kafka/SMT path stamps no
    // per-embed timestamp, so the card flashes when the embedding vector changes.
    it('flashes when the embedding vector changes, not on a stable vector', async () => {
      const respA = { data: { ...mockResponse.data, results: [{ ...mockResponse.data.results[0], embedding: EMBEDDING_A }] } }
      const respB = { data: { ...mockResponse.data, results: [{ ...mockResponse.data.results[0], embedding: EMBEDDING_B }] } }
      vi.mocked(searchApi.vectorSearchOrders)
        .mockResolvedValueOnce(respA as never)   // first search: baseline, no flash
        .mockResolvedValue(respB as never)        // subsequent: vector changed

      render(<VectorPipelineCard />)
      fireEvent.click(screen.getByRole('button', { name: /Vector Pipeline/i }))
      await waitFor(() => expect(screen.getByPlaceholderText(/search/i)).toBeInTheDocument())

      const input = screen.getByPlaceholderText(/search/i)
      const searchButton = screen.getByRole('button', { name: /^Search$/i })

      fireEvent.change(input, { target: { value: 'dairy' } })
      fireEvent.click(searchButton)
      await waitFor(() => expect(screen.getByText('#FM-1001')).toBeInTheDocument())
      // Baseline sighting must not flash.
      expect(screen.queryByText(/re-embedded/i)).not.toBeInTheDocument()

      // Re-run the same query; the vector now differs => re-embed flash.
      fireEvent.click(searchButton)
      await waitFor(() => expect(screen.getByText(/re-embedded/i)).toBeInTheDocument())
    })
  })
})
