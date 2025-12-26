import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import QueryStatisticsPage from './QueryStatisticsPage'

// Mock the API client
vi.mock('../api/client', () => ({
  queryStatsApi: {
    getOrders: vi.fn(),
    getMetrics: vi.fn(),
    getMetricsHistory: vi.fn(),
    getOrderData: vi.fn(),
    startPolling: vi.fn(),
    stopPolling: vi.fn(),
    writeTriple: vi.fn(),
  },
}))

// Mock Zero
vi.mock('@rocicorp/zero/react', () => ({
  useZero: vi.fn(() => ({
    query: {
      orders_with_lines_mv: {
        related: vi.fn(() => ({
          where: vi.fn(() => ({})),
        })),
      },
      inventory_items_with_dynamic_pricing: {
        where: vi.fn(() => ({})),
      },
    },
  })),
  useQuery: vi.fn(() => [null]),
}))

// Mock LineageGraph component
vi.mock('../components/LineageGraph', () => ({
  LineageGraph: () => <div>LineageGraph</div>,
}))

import { queryStatsApi } from '../api/client'

const mockOrders = [
  {
    order_id: 'order:FM-1001',
    order_number: 'FM-1001',
    order_status: 'PLACED',
    customer_name: 'Alex Thompson',
    store_name: 'FreshMart Brooklyn Heights',
  },
  {
    order_id: 'order:FM-1002',
    order_number: 'FM-1002',
    order_status: 'DELIVERED',
    customer_name: 'Jordan Lee',
    store_name: 'FreshMart Manhattan',
  },
]

