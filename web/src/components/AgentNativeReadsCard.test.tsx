import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { AgentNativeReadsCard } from './AgentNativeReadsCard'
import { keywordQueries, placeholder } from '../label'

// Mock the API client
vi.mock('../api/client', () => ({
  searchApi: {
    searchOrders: vi.fn(),
  },
}))

// Mock HighlightedJson component
vi.mock('./HighlightedJson', () => ({
  HighlightedJson: ({ data }: { data: object }) => (
    <div data-testid="highlighted-json">{JSON.stringify(data)}</div>
  ),
}))

import { searchApi } from '../api/client'

const mockSearchResponse = {
  took: 5,
  timed_out: false,
  _shards: { total: 1, successful: 1, skipped: 0, failed: 0 },
  hits: {
    total: { value: 2, relation: 'eq' },
    max_score: 1.5,
    hits: [
      {
        _index: 'orders',
        _id: 'order:FM-1001',
        _score: 1.5,
        _source: {
          order_id: 'order:FM-1001',
          customer_name: 'John Doe',
          order_status: 'PLACED',
          store_name: 'Downtown Store',
        },
      },
      {
        _index: 'orders',
        _id: 'order:FM-1002',
        _score: 1.2,
        _source: {
          order_id: 'order:FM-1002',
          customer_name: 'Jane Smith',
          order_status: 'PICKING',
          store_name: 'Brooklyn Store',
        },
      },
    ],
  },
}

