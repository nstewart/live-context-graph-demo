import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import TriplesBrowserPage from './TriplesBrowserPage'

// Mock the API client
vi.mock('../api/client', () => ({
  triplesApi: {
    listSubjects: vi.fn(),
    getSubject: vi.fn(),
    getSubjectCounts: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    delete: vi.fn(),
    deleteSubject: vi.fn(),
  },
  ontologyApi: {
    listProperties: vi.fn(),
    listClasses: vi.fn(),
  },
}))

import { triplesApi, ontologyApi } from '../api/client'

const mockSubjects = [
  'order:FM-1001',
  'order:FM-1002',
  'customer:101',
  'customer:102',
  'store:BK-01',
  'courier:C-101',
]

const mockSubjectInfo = {
  subject_id: 'order:FM-1001',
  class_name: 'Order',
  class_id: 1,
  triples: [
    { id: 1, subject_id: 'order:FM-1001', predicate: 'order_status', object_value: 'CREATED', object_type: 'string', created_at: '', updated_at: '' },
    { id: 2, subject_id: 'order:FM-1001', predicate: 'order_store', object_value: 'store:BK-01', object_type: 'entity_ref', created_at: '', updated_at: '' },
    { id: 3, subject_id: 'order:FM-1001', predicate: 'order_total_amount', object_value: '99.50', object_type: 'decimal', created_at: '', updated_at: '' },
  ],
}

const mockClasses = [
  { id: 1, class_name: 'Order', prefix: 'order', description: 'Customer orders', parent_class_id: null, created_at: '', updated_at: '' },
  { id: 2, class_name: 'Store', prefix: 'store', description: 'Stores', parent_class_id: null, created_at: '', updated_at: '' },
  { id: 3, class_name: 'Customer', prefix: 'customer', description: 'Customers', parent_class_id: null, created_at: '', updated_at: '' },
  { id: 4, class_name: 'Courier', prefix: 'courier', description: 'Couriers', parent_class_id: null, created_at: '', updated_at: '' },
]

const mockProperties = [
  { id: 1, prop_name: 'order_status', domain_class_id: 1, range_kind: 'string', range_class_id: null, is_multi_valued: false, is_required: true, description: 'Order status', domain_class_name: 'Order', range_class_name: null, created_at: '', updated_at: '' },
  { id: 2, prop_name: 'order_store', domain_class_id: 1, range_kind: 'entity_ref', range_class_id: 2, is_multi_valued: false, is_required: true, description: 'Store for order', domain_class_name: 'Order', range_class_name: 'Store', created_at: '', updated_at: '' },
  { id: 3, prop_name: 'order_total_amount', domain_class_id: 1, range_kind: 'decimal', range_class_id: null, is_multi_valued: false, is_required: false, description: 'Order total', domain_class_name: 'Order', range_class_name: null, created_at: '', updated_at: '' },
  { id: 4, prop_name: 'store_name', domain_class_id: 2, range_kind: 'string', range_class_id: null, is_multi_valued: false, is_required: true, description: 'Store name', domain_class_name: 'Store', range_class_name: null, created_at: '', updated_at: '' },
]

const mockSubjectCounts = {
  total: 6,
  by_type: {
    order: 2,
    customer: 2,
    store: 1,
    courier: 1,
  },
}

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