describe('QueryStatisticsPage ViewMode', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(queryStatsApi.getOrders).mockResolvedValue({ data: mockOrders } as never)
    vi.mocked(queryStatsApi.getMetrics).mockResolvedValue({ data: {} } as never)
    vi.mocked(queryStatsApi.getMetricsHistory).mockResolvedValue({ data: {} } as never)
    vi.mocked(queryStatsApi.getOrderData).mockResolvedValue({ data: {} } as never)
  })

  describe('View Mode Selection', () => {
    it('defaults to query-offload mode', async () => {
      render(<QueryStatisticsPage />)

      await waitFor(() => {
        const viewModeSelect = screen.getByRole('combobox', { name: /view mode/i })
        expect(viewModeSelect).toHaveValue('query-offload')
      })
    })

    it('allows switching to batch mode', async () => {
      render(<QueryStatisticsPage />)

      await waitFor(() => {
        expect(screen.getByText('FM-1001')).toBeInTheDocument()
      })

      const viewModeSelect = screen.getByDisplayValue('Query Offload')
      fireEvent.change(viewModeSelect, { target: { value: 'batch' } })

      expect(viewModeSelect).toHaveValue('batch')
    })

    it('allows switching to materialize mode', async () => {
      render(<QueryStatisticsPage />)

      await waitFor(() => {
        expect(screen.getByText('FM-1001')).toBeInTheDocument()
      })

      const viewModeSelect = screen.getByDisplayValue('Query Offload')
      fireEvent.change(viewModeSelect, { target: { value: 'materialize' } })

      expect(viewModeSelect).toHaveValue('materialize')
    })
  })

  describe('Order Cards Display Based on View Mode', () => {
    it('shows only PostgreSQL card in query-offload mode', async () => {
      render(<QueryStatisticsPage />)

      await waitFor(() => {
        expect(screen.getByText('PostgreSQL VIEW')).toBeInTheDocument()
      })

      // Should not show Batch or Materialize cards
      expect(screen.queryByText('Batch MATERIALIZED VIEW')).not.toBeInTheDocument()
      expect(screen.queryByText('Materialize (via Zero)')).not.toBeInTheDocument()
    })

    it('shows PostgreSQL and Batch cards in batch mode', async () => {
      render(<QueryStatisticsPage />)

      await waitFor(() => {
        expect(screen.getByText('FM-1001')).toBeInTheDocument()
      })

      const viewModeSelect = screen.getByDisplayValue('Query Offload')
      fireEvent.change(viewModeSelect, { target: { value: 'batch' } })

      await waitFor(() => {
        expect(screen.getByText('PostgreSQL VIEW')).toBeInTheDocument()
        expect(screen.getByText('Batch MATERIALIZED VIEW')).toBeInTheDocument()
      })

      // Should not show Materialize card
      expect(screen.queryByText('Materialize (via Zero)')).not.toBeInTheDocument()
    })

    it('shows all three cards in materialize mode', async () => {
      render(<QueryStatisticsPage />)

      await waitFor(() => {
        expect(screen.getByText('FM-1001')).toBeInTheDocument()
      })

      const viewModeSelect = screen.getByDisplayValue('Query Offload')
      fireEvent.change(viewModeSelect, { target: { value: 'materialize' } })

      await waitFor(() => {
        expect(screen.getByText('PostgreSQL VIEW')).toBeInTheDocument()
        expect(screen.getByText('Batch MATERIALIZED VIEW')).toBeInTheDocument()
        expect(screen.getByText('Materialize (via Zero)')).toBeInTheDocument()
      })
    })
  })

  describe('Subject Type Detection', () => {
    it('detects orderline subject from orderline_ prefix', async () => {
      render(<QueryStatisticsPage />)

      await waitFor(() => {
        expect(screen.getByText('FM-1001')).toBeInTheDocument()
      })

      const subjectInput = screen.getByPlaceholderText('order:FM-1001')
      fireEvent.change(subjectInput, { target: { value: 'orderline_12345' } })

      // Should show orderline predicates in the select
      const predicateSelect = screen.getByDisplayValue('quantity')
      expect(predicateSelect).toBeInTheDocument()
    })

    it('detects order subject from order_ prefix', async () => {
      render(<QueryStatisticsPage />)

      await waitFor(() => {
        expect(screen.getByText('FM-1001')).toBeInTheDocument()
      })

      const subjectInput = screen.getByPlaceholderText('order:FM-1001')
      fireEvent.change(subjectInput, { target: { value: 'order_FM-1001' } })

      // Predicate should auto-select to first order predicate
      await waitFor(() => {
        const predicateSelect = screen.getByRole('combobox', { name: /predicate/i })
        expect(predicateSelect).toHaveValue('order_status')
      })
    })

    it('detects subject type from colon prefix', async () => {
      render(<QueryStatisticsPage />)

      await waitFor(() => {
        expect(screen.getByText('FM-1001')).toBeInTheDocument()
      })

      const subjectInput = screen.getByPlaceholderText('order:FM-1001')
      fireEvent.change(subjectInput, { target: { value: 'product:123' } })

      // Predicate should auto-select to first product predicate
      await waitFor(() => {
        const predicateSelect = screen.getByRole('combobox', { name: /predicate/i })
        expect(predicateSelect).toHaveValue('product_name')
      })
    })
  })

  describe('Predicate Auto-selection', () => {
    it('auto-selects first available predicate when subject type changes', async () => {
      render(<QueryStatisticsPage />)

      await waitFor(() => {
        expect(screen.getByText('FM-1001')).toBeInTheDocument()
      })

      const subjectInput = screen.getByPlaceholderText('order:FM-1001')

      // Start with orderline (quantity is default)
      fireEvent.change(subjectInput, { target: { value: 'orderline_12345' } })

      await waitFor(() => {
        const predicateSelect = screen.getByRole('combobox', { name: /predicate/i })
        expect(predicateSelect).toHaveValue('quantity')
      })

      // Change to order type
      fireEvent.change(subjectInput, { target: { value: 'order_FM-1001' } })

      await waitFor(() => {
        const predicateSelect = screen.getByRole('combobox', { name: /predicate/i })
        expect(predicateSelect).toHaveValue('order_status')
      })
    })
  })

  describe('User Subject Input', () => {
    it('allows user to manually set subject and preserves it', async () => {
      render(<QueryStatisticsPage />)

      await waitFor(() => {
        expect(screen.getByText('FM-1001')).toBeInTheDocument()
      })

      const subjectInput = screen.getByPlaceholderText('order:FM-1001')
      fireEvent.change(subjectInput, { target: { value: 'orderline_custom_123' } })

      expect(subjectInput).toHaveValue('orderline_custom_123')
    })

    it('resets user flag when order selection changes', async () => {
      render(<QueryStatisticsPage />)

      await waitFor(() => {
        expect(screen.getByText('FM-1001')).toBeInTheDocument()
      })

      const subjectInput = screen.getByPlaceholderText('order:FM-1001')
      fireEvent.change(subjectInput, { target: { value: 'orderline_custom_123' } })

      // Change order selection
      const orderSelect = screen.getByDisplayValue(/FM-1001.*Alex Thompson/)
      fireEvent.change(orderSelect, { target: { value: 'order:FM-1002' } })

      // Subject should be updated to new order
      await waitFor(() => {
        expect(subjectInput).toHaveValue('order:FM-1002')
      })
    })
  })

  describe('Write Triple Functionality', () => {
    it('has write button disabled when fields are empty', async () => {
      render(<QueryStatisticsPage />)

      await waitFor(() => {
        expect(screen.getByText('FM-1001')).toBeInTheDocument()
      })

      const writeButton = screen.getByRole('button', { name: /write/i })
      expect(writeButton).toBeDisabled()
    })

    it('enables write button when all fields are filled', async () => {
      render(<QueryStatisticsPage />)

      await waitFor(() => {
        expect(screen.getByText('FM-1001')).toBeInTheDocument()
      })

      const subjectInput = screen.getByPlaceholderText('order:FM-1001')
      const valueInput = screen.getByPlaceholderText('DELIVERED')

      fireEvent.change(subjectInput, { target: { value: 'order:FM-1001' } })
      fireEvent.change(valueInput, { target: { value: 'DELIVERED' } })

      const writeButton = screen.getByRole('button', { name: /write/i })
      expect(writeButton).not.toBeDisabled()
    })

    it('calls writeTriple API when write button is clicked', async () => {
      vi.mocked(queryStatsApi.writeTriple).mockResolvedValue({ data: {} } as never)

      render(<QueryStatisticsPage />)

      await waitFor(() => {
        expect(screen.getByText('FM-1001')).toBeInTheDocument()
      })

      const subjectInput = screen.getByPlaceholderText('order:FM-1001')
      const valueInput = screen.getByPlaceholderText('DELIVERED')

      fireEvent.change(subjectInput, { target: { value: 'order:FM-1001' } })
      fireEvent.change(valueInput, { target: { value: 'DELIVERED' } })

      const writeButton = screen.getByRole('button', { name: /write/i })
      fireEvent.click(writeButton)

      await waitFor(() => {
        expect(queryStatsApi.writeTriple).toHaveBeenCalledWith({
          subject_id: 'order:FM-1001',
          predicate: 'order_status',
          object_value: 'DELIVERED',
        })
      })
    })
  })
})