describe('AgentNativeReadsCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Initial Render', () => {
    it('renders collapsed by default', () => {
      render(<AgentNativeReadsCard />)
      expect(screen.getByText('Agent-native Reads')).toBeInTheDocument()
      expect(screen.queryByPlaceholderText('Search orders...')).not.toBeInTheDocument()
    })

    it('expands when clicked', async () => {
      render(<AgentNativeReadsCard />)
      const button = screen.getByRole('button')
      fireEvent.click(button)

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Search orders...')).toBeInTheDocument()
      })
    })

    it('shows explanatory text when expanded', async () => {
      render(<AgentNativeReadsCard />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(
          screen.getByText(/Traditional databases require agents to know exact IDs/i)
        ).toBeInTheDocument()
      })
    })
  })

  describe('Search Functionality', () => {
    it('performs search when search button is clicked', async () => {
      vi.mocked(searchApi.searchOrders).mockResolvedValue({ data: mockSearchResponse } as never)

      render(<AgentNativeReadsCard />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Search orders...')).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText('Search orders...')
      const searchButton = screen.getByRole('button', { name: /search/i })

      fireEvent.change(input, { target: { value: 'john' } })
      fireEvent.click(searchButton)

      await waitFor(() => {
        expect(searchApi.searchOrders).toHaveBeenCalledWith('john', 3)
      })
    })

    it('performs search when Enter key is pressed', async () => {
      vi.mocked(searchApi.searchOrders).mockResolvedValue({ data: mockSearchResponse } as never)

      render(<AgentNativeReadsCard />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Search orders...')).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText('Search orders...')
      fireEvent.change(input, { target: { value: 'downtown' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      await waitFor(() => {
        expect(searchApi.searchOrders).toHaveBeenCalledWith('downtown', 3)
      })
    })

    it('disables search button when query is empty', async () => {
      render(<AgentNativeReadsCard />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() => {
        const searchButton = screen.getByRole('button', { name: /search/i })
        expect(searchButton).toBeDisabled()
      })
    })

    it('enables search button when query is provided', async () => {
      render(<AgentNativeReadsCard />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Search orders...')).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText('Search orders...')
      const searchButton = screen.getByRole('button', { name: /search/i })

      fireEvent.change(input, { target: { value: 'test' } })

      expect(searchButton).not.toBeDisabled()
    })

    it('displays search results', async () => {
      vi.mocked(searchApi.searchOrders).mockResolvedValue({ data: mockSearchResponse } as never)

      render(<AgentNativeReadsCard />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Search orders...')).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText('Search orders...')
      fireEvent.change(input, { target: { value: 'john' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      await waitFor(() => {
        expect(screen.getByText('2 hits')).toBeInTheDocument()
      })
    })

    it('clears results when search query is cleared', async () => {
      vi.mocked(searchApi.searchOrders).mockResolvedValue({ data: mockSearchResponse } as never)

      render(<AgentNativeReadsCard />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Search orders...')).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText('Search orders...')
      fireEvent.change(input, { target: { value: 'john' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      await waitFor(() => {
        expect(screen.getByText('2 hits')).toBeInTheDocument()
      })

      // Clear the input
      fireEvent.change(input, { target: { value: '' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      await waitFor(() => {
        expect(screen.queryByText('2 hits')).not.toBeInTheDocument()
      })
    })
  })

  describe('Example Queries', () => {
    it('displays example query buttons', async () => {
      render(<AgentNativeReadsCard />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() => {
        for (const q of keywordQueries) {
          expect(screen.getByText(q)).toBeInTheDocument()
        }
      })
    })

    it('performs search when example query is clicked', async () => {
      vi.mocked(searchApi.searchOrders).mockResolvedValue({ data: mockSearchResponse } as never)

      render(<AgentNativeReadsCard />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByPlaceholderText(placeholder('order_search'))).toBeInTheDocument()
      })

      const [first] = keywordQueries
      fireEvent.click(screen.getByRole('button', { name: first }))

      await waitFor(() => {
        expect(searchApi.searchOrders).toHaveBeenCalledWith(first, 3)
      })
    })

    it('updates search input when example is clicked', async () => {
      vi.mocked(searchApi.searchOrders).mockResolvedValue({ data: mockSearchResponse } as never)

      render(<AgentNativeReadsCard />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByPlaceholderText(placeholder('order_search'))).toBeInTheDocument()
      })

      const [, second] = keywordQueries
      fireEvent.click(screen.getByRole('button', { name: second }))

      const input = screen.getByPlaceholderText(
        placeholder('order_search'),
      ) as HTMLInputElement
      expect(input.value).toBe(second)
    })
  })

  describe('Error Handling', () => {
    it('displays error message when search fails', async () => {
      vi.mocked(searchApi.searchOrders).mockRejectedValue(new Error('Network error'))

      render(<AgentNativeReadsCard />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Search orders...')).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText('Search orders...')
      fireEvent.change(input, { target: { value: 'test' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      await waitFor(() => {
        expect(
          screen.getByText(/Search unavailable. Ensure OpenSearch is running./i)
        ).toBeInTheDocument()
      })
    })

    it('shows loading state during search', async () => {
      vi.mocked(searchApi.searchOrders).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve({ data: mockSearchResponse } as never), 100))
      )

      render(<AgentNativeReadsCard />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Search orders...')).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText('Search orders...')
      fireEvent.change(input, { target: { value: 'test' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      expect(screen.getByText('Searching...')).toBeInTheDocument()

      await waitFor(() => {
        expect(screen.queryByText('Searching...')).not.toBeInTheDocument()
      })
    })

    it('disables search button during search', async () => {
      vi.mocked(searchApi.searchOrders).mockImplementation(
        () => new Promise((resolve) => setTimeout(() => resolve({ data: mockSearchResponse } as never), 100))
      )

      render(<AgentNativeReadsCard />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Search orders...')).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText('Search orders...')
      const searchButton = screen.getByRole('button', { name: /search/i })

      fireEvent.change(input, { target: { value: 'test' } })
      fireEvent.click(searchButton)

      expect(searchButton).toBeDisabled()

      await waitFor(() => {
        expect(searchButton).not.toBeDisabled()
      })
    })
  })

  describe('Hit Count Display', () => {
    it('displays singular "hit" for one result', async () => {
      const singleHitResponse = {
        ...mockSearchResponse,
        hits: {
          ...mockSearchResponse.hits,
          total: { value: 1, relation: 'eq' },
          hits: [mockSearchResponse.hits.hits[0]],
        },
      }

      vi.mocked(searchApi.searchOrders).mockResolvedValue({ data: singleHitResponse } as never)

      render(<AgentNativeReadsCard />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Search orders...')).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText('Search orders...')
      fireEvent.change(input, { target: { value: 'test' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      await waitFor(() => {
        expect(screen.getByText('1 hit')).toBeInTheDocument()
      })
    })

    it('displays plural "hits" for multiple results', async () => {
      vi.mocked(searchApi.searchOrders).mockResolvedValue({ data: mockSearchResponse } as never)

      render(<AgentNativeReadsCard />)
      fireEvent.click(screen.getByRole('button'))

      await waitFor(() => {
        expect(screen.getByPlaceholderText('Search orders...')).toBeInTheDocument()
      })

      const input = screen.getByPlaceholderText('Search orders...')
      fireEvent.change(input, { target: { value: 'test' } })
      fireEvent.keyDown(input, { key: 'Enter' })

      await waitFor(() => {
        expect(screen.getByText('2 hits')).toBeInTheDocument()
      })
    })
  })
})
