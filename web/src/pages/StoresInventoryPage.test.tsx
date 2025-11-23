import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import StoresInventoryPage from './StoresInventoryPage'
import { mockStoreWithInventory, mockStoreSubjectInfo } from '../test/mocks'

// Mock the API client
vi.mock('../api/client', () => ({
  freshmartApi: {
    listStores: vi.fn(),
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

describe('StoresInventoryPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('Rendering', () => {
    it('shows loading state initially', () => {
      vi.mocked(freshmartApi.listStores).mockReturnValue(new Promise(() => {}))
      renderWithClient(<StoresInventoryPage />)
      expect(screen.getByText('Loading stores...')).toBeInTheDocument()
    })

    it('renders stores when loaded', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [mockStoreWithInventory] } as never)
      renderWithClient(<StoresInventoryPage />)

      await waitFor(() => {
        expect(screen.getByText('FreshMart Brooklyn Heights')).toBeInTheDocument()
      })
    })

    it('shows error state when API fails', async () => {
      vi.mocked(freshmartApi.listStores).mockRejectedValue(new Error('API Error'))
      renderWithClient(<StoresInventoryPage />)

      await waitFor(() => {
        expect(screen.getByText(/Error loading stores/)).toBeInTheDocument()
      })
    })

    it('displays page title and description', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [] } as never)
      renderWithClient(<StoresInventoryPage />)

      expect(screen.getByText('Stores & Inventory')).toBeInTheDocument()
      expect(screen.getByText(/Monitor store status and inventory levels/)).toBeInTheDocument()
    })

    it('shows Add Store button', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [] } as never)
      renderWithClient(<StoresInventoryPage />)

      expect(screen.getByText('Add Store')).toBeInTheDocument()
    })
  })

  describe('Create Store Modal', () => {
    it('opens create modal when Add Store button is clicked', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [] } as never)
      renderWithClient(<StoresInventoryPage />)

      fireEvent.click(screen.getByText('Add Store'))

      await waitFor(() => {
        expect(screen.getByText('Create Store')).toBeInTheDocument()
      })
    })

    it('closes modal when Cancel is clicked', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [] } as never)
      renderWithClient(<StoresInventoryPage />)

      fireEvent.click(screen.getByText('Add Store'))
      await waitFor(() => {
        expect(screen.getByText('Create Store')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Cancel'))

      await waitFor(() => {
        expect(screen.queryByText('Create Store')).not.toBeInTheDocument()
      })
    })

    it('has required form fields', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [] } as never)
      renderWithClient(<StoresInventoryPage />)

      fireEvent.click(screen.getByText('Add Store'))

      await waitFor(() => {
        expect(screen.getByText(/Store ID/)).toBeInTheDocument()
        expect(screen.getByText(/Store Name/)).toBeInTheDocument()
        expect(screen.getByText(/Address/)).toBeInTheDocument()
        expect(screen.getByText(/Zone/)).toBeInTheDocument()
      })
    })

    it('calls createBatch API when form is submitted', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [] } as never)
      vi.mocked(triplesApi.createBatch).mockResolvedValue({ data: [] } as never)

      renderWithClient(<StoresInventoryPage />)

      fireEvent.click(screen.getByText('Add Store'))

      await waitFor(() => {
        expect(screen.getByText('Create Store')).toBeInTheDocument()
      })

      // Fill out form using placeholders
      fireEvent.change(screen.getByPlaceholderText('BK-01'), { target: { value: 'TEST-01' } })
      fireEvent.change(screen.getByPlaceholderText('FreshMart Brooklyn'), { target: { value: 'Test Store' } })
      fireEvent.change(screen.getByPlaceholderText('123 Main St, Brooklyn, NY'), { target: { value: '123 Test Ave' } })
      fireEvent.change(screen.getByPlaceholderText('BK'), { target: { value: 'TEST' } })

      // Submit form
      const submitButtons = screen.getAllByRole('button')
      const createButton = submitButtons.find(btn => btn.textContent === 'Create')
      expect(createButton).toBeDefined()
      fireEvent.click(createButton!)

      await waitFor(() => {
        expect(triplesApi.createBatch).toHaveBeenCalled()
      })
    })
  })

  describe('Edit Store', () => {
    it('opens edit modal when edit button is clicked', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [mockStoreWithInventory] } as never)
      renderWithClient(<StoresInventoryPage />)

      await waitFor(() => {
        expect(screen.getByText('FreshMart Brooklyn Heights')).toBeInTheDocument()
      })

      const editButtons = screen.getAllByTitle('Edit store')
      fireEvent.click(editButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Edit Store')).toBeInTheDocument()
      })
    })

    it('populates form with existing store data', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [mockStoreWithInventory] } as never)
      renderWithClient(<StoresInventoryPage />)

      await waitFor(() => {
        expect(screen.getByText('FreshMart Brooklyn Heights')).toBeInTheDocument()
      })

      const editButtons = screen.getAllByTitle('Edit store')
      fireEvent.click(editButtons[0])

      await waitFor(() => {
        const storeIdInput = screen.getByPlaceholderText('BK-01') as HTMLInputElement
        expect(storeIdInput.value).toBe('BK-01')
      })
    })

    it('calls update API when edit form is submitted', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [mockStoreWithInventory] } as never)
      vi.mocked(triplesApi.getSubject).mockResolvedValue({ data: mockStoreSubjectInfo } as never)
      vi.mocked(triplesApi.update).mockResolvedValue({ data: {} } as never)
      vi.mocked(triplesApi.create).mockResolvedValue({ data: {} } as never)

      renderWithClient(<StoresInventoryPage />)

      await waitFor(() => {
        expect(screen.getByText('FreshMart Brooklyn Heights')).toBeInTheDocument()
      })

      const editButtons = screen.getAllByTitle('Edit store')
      fireEvent.click(editButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Edit Store')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Update'))

      await waitFor(() => {
        expect(triplesApi.getSubject).toHaveBeenCalledWith('store:BK-01')
      })
    })
  })

  describe('Delete Store', () => {
    it('shows delete confirmation modal when delete button is clicked', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [mockStoreWithInventory] } as never)
      renderWithClient(<StoresInventoryPage />)

      await waitFor(() => {
        expect(screen.getByText('FreshMart Brooklyn Heights')).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByTitle('Delete store')
      fireEvent.click(deleteButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Delete Store')).toBeInTheDocument()
        expect(screen.getByText(/Are you sure you want to delete/)).toBeInTheDocument()
      })
    })

    it('calls deleteSubject API when delete is confirmed', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [mockStoreWithInventory] } as never)
      vi.mocked(triplesApi.deleteSubject).mockResolvedValue({ data: {} } as never)

      renderWithClient(<StoresInventoryPage />)

      await waitFor(() => {
        expect(screen.getByText('FreshMart Brooklyn Heights')).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByTitle('Delete store')
      fireEvent.click(deleteButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Delete Store')).toBeInTheDocument()
      })

      // Find the Delete button in the modal by looking at all buttons
      const allButtons = screen.getAllByRole('button')
      const deleteConfirmButton = allButtons.find(btn => btn.textContent === 'Delete')
      expect(deleteConfirmButton).toBeDefined()
      fireEvent.click(deleteConfirmButton!)

      await waitFor(() => {
        expect(triplesApi.deleteSubject).toHaveBeenCalledWith('store:BK-01')
      })
    })
  })

  describe('Inventory Display', () => {
    it('displays inventory items for a store', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [mockStoreWithInventory] } as never)
      renderWithClient(<StoresInventoryPage />)

      await waitFor(() => {
        expect(screen.getByText('product:MILK-001')).toBeInTheDocument()
        expect(screen.getByText('product:BREAD-001')).toBeInTheDocument()
      })
    })

    it('displays stock levels', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [mockStoreWithInventory] } as never)
      renderWithClient(<StoresInventoryPage />)

      await waitFor(() => {
        expect(screen.getByText('50')).toBeInTheDocument()
        expect(screen.getByText('5')).toBeInTheDocument()
      })
    })

    it('shows Add Item button for inventory', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [mockStoreWithInventory] } as never)
      renderWithClient(<StoresInventoryPage />)

      await waitFor(() => {
        expect(screen.getByText('Add Item')).toBeInTheDocument()
      })
    })
  })

  describe('Inventory CRUD', () => {
    it('opens inventory modal when Add Item is clicked', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [mockStoreWithInventory] } as never)
      renderWithClient(<StoresInventoryPage />)

      await waitFor(() => {
        expect(screen.getByText('Add Item')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Add Item'))

      await waitFor(() => {
        expect(screen.getByText('Add Inventory Item')).toBeInTheDocument()
      })
    })

    it('shows inventory edit buttons', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [mockStoreWithInventory] } as never)
      renderWithClient(<StoresInventoryPage />)

      await waitFor(() => {
        const editButtons = screen.getAllByTitle('Edit')
        expect(editButtons.length).toBeGreaterThan(0)
      })
    })

    it('shows inventory delete buttons', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [mockStoreWithInventory] } as never)
      renderWithClient(<StoresInventoryPage />)

      await waitFor(() => {
        const deleteButtons = screen.getAllByTitle('Delete')
        expect(deleteButtons.length).toBeGreaterThan(0)
      })
    })
  })

  describe('Store Status Display', () => {
    it('displays store status badge', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [mockStoreWithInventory] } as never)
      renderWithClient(<StoresInventoryPage />)

      await waitFor(() => {
        expect(screen.getByText('OPEN')).toBeInTheDocument()
      })
    })

    it('displays store zone', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [mockStoreWithInventory] } as never)
      renderWithClient(<StoresInventoryPage />)

      await waitFor(() => {
        // Zone is displayed in a <p> element with "Zone: " and zone name as separate text nodes
        // Use regex to match the partial text
        expect(screen.getByText(/Zone:/)).toBeInTheDocument()
      })
    })

    it('displays store address', async () => {
      vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: [mockStoreWithInventory] } as never)
      renderWithClient(<StoresInventoryPage />)

      await waitFor(() => {
        expect(screen.getByText('100 Court St, Brooklyn')).toBeInTheDocument()
      })
    })
  })
})
