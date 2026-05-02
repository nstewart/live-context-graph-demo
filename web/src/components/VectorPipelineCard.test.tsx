import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { VectorPipelineCard } from './VectorPipelineCard'

// Mock the API client
vi.mock('../api/client', () => ({
  searchApi: {
    vectorSearchOrders: vi.fn(),
  },
}))

import { searchApi } from '../api/client'

const mockResponse = {
  data: {
    results: [
      {
        order_id: 'order:FM-1001',
        score: 0.92,
        embedding_text: 'Whole Milk (Dairy) | Bananas (Produce)',
        embedded_at: '2024-01-15T14:30:00Z',
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

    it('shows architecture steps when expanded', async () => {
      render(<VectorPipelineCard />)
      fireEvent.click(screen.getByRole('button', { name: /Vector Pipeline/i }))

      await waitFor(() => {
        expect(screen.getByText('Embed query')).toBeInTheDocument()
        expect(screen.getByText('knn_search')).toBeInTheDocument()
        expect(screen.getByText('Hydrate')).toBeInTheDocument()
        expect(screen.getByText(/Merge/i)).toBeInTheDocument()
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
        expect(searchApi.vectorSearchOrders).toHaveBeenCalledWith('dairy products', 3)
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
        expect(searchApi.vectorSearchOrders).toHaveBeenCalledWith('organic produce', 3)
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
        expect(screen.getByText(/FM-1001/)).toBeInTheDocument()
        expect(screen.getByText('Alex Thompson')).toBeInTheDocument()
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
})
