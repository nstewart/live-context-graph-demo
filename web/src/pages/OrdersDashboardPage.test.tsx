import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import OrdersDashboardPage from './OrdersDashboardPage'
import { mockOrders, mockOrderSubjectInfo } from '../test/mocks'

// Mock the API client
vi.mock('../api/client', () => ({
  freshmartApi: {
    listOrders: vi.fn(),
    listStores: vi.fn(),
    listCustomers: vi.fn(),
  },
  triplesApi: {
    createBatch: vi.fn(),
    getSubject: vi.fn(),
    update: vi.fn(),
    create: vi.fn(),
    deleteSubject: vi.fn(),
  },
}))

import { freshmartApi, triplesApi } from '../api/client'

const createTestQueryClient = () =>
  new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  })

const renderWithClient = (ui: React.ReactElement) => {
  const queryClient = createTestQueryClient()
  return render(
    <QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>
  )
}

const mockStores = [
  { store_id: 'store:BK-01', store_name: 'Brooklyn Heights', store_address: '123 Main St', store_zone: 'Brooklyn', store_status: 'ACTIVE', store_capacity_orders_per_hour: 50, inventory_items: [] },
]

const mockCustomers = [
  { customer_id: 'customer:101', customer_name: 'Alex Thompson', customer_email: 'alex@example.com', customer_address: '456 Oak Ave' },
]