describe('TriplesBrowserPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(ontologyApi.listClasses).mockResolvedValue({ data: mockClasses } as never)
    vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: mockProperties } as never)
    vi.mocked(triplesApi.getSubjectCounts).mockResolvedValue({ data: mockSubjectCounts } as never)
  })

  describe('Rendering', () => {
    it('displays page title and description', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: [] } as never)
      renderWithClient(<TriplesBrowserPage />)

      expect(screen.getByText('Triples Browser')).toBeInTheDocument()
      expect(screen.getByText(/Explore and manage entities/)).toBeInTheDocument()
    })

    it('shows Add Triple button', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: [] } as never)
      renderWithClient(<TriplesBrowserPage />)

      expect(screen.getByText('Add Triple')).toBeInTheDocument()
    })

    it('renders subjects list when loaded', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      renderWithClient(<TriplesBrowserPage />)

      await waitFor(() => {
        expect(screen.getByText('order:FM-1001')).toBeInTheDocument()
      })
      expect(screen.getByText('customer:101')).toBeInTheDocument()
    })

    it('shows entity type filter with counts', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      renderWithClient(<TriplesBrowserPage />)

      await waitFor(() => {
        // Dropdown now shows counts: "All entity types (6)"
        expect(screen.getByText('All entity types (6)')).toBeInTheDocument()
      })
    })

    it('shows total count of filtered subjects', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      renderWithClient(<TriplesBrowserPage />)

      await waitFor(() => {
        expect(screen.getByText('6 total')).toBeInTheDocument()
      })
    })
  })

  describe('Subject Selection', () => {
    it('shows subject details when a subject is clicked', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      vi.mocked(triplesApi.getSubject).mockResolvedValue({ data: mockSubjectInfo } as never)
      renderWithClient(<TriplesBrowserPage />)

      await waitFor(() => {
        expect(screen.getByText('order:FM-1001')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('order:FM-1001'))

      await waitFor(() => {
        expect(screen.getByText('order_status')).toBeInTheDocument()
      })
      expect(screen.getByText('CREATED')).toBeInTheDocument()
    })

    it('displays entity_ref values as clickable links', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      vi.mocked(triplesApi.getSubject).mockResolvedValue({ data: mockSubjectInfo } as never)
      renderWithClient(<TriplesBrowserPage />)

      await waitFor(() => {
        expect(screen.getByText('order:FM-1001')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('order:FM-1001'))

      await waitFor(() => {
        // Get all elements with store:BK-01 - one in subject list, one as entity_ref link
        const storeElements = screen.getAllByText('store:BK-01')
        // Find the one that's a button (entity_ref link in the triples table)
        const storeLink = storeElements.find(el => el.tagName === 'BUTTON' && el.classList.contains('text-green-600'))
        expect(storeLink).toBeDefined()
      })
    })

    it('shows edit and delete buttons for each triple', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      vi.mocked(triplesApi.getSubject).mockResolvedValue({ data: mockSubjectInfo } as never)
      renderWithClient(<TriplesBrowserPage />)

      await waitFor(() => {
        expect(screen.getByText('order:FM-1001')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('order:FM-1001'))

      await waitFor(() => {
        const editButtons = screen.getAllByTitle('Edit triple')
        const deleteButtons = screen.getAllByTitle('Delete triple')
        expect(editButtons.length).toBe(3)
        expect(deleteButtons.length).toBe(3)
      })
    })
  })

  describe('Entity Type Filter', () => {
    it('filters subjects by entity type', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      renderWithClient(<TriplesBrowserPage />)

      await waitFor(() => {
        expect(screen.getByText('6 total')).toBeInTheDocument()
      })

      // Find and change the entity type filter
      const selects = screen.getAllByRole('combobox')
      const entityTypeSelect = selects.find(s => s.textContent?.includes('All entity types'))
      fireEvent.change(entityTypeSelect || selects[0], { target: { value: 'order' } })

      // After filter change, the count comes from subjectCounts.by_type['order'] = 2
      await waitFor(() => {
        expect(screen.getByText('2 total')).toBeInTheDocument()
      })
    })
  })

  describe('Create Triple Modal', () => {
    it('opens create modal when Add Triple button is clicked', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      renderWithClient(<TriplesBrowserPage />)

      fireEvent.click(screen.getByText('Add Triple'))

      await waitFor(() => {
        expect(screen.getByText('Create Triple')).toBeInTheDocument()
      })
    })

    it('closes modal when Cancel is clicked', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      renderWithClient(<TriplesBrowserPage />)

      fireEvent.click(screen.getByText('Add Triple'))
      await waitFor(() => {
        expect(screen.getByText('Create Triple')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Cancel'))

      await waitFor(() => {
        expect(screen.queryByText('Create Triple')).not.toBeInTheDocument()
      })
    })

    it('has required form fields', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      renderWithClient(<TriplesBrowserPage />)

      fireEvent.click(screen.getByText('Add Triple'))

      await waitFor(() => {
        expect(screen.getByText(/Subject ID/)).toBeInTheDocument()
        expect(screen.getByText(/Predicate/)).toBeInTheDocument()
        expect(screen.getByText(/Value/)).toBeInTheDocument()
      })
    })

    it('shows class prefixes in subject dropdown', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      renderWithClient(<TriplesBrowserPage />)

      fireEvent.click(screen.getByText('Add Triple'))

      await waitFor(() => {
        expect(screen.getByText('order')).toBeInTheDocument()
        expect(screen.getByText('store')).toBeInTheDocument()
        expect(screen.getByText('customer')).toBeInTheDocument()
      })
    })

    it('calls create API when form is submitted', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      vi.mocked(triplesApi.create).mockResolvedValue({ data: mockSubjectInfo.triples[0] } as never)

      renderWithClient(<TriplesBrowserPage />)

      fireEvent.click(screen.getByText('Add Triple'))

      await waitFor(() => {
        expect(screen.getByText('Create Triple')).toBeInTheDocument()
      })

      // Wait for ontology data to load
      await waitFor(() => {
        expect(screen.getByText('order')).toBeInTheDocument()
      })

      // Get all selects in the modal (entity type filter is outside modal)
      // Modal selects are: prefix dropdown, predicate dropdown
      const modalSelects = screen.getAllByRole('combobox')
      // First select after opening modal is the prefix select (it has "Prefix..." option)
      const prefixSelect = modalSelects.find(s => {
        const options = s.querySelectorAll('option')
        return Array.from(options).some(o => o.textContent === 'Prefix...')
      })

      // Select prefix
      fireEvent.change(prefixSelect!, { target: { value: 'order' } })

      // Enter ID
      fireEvent.change(screen.getByPlaceholderText('entity-id'), { target: { value: 'FM-9999' } })

      // Get fresh list of selects after prefix change
      const updatedSelects = screen.getAllByRole('combobox')
      const predicateSelect = updatedSelects.find(s => {
        const options = s.querySelectorAll('option')
        return Array.from(options).some(o => o.textContent === 'Select a predicate...')
      })

      // Select predicate
      fireEvent.change(predicateSelect!, { target: { value: 'order_status' } })

      // Wait for value input to appear
      await waitFor(() => {
        expect(screen.getByPlaceholderText('Enter value...')).toBeInTheDocument()
      })

      // Enter value
      fireEvent.change(screen.getByPlaceholderText('Enter value...'), { target: { value: 'PENDING' } })

      // Submit
      const createButton = screen.getAllByRole('button').find(btn => btn.textContent === 'Create')
      fireEvent.click(createButton!)

      await waitFor(() => {
        expect(triplesApi.create).toHaveBeenCalledWith(expect.objectContaining({
          subject_id: 'order:FM-9999',
          predicate: 'order_status',
          object_value: 'PENDING',
        }))
      })
    })
  })

  describe('Edit Triple', () => {
    it('opens edit modal when edit button is clicked', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      vi.mocked(triplesApi.getSubject).mockResolvedValue({ data: mockSubjectInfo } as never)
      renderWithClient(<TriplesBrowserPage />)

      await waitFor(() => {
        expect(screen.getByText('order:FM-1001')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('order:FM-1001'))

      await waitFor(() => {
        expect(screen.getByText('order_status')).toBeInTheDocument()
      })

      const editButtons = screen.getAllByTitle('Edit triple')
      fireEvent.click(editButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Edit Triple')).toBeInTheDocument()
      })
    })

    it('populates form with existing triple data', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      vi.mocked(triplesApi.getSubject).mockResolvedValue({ data: mockSubjectInfo } as never)
      renderWithClient(<TriplesBrowserPage />)

      await waitFor(() => {
        expect(screen.getByText('order:FM-1001')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('order:FM-1001'))

      await waitFor(() => {
        expect(screen.getByText('order_status')).toBeInTheDocument()
      })

      const editButtons = screen.getAllByTitle('Edit triple')
      fireEvent.click(editButtons[0])

      await waitFor(() => {
        const inputs = screen.getAllByRole('textbox') as HTMLInputElement[]
        // Subject ID should be disabled and contain the value
        const subjectInput = inputs.find(i => i.value === 'order:FM-1001')
        expect(subjectInput).toBeDefined()
        expect(subjectInput?.disabled).toBe(true)
      })
    })

    it('calls update API when edit form is submitted', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      vi.mocked(triplesApi.getSubject).mockResolvedValue({ data: mockSubjectInfo } as never)
      vi.mocked(triplesApi.update).mockResolvedValue({ data: mockSubjectInfo.triples[0] } as never)

      renderWithClient(<TriplesBrowserPage />)

      await waitFor(() => {
        expect(screen.getByText('order:FM-1001')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('order:FM-1001'))

      await waitFor(() => {
        expect(screen.getByText('order_status')).toBeInTheDocument()
      })

      const editButtons = screen.getAllByTitle('Edit triple')
      fireEvent.click(editButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Edit Triple')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Update'))

      await waitFor(() => {
        expect(triplesApi.update).toHaveBeenCalledWith(1, expect.any(Object))
      })
    })
  })

  describe('Delete Triple', () => {
    it('shows delete confirmation modal when delete button is clicked', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      vi.mocked(triplesApi.getSubject).mockResolvedValue({ data: mockSubjectInfo } as never)
      renderWithClient(<TriplesBrowserPage />)

      await waitFor(() => {
        expect(screen.getByText('order:FM-1001')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('order:FM-1001'))

      await waitFor(() => {
        expect(screen.getByText('order_status')).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByTitle('Delete triple')
      fireEvent.click(deleteButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Delete Triple')).toBeInTheDocument()
        expect(screen.getByText(/Are you sure you want to delete/)).toBeInTheDocument()
      })
    })

    it('cancels delete when Cancel is clicked', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      vi.mocked(triplesApi.getSubject).mockResolvedValue({ data: mockSubjectInfo } as never)
      renderWithClient(<TriplesBrowserPage />)

      await waitFor(() => {
        expect(screen.getByText('order:FM-1001')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('order:FM-1001'))

      await waitFor(() => {
        expect(screen.getByText('order_status')).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByTitle('Delete triple')
      fireEvent.click(deleteButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Delete Triple')).toBeInTheDocument()
      })

      const cancelButtons = screen.getAllByText('Cancel')
      fireEvent.click(cancelButtons[cancelButtons.length - 1])

      await waitFor(() => {
        expect(screen.queryByText('Delete Triple')).not.toBeInTheDocument()
      })
    })

    it('calls delete API when delete is confirmed', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      vi.mocked(triplesApi.getSubject).mockResolvedValue({ data: mockSubjectInfo } as never)
      vi.mocked(triplesApi.delete).mockResolvedValue({ data: {} } as never)

      renderWithClient(<TriplesBrowserPage />)

      await waitFor(() => {
        expect(screen.getByText('order:FM-1001')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('order:FM-1001'))

      await waitFor(() => {
        expect(screen.getByText('order_status')).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByTitle('Delete triple')
      fireEvent.click(deleteButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Delete Triple')).toBeInTheDocument()
      })

      const allButtons = screen.getAllByRole('button')
      const deleteConfirmButton = allButtons.find(btn => btn.textContent === 'Delete')
      fireEvent.click(deleteConfirmButton!)

      await waitFor(() => {
        expect(triplesApi.delete).toHaveBeenCalledWith(1)
      })
    })
  })

  describe('Delete Subject', () => {
    it('shows Delete Subject button when viewing a subject', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      vi.mocked(triplesApi.getSubject).mockResolvedValue({ data: mockSubjectInfo } as never)
      renderWithClient(<TriplesBrowserPage />)

      await waitFor(() => {
        expect(screen.getByText('order:FM-1001')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('order:FM-1001'))

      await waitFor(() => {
        expect(screen.getByText('Delete Subject')).toBeInTheDocument()
      })
    })

    it('shows delete subject confirmation modal', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      vi.mocked(triplesApi.getSubject).mockResolvedValue({ data: mockSubjectInfo } as never)
      renderWithClient(<TriplesBrowserPage />)

      await waitFor(() => {
        expect(screen.getByText('order:FM-1001')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('order:FM-1001'))

      await waitFor(() => {
        expect(screen.getByText('Delete Subject')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Delete Subject'))

      await waitFor(() => {
        expect(screen.getByText(/delete.*and all its triples/i)).toBeInTheDocument()
      })
    })

    it('calls deleteSubject API when confirmed', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      vi.mocked(triplesApi.getSubject).mockResolvedValue({ data: mockSubjectInfo } as never)
      vi.mocked(triplesApi.deleteSubject).mockResolvedValue({ data: {} } as never)

      renderWithClient(<TriplesBrowserPage />)

      await waitFor(() => {
        expect(screen.getByText('order:FM-1001')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('order:FM-1001'))

      await waitFor(() => {
        expect(screen.getByText('Delete Subject')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Delete Subject'))

      await waitFor(() => {
        expect(screen.getByText('Delete All')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Delete All'))

      await waitFor(() => {
        expect(triplesApi.deleteSubject).toHaveBeenCalledWith('order:FM-1001')
      })
    })
  })

  describe('Subject Header Actions', () => {
    it('shows Add button in subject header', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      vi.mocked(triplesApi.getSubject).mockResolvedValue({ data: mockSubjectInfo } as never)
      renderWithClient(<TriplesBrowserPage />)

      await waitFor(() => {
        expect(screen.getByText('order:FM-1001')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('order:FM-1001'))

      await waitFor(() => {
        const addButton = screen.getByTitle('Add triple to this subject')
        expect(addButton).toBeInTheDocument()
      })
    })

    it('opens create modal with subject pre-filled when Add button is clicked', async () => {
      vi.mocked(triplesApi.listSubjects).mockResolvedValue({ data: mockSubjects } as never)
      vi.mocked(triplesApi.getSubject).mockResolvedValue({ data: mockSubjectInfo } as never)
      renderWithClient(<TriplesBrowserPage />)

      await waitFor(() => {
        expect(screen.getByText('order:FM-1001')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('order:FM-1001'))

      await waitFor(() => {
        expect(screen.getByText('order_status')).toBeInTheDocument()
      })

      const addButton = screen.getByTitle('Add triple to this subject')
      fireEvent.click(addButton)

      await waitFor(() => {
        expect(screen.getByText('Create Triple')).toBeInTheDocument()
      })
    })
  })
})
