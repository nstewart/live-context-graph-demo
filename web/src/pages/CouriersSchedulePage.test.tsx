import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import CouriersSchedulePage from './CouriersSchedulePage'
import { mockCouriers, mockCourierSubjectInfo } from '../test/mocks'

// Mock the API client
vi.mock('../api/client', () => ({
  freshmartApi: {
    listCouriers: vi.fn(),
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

const mockStores = [
  { store_id: 'store:BK-01', store_name: 'Brooklyn Heights', store_address: '123 Main St', store_zone: 'Brooklyn', store_status: 'ACTIVE', store_capacity_orders_per_hour: 50, inventory_items: [] },
  { store_id: 'store:MH-01', store_name: 'Manhattan', store_address: '456 Broadway', store_zone: 'Manhattan', store_status: 'ACTIVE', store_capacity_orders_per_hour: 75, inventory_items: [] },
]

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

describe('CouriersSchedulePage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Default mock for stores
    vi.mocked(freshmartApi.listStores).mockResolvedValue({ data: mockStores } as never)
  })

  describe('Rendering', () => {
    it('shows loading state initially', () => {
      vi.mocked(freshmartApi.listCouriers).mockReturnValue(new Promise(() => {}))
      renderWithClient(<CouriersSchedulePage />)
      expect(screen.getByText('Loading couriers...')).toBeInTheDocument()
    })

    it('renders couriers when loaded', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: mockCouriers } as never)
      renderWithClient(<CouriersSchedulePage />)

      await waitFor(() => {
        expect(screen.getByText(/Mike Johnson/)).toBeInTheDocument()
      })
      expect(screen.getByText(/Sarah Davis/)).toBeInTheDocument()
    })

    it('shows error state when API fails', async () => {
      vi.mocked(freshmartApi.listCouriers).mockRejectedValue(new Error('API Error'))
      renderWithClient(<CouriersSchedulePage />)

      await waitFor(() => {
        expect(screen.getByText(/Error loading couriers/)).toBeInTheDocument()
      })
    })

    it('displays page title and description', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: [] } as never)
      renderWithClient(<CouriersSchedulePage />)

      expect(screen.getByText('Couriers & Schedule')).toBeInTheDocument()
      expect(screen.getByText(/View courier status and assigned tasks/)).toBeInTheDocument()
    })

    it('shows Add Courier button', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: [] } as never)
      renderWithClient(<CouriersSchedulePage />)

      expect(screen.getByText('Add Courier')).toBeInTheDocument()
    })
  })

  describe('Create Courier Modal', () => {
    it('opens create modal when Add Courier button is clicked', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: [] } as never)
      renderWithClient(<CouriersSchedulePage />)

      fireEvent.click(screen.getByText('Add Courier'))

      await waitFor(() => {
        expect(screen.getByText('Create Courier')).toBeInTheDocument()
      })
    })

    it('closes modal when Cancel is clicked', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: [] } as never)
      renderWithClient(<CouriersSchedulePage />)

      fireEvent.click(screen.getByText('Add Courier'))
      await waitFor(() => {
        expect(screen.getByText('Create Courier')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Cancel'))

      await waitFor(() => {
        expect(screen.queryByText('Create Courier')).not.toBeInTheDocument()
      })
    })

    it('has required form fields', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: [] } as never)
      renderWithClient(<CouriersSchedulePage />)

      fireEvent.click(screen.getByText('Add Courier'))

      await waitFor(() => {
        expect(screen.getByText(/Courier ID/)).toBeInTheDocument()
        expect(screen.getByText(/Name/)).toBeInTheDocument()
        expect(screen.getByText(/Vehicle Type/)).toBeInTheDocument()
        expect(screen.getByText(/Home Store \*/)).toBeInTheDocument()
        expect(screen.getByText(/Status/)).toBeInTheDocument()
      })
    })

    it('calls createBatch API when form is submitted', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: [] } as never)
      vi.mocked(triplesApi.createBatch).mockResolvedValue({ data: [] } as never)

      renderWithClient(<CouriersSchedulePage />)

      fireEvent.click(screen.getByText('Add Courier'))

      await waitFor(() => {
        expect(screen.getByText('Create Courier')).toBeInTheDocument()
      })

      // Wait for stores dropdown to be populated
      await waitFor(() => {
        expect(screen.getByText('Brooklyn Heights (store:BK-01)')).toBeInTheDocument()
      })

      // Fill out form using placeholders
      fireEvent.change(screen.getByPlaceholderText('CR-01'), { target: { value: 'CR-99' } })
      fireEvent.change(screen.getByPlaceholderText('John Smith'), { target: { value: 'Test Courier' } })

      // Select home store from dropdown (3rd select: Status, Vehicle Type, Home Store)
      const selects = screen.getAllByRole('combobox')
      fireEvent.change(selects[2], { target: { value: 'store:BK-01' } })

      // Submit form
      const submitButtons = screen.getAllByRole('button')
      const createButton = submitButtons.find(btn => btn.textContent === 'Create')
      expect(createButton).toBeDefined()
      fireEvent.click(createButton!)

      await waitFor(() => {
        expect(triplesApi.createBatch).toHaveBeenCalled()
      })
    })

    it('creates courier with correct triples', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: [] } as never)
      vi.mocked(triplesApi.createBatch).mockResolvedValue({ data: [] } as never)

      renderWithClient(<CouriersSchedulePage />)

      fireEvent.click(screen.getByText('Add Courier'))

      await waitFor(() => {
        expect(screen.getByText('Create Courier')).toBeInTheDocument()
      })

      // Wait for stores dropdown to be populated
      await waitFor(() => {
        expect(screen.getByText('Brooklyn Heights (store:BK-01)')).toBeInTheDocument()
      })

      fireEvent.change(screen.getByPlaceholderText('CR-01'), { target: { value: 'CR-99' } })
      fireEvent.change(screen.getByPlaceholderText('John Smith'), { target: { value: 'Test Courier' } })

      // Select home store from dropdown (3rd select: Status, Vehicle Type, Home Store)
      const selects = screen.getAllByRole('combobox')
      fireEvent.change(selects[2], { target: { value: 'store:BK-01' } })

      const submitButtons = screen.getAllByRole('button')
      const createButton = submitButtons.find(btn => btn.textContent === 'Create')
      fireEvent.click(createButton!)

      await waitFor(() => {
        expect(triplesApi.createBatch).toHaveBeenCalledWith(
          expect.arrayContaining([
            expect.objectContaining({ subject_id: 'courier:CR-99', predicate: 'courier_name' }),
            expect.objectContaining({ subject_id: 'courier:CR-99', predicate: 'vehicle_type' }),
            expect.objectContaining({ subject_id: 'courier:CR-99', predicate: 'courier_home_store' }),
            expect.objectContaining({ subject_id: 'courier:CR-99', predicate: 'courier_status' }),
          ])
        )
      })
    })
  })

  describe('Edit Courier', () => {
    it('opens edit modal when edit button is clicked', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: mockCouriers } as never)
      renderWithClient(<CouriersSchedulePage />)

      await waitFor(() => {
        expect(screen.getByText(/Mike Johnson/)).toBeInTheDocument()
      })

      const editButtons = screen.getAllByTitle('Edit courier')
      fireEvent.click(editButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Edit Courier')).toBeInTheDocument()
      })
    })

    it('populates form with existing courier data', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: mockCouriers } as never)
      renderWithClient(<CouriersSchedulePage />)

      await waitFor(() => {
        expect(screen.getByText(/Mike Johnson/)).toBeInTheDocument()
      })

      const editButtons = screen.getAllByTitle('Edit courier')
      fireEvent.click(editButtons[0])

      await waitFor(() => {
        const courierIdInput = screen.getByPlaceholderText('CR-01') as HTMLInputElement
        expect(courierIdInput.value).toBe('C-101')
        expect(courierIdInput.disabled).toBe(true)
      })
    })

    it('calls update API when edit form is submitted', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: mockCouriers } as never)
      vi.mocked(triplesApi.getSubject).mockResolvedValue({ data: mockCourierSubjectInfo } as never)
      vi.mocked(triplesApi.update).mockResolvedValue({ data: {} } as never)
      vi.mocked(triplesApi.create).mockResolvedValue({ data: {} } as never)

      renderWithClient(<CouriersSchedulePage />)

      await waitFor(() => {
        expect(screen.getByText(/Mike Johnson/)).toBeInTheDocument()
      })

      const editButtons = screen.getAllByTitle('Edit courier')
      fireEvent.click(editButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Edit Courier')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Update'))

      await waitFor(() => {
        expect(triplesApi.getSubject).toHaveBeenCalledWith('courier:C-101')
      })
    })
  })

  describe('Delete Courier', () => {
    it('shows delete confirmation modal when delete button is clicked', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: mockCouriers } as never)
      renderWithClient(<CouriersSchedulePage />)

      await waitFor(() => {
        expect(screen.getByText(/Mike Johnson/)).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByTitle('Delete courier')
      fireEvent.click(deleteButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Delete Courier')).toBeInTheDocument()
        expect(screen.getByText(/Are you sure you want to delete/)).toBeInTheDocument()
      })
    })

    it('cancels delete when Cancel is clicked', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: mockCouriers } as never)
      renderWithClient(<CouriersSchedulePage />)

      await waitFor(() => {
        expect(screen.getByText(/Mike Johnson/)).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByTitle('Delete courier')
      fireEvent.click(deleteButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Delete Courier')).toBeInTheDocument()
      })

      const cancelButtons = screen.getAllByText('Cancel')
      fireEvent.click(cancelButtons[cancelButtons.length - 1])

      await waitFor(() => {
        expect(screen.queryByText('Delete Courier')).not.toBeInTheDocument()
      })
    })

    it('calls deleteSubject API when delete is confirmed', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: mockCouriers } as never)
      vi.mocked(triplesApi.deleteSubject).mockResolvedValue({ data: {} } as never)

      renderWithClient(<CouriersSchedulePage />)

      await waitFor(() => {
        expect(screen.getByText(/Mike Johnson/)).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByTitle('Delete courier')
      fireEvent.click(deleteButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Delete Courier')).toBeInTheDocument()
      })

      // Find the Delete button in the modal
      const allButtons = screen.getAllByRole('button')
      const deleteConfirmButton = allButtons.find(btn => btn.textContent === 'Delete')
      expect(deleteConfirmButton).toBeDefined()
      fireEvent.click(deleteConfirmButton!)

      await waitFor(() => {
        expect(triplesApi.deleteSubject).toHaveBeenCalledWith('courier:C-101')
      })
    })
  })

  describe('Courier Card Display', () => {
    it('displays courier name', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: mockCouriers } as never)
      renderWithClient(<CouriersSchedulePage />)

      await waitFor(() => {
        expect(screen.getByText(/Mike Johnson/)).toBeInTheDocument()
        expect(screen.getByText(/Sarah Davis/)).toBeInTheDocument()
      })
    })

    it('displays vehicle type', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: mockCouriers } as never)
      renderWithClient(<CouriersSchedulePage />)

      await waitFor(() => {
        const vehicleTypes = screen.getAllByText('bike')
        expect(vehicleTypes.length).toBeGreaterThan(0)
      })
    })

    it('displays home store', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: mockCouriers } as never)
      renderWithClient(<CouriersSchedulePage />)

      await waitFor(() => {
        // Home store now shows "Store Name (store:ID)" format
        expect(screen.getByText(/Brooklyn Heights \(store:BK-01\)/)).toBeInTheDocument()
        expect(screen.getByText(/Manhattan \(store:MH-01\)/)).toBeInTheDocument()
      })
    })
  })

  describe('Tasks Display', () => {
    it('displays assigned tasks count', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: mockCouriers } as never)
      renderWithClient(<CouriersSchedulePage />)

      await waitFor(() => {
        expect(screen.getByText('Assigned Tasks (1)')).toBeInTheDocument()
        expect(screen.getByText('Assigned Tasks (0)')).toBeInTheDocument()
      })
    })

    it('shows "No active tasks" for couriers without tasks', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: mockCouriers } as never)
      renderWithClient(<CouriersSchedulePage />)

      await waitFor(() => {
        expect(screen.getByText('No active tasks')).toBeInTheDocument()
      })
    })

    it('displays task details for couriers with tasks', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: mockCouriers } as never)
      renderWithClient(<CouriersSchedulePage />)

      await waitFor(() => {
        expect(screen.getByText('order:FM-1001')).toBeInTheDocument()
        expect(screen.getByText('IN_PROGRESS')).toBeInTheDocument()
      })
    })
  })

  describe('Form Validation', () => {
    it('disables courier ID field when editing', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: mockCouriers } as never)
      renderWithClient(<CouriersSchedulePage />)

      await waitFor(() => {
        expect(screen.getByText(/Mike Johnson/)).toBeInTheDocument()
      })

      const editButtons = screen.getAllByTitle('Edit courier')
      fireEvent.click(editButtons[0])

      await waitFor(() => {
        const courierIdInput = screen.getByPlaceholderText('CR-01') as HTMLInputElement
        expect(courierIdInput.disabled).toBe(true)
      })
    })

    it('enables courier ID field when creating', async () => {
      vi.mocked(freshmartApi.listCouriers).mockResolvedValue({ data: [] } as never)
      renderWithClient(<CouriersSchedulePage />)

      fireEvent.click(screen.getByText('Add Courier'))

      await waitFor(() => {
        const courierIdInput = screen.getByPlaceholderText('CR-01') as HTMLInputElement
        expect(courierIdInput.disabled).toBe(false)
      })
    })
  })
})
