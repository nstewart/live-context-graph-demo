import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import OntologyPropertiesPage from './OntologyPropertiesPage'

// Mock the API client
vi.mock('../api/client', () => ({
  ontologyApi: {
    listProperties: vi.fn(),
    listClasses: vi.fn(),
    createProperty: vi.fn(),
    updateProperty: vi.fn(),
    deleteProperty: vi.fn(),
  },
}))

import { ontologyApi } from '../api/client'

const mockClasses = [
  { id: 1, class_name: 'Order', prefix: 'order', description: 'Customer orders', parent_class_id: null, created_at: '', updated_at: '' },
  { id: 2, class_name: 'Store', prefix: 'store', description: 'Stores', parent_class_id: null, created_at: '', updated_at: '' },
  { id: 3, class_name: 'Customer', prefix: 'customer', description: 'Customers', parent_class_id: null, created_at: '', updated_at: '' },
]

const mockProperties = [
  {
    id: 1,
    prop_name: 'order_status',
    domain_class_id: 1,
    range_kind: 'string',
    range_class_id: null,
    is_multi_valued: false,
    is_required: true,
    description: 'Order status',
    domain_class_name: 'Order',
    range_class_name: null,
    created_at: '',
    updated_at: '',
  },
  {
    id: 2,
    prop_name: 'order_store',
    domain_class_id: 1,
    range_kind: 'entity_ref',
    range_class_id: 2,
    is_multi_valued: false,
    is_required: true,
    description: 'Store for order',
    domain_class_name: 'Order',
    range_class_name: 'Store',
    created_at: '',
    updated_at: '',
  },
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

describe('OntologyPropertiesPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(ontologyApi.listClasses).mockResolvedValue({ data: mockClasses } as never)
  })

  describe('Rendering', () => {
    it('shows loading state initially', () => {
      vi.mocked(ontologyApi.listProperties).mockReturnValue(new Promise(() => {}))
      renderWithClient(<OntologyPropertiesPage />)
      expect(screen.getByText('Loading...')).toBeInTheDocument()
    })

    it('renders properties when loaded', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: mockProperties } as never)
      renderWithClient(<OntologyPropertiesPage />)

      await waitFor(() => {
        expect(screen.getByText('order_status')).toBeInTheDocument()
      })
      expect(screen.getByText('order_store')).toBeInTheDocument()
    })

    it('shows error state when API fails', async () => {
      vi.mocked(ontologyApi.listProperties).mockRejectedValue(new Error('API Error'))
      renderWithClient(<OntologyPropertiesPage />)

      await waitFor(() => {
        expect(screen.getByText('Error loading properties')).toBeInTheDocument()
      })
    })

    it('displays page title and description', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: [] } as never)
      renderWithClient(<OntologyPropertiesPage />)

      expect(screen.getByText('Ontology Properties')).toBeInTheDocument()
      expect(screen.getByText(/Define relationships and attributes/)).toBeInTheDocument()
    })

    it('shows Add Property button', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: [] } as never)
      renderWithClient(<OntologyPropertiesPage />)

      expect(screen.getByText('Add Property')).toBeInTheDocument()
    })
  })

  describe('Create Property Modal', () => {
    it('opens create modal when Add Property button is clicked', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: [] } as never)
      renderWithClient(<OntologyPropertiesPage />)

      fireEvent.click(screen.getByText('Add Property'))

      await waitFor(() => {
        expect(screen.getByText('Create Property')).toBeInTheDocument()
      })
    })

    it('closes modal when Cancel is clicked', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: [] } as never)
      renderWithClient(<OntologyPropertiesPage />)

      fireEvent.click(screen.getByText('Add Property'))
      await waitFor(() => {
        expect(screen.getByText('Create Property')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Cancel'))

      await waitFor(() => {
        expect(screen.queryByText('Create Property')).not.toBeInTheDocument()
      })
    })

    it('has required form fields', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: [] } as never)
      renderWithClient(<OntologyPropertiesPage />)

      fireEvent.click(screen.getByText('Add Property'))

      await waitFor(() => {
        expect(screen.getByText(/Property Name/)).toBeInTheDocument()
        expect(screen.getByText(/Domain Class/)).toBeInTheDocument()
        expect(screen.getByText(/Range Kind/)).toBeInTheDocument()
      })
    })

    it('shows Range Class dropdown when entity_ref is selected', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: [] } as never)
      renderWithClient(<OntologyPropertiesPage />)

      fireEvent.click(screen.getByText('Add Property'))

      await waitFor(() => {
        expect(screen.getByText('Create Property')).toBeInTheDocument()
      })

      // Select entity_ref as range kind
      const selects = screen.getAllByRole('combobox')
      const rangeKindSelect = selects[1] // Domain is first, Range Kind is second
      fireEvent.change(rangeKindSelect, { target: { value: 'entity_ref' } })

      await waitFor(() => {
        expect(screen.getByText(/Range Class/)).toBeInTheDocument()
      })
    })

    it('calls createProperty API when form is submitted', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: [] } as never)
      vi.mocked(ontologyApi.createProperty).mockResolvedValue({ data: mockProperties[0] } as never)

      renderWithClient(<OntologyPropertiesPage />)

      fireEvent.click(screen.getByText('Add Property'))

      await waitFor(() => {
        expect(screen.getByText('Create Property')).toBeInTheDocument()
      })

      // Wait for classes to load in dropdown
      await waitFor(() => {
        expect(screen.getByText('Order')).toBeInTheDocument()
      })

      // Fill out form
      fireEvent.change(screen.getByPlaceholderText('order_status'), { target: { value: 'test_property' } })

      // Select domain class (first dropdown)
      const selects = screen.getAllByRole('combobox')
      fireEvent.change(selects[0], { target: { value: '1' } })

      // Submit form by clicking Create button
      const allButtons = screen.getAllByRole('button')
      const createButton = allButtons.find(btn => btn.textContent === 'Create')
      fireEvent.click(createButton!)

      await waitFor(() => {
        expect(ontologyApi.createProperty).toHaveBeenCalled()
      })
    })
  })

  describe('Edit Property', () => {
    it('opens edit modal when edit button is clicked', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: mockProperties } as never)
      renderWithClient(<OntologyPropertiesPage />)

      await waitFor(() => {
        expect(screen.getByText('order_status')).toBeInTheDocument()
      })

      const editButtons = screen.getAllByTitle('Edit property')
      fireEvent.click(editButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Edit Property')).toBeInTheDocument()
      })
    })

    it('populates form with existing property data', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: mockProperties } as never)
      renderWithClient(<OntologyPropertiesPage />)

      await waitFor(() => {
        expect(screen.getByText('order_status')).toBeInTheDocument()
      })

      const editButtons = screen.getAllByTitle('Edit property')
      fireEvent.click(editButtons[0])

      await waitFor(() => {
        const propNameInput = screen.getByPlaceholderText('order_status') as HTMLInputElement
        expect(propNameInput.value).toBe('order_status')
      })
    })

    it('calls updateProperty API when edit form is submitted', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: mockProperties } as never)
      vi.mocked(ontologyApi.updateProperty).mockResolvedValue({ data: mockProperties[0] } as never)

      renderWithClient(<OntologyPropertiesPage />)

      await waitFor(() => {
        expect(screen.getByText('order_status')).toBeInTheDocument()
      })

      const editButtons = screen.getAllByTitle('Edit property')
      fireEvent.click(editButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Edit Property')).toBeInTheDocument()
      })

      fireEvent.click(screen.getByText('Update'))

      await waitFor(() => {
        expect(ontologyApi.updateProperty).toHaveBeenCalledWith(1, expect.any(Object))
      })
    })
  })

  describe('Delete Property', () => {
    it('shows delete confirmation modal when delete button is clicked', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: mockProperties } as never)
      renderWithClient(<OntologyPropertiesPage />)

      await waitFor(() => {
        expect(screen.getByText('order_status')).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByTitle('Delete property')
      fireEvent.click(deleteButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Delete Property')).toBeInTheDocument()
        expect(screen.getByText(/Are you sure you want to delete/)).toBeInTheDocument()
      })
    })

    it('cancels delete when Cancel is clicked', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: mockProperties } as never)
      renderWithClient(<OntologyPropertiesPage />)

      await waitFor(() => {
        expect(screen.getByText('order_status')).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByTitle('Delete property')
      fireEvent.click(deleteButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Delete Property')).toBeInTheDocument()
      })

      const cancelButtons = screen.getAllByText('Cancel')
      fireEvent.click(cancelButtons[cancelButtons.length - 1])

      await waitFor(() => {
        expect(screen.queryByText('Delete Property')).not.toBeInTheDocument()
      })
    })

    it('calls deleteProperty API when delete is confirmed', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: mockProperties } as never)
      vi.mocked(ontologyApi.deleteProperty).mockResolvedValue({ data: {} } as never)

      renderWithClient(<OntologyPropertiesPage />)

      await waitFor(() => {
        expect(screen.getByText('order_status')).toBeInTheDocument()
      })

      const deleteButtons = screen.getAllByTitle('Delete property')
      fireEvent.click(deleteButtons[0])

      await waitFor(() => {
        expect(screen.getByText('Delete Property')).toBeInTheDocument()
      })

      const allButtons = screen.getAllByRole('button')
      const deleteConfirmButton = allButtons.find(btn => btn.textContent === 'Delete')
      fireEvent.click(deleteConfirmButton!)

      await waitFor(() => {
        expect(ontologyApi.deleteProperty).toHaveBeenCalledWith(1)
      })
    })
  })

  describe('Property Table Display', () => {
    it('displays property name', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: mockProperties } as never)
      renderWithClient(<OntologyPropertiesPage />)

      await waitFor(() => {
        expect(screen.getByText('order_status')).toBeInTheDocument()
        expect(screen.getByText('order_store')).toBeInTheDocument()
      })
    })

    it('displays domain class', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: mockProperties } as never)
      renderWithClient(<OntologyPropertiesPage />)

      await waitFor(() => {
        const orderBadges = screen.getAllByText('Order')
        expect(orderBadges.length).toBeGreaterThan(0)
      })
    })

    it('displays range class for entity_ref properties', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: mockProperties } as never)
      renderWithClient(<OntologyPropertiesPage />)

      await waitFor(() => {
        expect(screen.getByText('Store')).toBeInTheDocument()
      })
    })

    it('displays range kind for non-entity properties', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: mockProperties } as never)
      renderWithClient(<OntologyPropertiesPage />)

      await waitFor(() => {
        expect(screen.getByText('string')).toBeInTheDocument()
      })
    })

    it('displays required flag', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: mockProperties } as never)
      renderWithClient(<OntologyPropertiesPage />)

      await waitFor(() => {
        const requiredBadges = screen.getAllByText('required')
        expect(requiredBadges.length).toBeGreaterThan(0)
      })
    })

    it('displays description', async () => {
      vi.mocked(ontologyApi.listProperties).mockResolvedValue({ data: mockProperties } as never)
      renderWithClient(<OntologyPropertiesPage />)

      await waitFor(() => {
        expect(screen.getByText('Order status')).toBeInTheDocument()
      })
    })
  })
})