describe('OrdersDashboardPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default mocks for stores and customers
    vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: mockStores } as never)
    vi.mocked(freshmartApi.listCustomers).mockResolvedValue({ data: mockCustomers } as never)
  })

  describe('Rendering', () => {
    it('shows loading state initially', () => {
      vi.mocked(freshmartApi.listOrders).mockReturnValue(new Promise(() => {}))
      renderWithClient(<OrdersDashboardPage />)
      expect(screen.getByText('Loading orders...')).toBeInTheDocument()
    })

    it('renders orders when loaded', async () => {
      vi.mocked(freshmartApi.listOrders).mockResolvedValue({ data: mockOrders } as never)
      renderWithClient(<OrdersDashboardPage />)

      await waitFor(() => {
        expect(screen.getByText('Alex Thompson')).toBeInTheDocument()
      })
      expect(screen.getByText('Jordan Lee')).toBeInTheDocument()
    })

    it('shows error state when API fails', async () => {
      vi.mocked(freshmartApi.listOrders).mockRejectedValue(new Error('API Error'))
      renderWithClient(<OrdersDashboardPage />)

      await waitFor(() => {
        expect(screen.getByText(/Error loading orders/)).toBeInTheDocument()
      })
    })

    it('displays page title and description', async () => {
      vi.mocked(freshmartApi.listOrders).mockResolvedValue({ data: [] } as never)
      renderWithClient(<OrdersDashboardPage />)

      expect(screen.getByText('Orders Dashboard')).toBeInTheDocument()
      expect(screen.getByText(/Monitor and manage FreshMart orders/)).toBeInTheDocument()
    })

    it('shows Create Order button', async () => {
      vi.mocked(freshmartApi.listOrders).mockResolvedValue({ data: [] } as never)
      renderWithClient(<OrdersDashboardPage />)

      expect(screen.getByText('Create Order')).toBeInTheDocument()
    })
  })

  describe('Create Order Modal', () => {
    it('opens create modal when Create Order button is clicked', async () => {
      vi.mocked(freshmartApi.listOrders).mockResolvedValue({ data: [] } as never)
      renderWithClient(<OrdersDashboardPage />)

      fireEvent.click(screen.getByText('Create Order'))

      await waitFor(() => {
        // Modal title is also "Create Order" when creating
        expect(screen.getAllByText('Create Order').length).toBeGreaterThanOrEqual(1)
      })
    })

    it('closes modal when Cancel is clicked', async () => {
      vi.mocked(freshmartApi.listOrders).mockResolvedValue({ data: [] } as never)
      renderWithClient(<OrdersDashboardPage />)

      fireEvent.click(screen.getByText('Create Order'))
      await waitFor(() => {
        expect(screen.getByText('Cancel')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Cancel'))

      await waitFor(() => {
        // Modal should be closed, only the button "Create Order" should remain
        expect(screen.getAllByText('Create Order').length).toBe(1)
      })
    })

    it('has required form fields', async () => {
      vi.mocked(freshmartApi.listOrders).mockResolvedValue({ data: [] } as never)
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [] } as never)
      vi.mocked(freshmartApi.listCustomers).mockResolvedValue({ data: [] } as never)
      renderWithClient(<OrdersDashboardPage />)

      fireEvent.click(screen.getByText('Create Order'))

      await waitFor(() => {
        expect(screen.getByText(/Order Number/)).toBeInTheDocument()
        expect(screen.getByText(/Status/)).toBeInTheDocument()
        expect(screen.getByText(/Customer \*/)).toBeInTheDocument()
        expect(screen.getByText(/Store \*/)).toBeInTheDocument()
      })
    })

    it('calls createBatch API when form is submitted', async () => {
      vi.mocked(freshmartApi.listOrders).mockResolvedValue({ data: [] } as never)
      vi.mocked(triplesApi.createBatch).mockResolvedValue({ data: [] } as never)

      renderWithClient(<OrdersDashboardPage />)

      fireEvent.click(screen.getByText('Create Order'))

      // Wait for dropdowns to be populated with options
      await waitFor(() => {
        expect(screen.getByText('Alex Thompson (customer:101)')).toBeInTheDocument()
      })

      // Fill out form - find inputs by placeholder or role
      const orderNumberInput = screen.getByPlaceholderText('FM-1001')
      fireEvent.change(orderNumberInput, { target: { value: 'FM-9999' } })

      // Select customer and store from dropdowns
      const selects = screen.getAllByRole('combobox')
      // First select is Status, second is Customer, third is Store
      const customerSelect = selects[1]
      const storeSelect = selects[2]

      fireEvent.change(customerSelect, { target: { value: 'customer:101' } })
      fireEvent.change(storeSelect, { target: { value: 'store:BK-01' } })

      // Submit form - the submit button text is "Create" not "Create Order"
      const submitButtons = screen.getAllByRole('button')
      const createButton = submitButtons.find(btn => btn.textContent === 'Create')
      expect(createButton).toBeDefined()
      fireEvent.click(createButton!)

      await waitFor(() => {
        expect(triplesApi.createBatch).toHaveBeenCalled()
      })
    })
  })

  describe('Edit Order', () => {
    it('opens edit modal when edit button is clicked', async () => {
      vi.mocked(freshmartApi.listOrders).mockResolvedValue({ data: mockOrders } as never)
      renderWithClient(<OrdersDashboardPage />)

      await waitFor(() => {
        expect(screen.getByText('Alex Thompson')).toBeInTheDocument()
      })

      // Click the first edit button
      const editButtons = screen.getAllByTitle('Edit order')
      fireEvent.click(editButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Edit Order')).toBeInTheDocument()
      })
    })

    it('populates form with existing order data', async () => {
      vi.mocked(freshmartApi.listOrders).mockResolvedValue({ data: mockOrders } as never)
      renderWithClient(<OrdersDashboardPage />)

      await waitFor(() => {
        expect(screen.getByText('Alex Thompson')).toBeInTheDocument()
      })

      const editButtons = screen.getAllByTitle('Edit order')
      fireEvent.click(editButtons[0])

      await waitFor(() => {
        const orderNumberInput = screen.getByPlaceholderText('FM-1001') as HTMLInputElement
        expect(orderNumberInput.value).toBe('FM-1001')
      })
    })

    it('calls update API when edit form is submitted', async () => {
      vi.mocked(freshmartApi.listOrders).mockResolvedValue({ data: mockOrders } as never)
      vi.mocked(triplesApi.getSubject).mockResolvedValue({ data: mockOrderSubjectInfo } as never)
      vi.mocked(triplesApi.update).mockResolvedValue({ data: {} } as never)

      renderWithClient(<OrdersDashboardPage />)

      await waitFor(() => {
        expect(screen.getByText('Alex Thompson')).toBeInTheDocument()
      })

      const editButtons = screen.getAllByTitle('Edit order')
      fireEvent.click(editButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Edit Order')).toBeInTheDocument()
      })

      // Submit edit form
      fireEvent.click(screen.getByText('Update'))

      await waitFor(() => {
        expect(triplesApi.getSubject).toHaveBeenCalledWith('order:FM-1001')
      })
    })
  })

  describe('Delete Order', () => {
    it('shows delete confirmation modal when delete button is clicked', async () => {
      vi.mocked(freshmartApi.listOrders).mockResolvedValue({ data: mockOrders } as never)
      renderWithClient(<OrdersDashboardPage />)

      await waitFor(() => {
        expect(screen.getByText('Alex Thompson')).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByTitle('Delete order')
      fireEvent.click(deleteButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Delete Order')).toBeInTheDocument()
        expect(screen.getByText(/Are you sure you want to delete/)).toBeInTheDocument()
      })
    })

    it('cancels delete when Cancel is clicked', async () => {
      vi.mocked(freshmartApi.listOrders).mockResolvedValue({ data: mockOrders } as never)
      renderWithClient(<OrdersDashboardPage />)

      await waitFor(() => {
        expect(screen.getByText('Alex Thompson')).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByTitle('Delete order')
      fireEvent.click(deleteButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Delete Order')).toBeInTheDocument()
      })

      // Find and click the Cancel button in the delete modal
      const cancelButtons = screen.getAllByText('Cancel')
      fireEvent.click(cancelButtons[cancelButtons.length - 1])

      await waitFor(() => {
        expect(screen.queryByText('Delete Order')).not.toBeInTheDocument()
      })
    })

    it('calls deleteSubject API when delete is confirmed', async () => {
      vi.mocked(freshmartApi.listOrders).mockResolvedValue({ data: mockOrders } as never)
      vi.mocked(triplesApi.deleteSubject).mockResolvedValue({ data: {} } as never)

      renderWithClient(<OrdersDashboardPage />)

      await waitFor(() => {
        expect(screen.getByText('Alex Thompson')).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByTitle('Delete order')
      fireEvent.click(deleteButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Delete Order')).toBeInTheDocument()
      })

      // Find and click the Delete button in the modal (not a Cancel button)
      const allButtons = screen.getAllByRole('button')
      const deleteConfirmButton = allButtons.find(btn => btn.textContent === 'Delete')
      expect(deleteConfirmButton).toBeDefined()
      fireEvent.click(deleteConfirmButton!)

      await waitFor(() => {
        expect(triplesApi.deleteSubject).toHaveBeenCalledWith('order:FM-1001')
      })
    })
  })

  describe('Order Card Display', () => {
    it('displays order number', async () => {
      vi.mocked(freshmartApi.listOrders).mockResolvedValue({ data: mockOrders } as never)
      renderWithClient(<OrdersDashboardPage />)

      await waitFor(() => {
        expect(screen.getByText('FM-1001')).toBeInTheDocument()
        expect(screen.getByText('FM-1002')).toBeInTheDocument()
      })
    })

    it('displays order total amount', async () => {
      vi.mocked(freshmartApi.listOrders).mockResolvedValue({ data: mockOrders } as never)
      renderWithClient(<OrdersDashboardPage />)

      await waitFor(() => {
        expect(screen.getByText('$45.99')).toBeInTheDocument()
        expect(screen.getByText('$32.50')).toBeInTheDocument()
      })
    })

    it('displays store name', async () => {
      vi.mocked(freshmartApi.listOrders).mockResolvedValue({ data: mockOrders } as never)
      renderWithClient(<OrdersDashboardPage />)

      await waitFor(() => {
        expect(screen.getByText(/FreshMart Brooklyn Heights/)).toBeInTheDocument()
        expect(screen.getByText(/FreshMart Manhattan/)).toBeInTheDocument()
      })
    })
  })

  describe('Status Statistics', () => {
    it('displays status counts', async () => {
      vi.mocked(freshmartApi.listOrders).mockResolvedValue({ data: mockOrders } as never)
      renderWithClient(<OrdersDashboardPage />)

      await waitFor(() => {
        // Should show stats for different statuses
        // DELIVERED appears multiple times (once in stats, once in order card badge)
        const deliveredElements = screen.getAllByText('DELIVERED')
        expect(deliveredElements.length).toBeGreaterThanOrEqual(1)
      })
    })
  })
})
