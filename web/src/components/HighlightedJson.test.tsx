import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { HighlightedJson } from './HighlightedJson'

describe('HighlightedJson', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  describe('Basic Rendering', () => {
    it('renders simple JSON object', () => {
      const data = { name: 'John', age: 30 }
      render(<HighlightedJson data={data} />)

      expect(screen.getByText(/"name"/)).toBeInTheDocument()
      expect(screen.getByText(/"John"/)).toBeInTheDocument()
      expect(screen.getByText(/"age"/)).toBeInTheDocument()
      expect(screen.getByText(/30/)).toBeInTheDocument()
    })

    it('renders nested objects', () => {
      const data = {
        user: {
          name: 'John',
          address: {
            city: 'NYC',
          },
        },
      }
      render(<HighlightedJson data={data} />)

      expect(screen.getByText(/"user"/)).toBeInTheDocument()
      expect(screen.getByText(/"name"/)).toBeInTheDocument()
      expect(screen.getByText(/"address"/)).toBeInTheDocument()
      expect(screen.getByText(/"city"/)).toBeInTheDocument()
      expect(screen.getByText(/"NYC"/)).toBeInTheDocument()
    })

    it('renders arrays', () => {
      const data = { items: ['apple', 'banana', 'orange'] }
      render(<HighlightedJson data={data} />)

      expect(screen.getByText(/"items"/)).toBeInTheDocument()
      expect(screen.getByText(/"apple"/)).toBeInTheDocument()
      expect(screen.getByText(/"banana"/)).toBeInTheDocument()
      expect(screen.getByText(/"orange"/)).toBeInTheDocument()
    })

    it('renders boolean values', () => {
      const data = { isActive: true, isDeleted: false }
      render(<HighlightedJson data={data} />)

      expect(screen.getByText(/true/)).toBeInTheDocument()
      expect(screen.getByText(/false/)).toBeInTheDocument()
    })

    it('renders null values', () => {
      const data = { value: null }
      render(<HighlightedJson data={data} />)

      expect(screen.getByText(/null/)).toBeInTheDocument()
    })

    it('renders numbers', () => {
      const data = { count: 42, price: 19.99, negative: -10 }
      render(<HighlightedJson data={data} />)

      expect(screen.getByText(/42/)).toBeInTheDocument()
      expect(screen.getByText(/19.99/)).toBeInTheDocument()
      expect(screen.getByText(/-10/)).toBeInTheDocument()
    })

    it('renders empty objects', () => {
      const data = { empty: {} }
      const { container } = render(<HighlightedJson data={data} />)

      expect(container.textContent).toContain('{}')
    })

    it('renders empty arrays', () => {
      const data = { empty: [] }
      const { container } = render(<HighlightedJson data={data} />)

      expect(container.textContent).toContain('[]')
    })
  })

  describe('Change Detection', () => {
    it('does not highlight on initial render', () => {
      const data = { status: 'PENDING' }
      const { container } = render(<HighlightedJson data={data} />)

      // Check that no highlight classes are present
      expect(container.querySelector('.animate-pulse')).not.toBeInTheDocument()
    })

    it('highlights changed values', async () => {
      const { rerender, container } = render(<HighlightedJson data={{ status: 'PENDING' }} />)

      // Update data
      rerender(<HighlightedJson data={{ status: 'COMPLETED' }} />)

      await waitFor(() => {
        // Check for highlight class
        expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
      })
    })

    it('clears highlights after duration', async () => {
      const { rerender, container } = render(<HighlightedJson data={{ status: 'PENDING' }} />)

      rerender(<HighlightedJson data={{ status: 'COMPLETED' }} />)

      await waitFor(() => {
        expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
      })

      // Fast-forward time past HIGHLIGHT_DURATION (1500ms)
      vi.advanceTimersByTime(1600)

      await waitFor(() => {
        expect(container.querySelector('.animate-pulse')).not.toBeInTheDocument()
      })
    })

    it('highlights nested property changes', async () => {
      const initialData = { user: { name: 'John', age: 30 } }
      const updatedData = { user: { name: 'John', age: 31 } }

      const { rerender, container } = render(<HighlightedJson data={initialData} />)
      rerender(<HighlightedJson data={updatedData} />)

      await waitFor(() => {
        expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
      })
    })

    it('highlights array changes', async () => {
      const initialData = { items: ['a', 'b'] }
      const updatedData = { items: ['a', 'b', 'c'] }

      const { rerender, container } = render(<HighlightedJson data={initialData} />)
      rerender(<HighlightedJson data={updatedData} />)

      await waitFor(() => {
        expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
      })
    })

    it('highlights multiple changed properties', async () => {
      const initialData = { name: 'John', age: 30, city: 'NYC' }
      const updatedData = { name: 'Jane', age: 31, city: 'NYC' }

      const { rerender, container } = render(<HighlightedJson data={initialData} />)
      rerender(<HighlightedJson data={updatedData} />)

      await waitFor(() => {
        const highlights = container.querySelectorAll('.animate-pulse')
        expect(highlights.length).toBeGreaterThan(0)
      })
    })
  })

  describe('Tracking Key', () => {
    it('resets highlights when tracking key changes', async () => {
      const { rerender, container } = render(
        <HighlightedJson data={{ status: 'PENDING' }} trackingKey="order1" />
      )

      rerender(<HighlightedJson data={{ status: 'COMPLETED' }} trackingKey="order1" />)

      await waitFor(() => {
        expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
      })

      // Change tracking key (simulates viewing a different order)
      rerender(<HighlightedJson data={{ status: 'PENDING' }} trackingKey="order2" />)

      await waitFor(() => {
        expect(container.querySelector('.animate-pulse')).not.toBeInTheDocument()
      })
    })

    it('does not highlight when tracking key changes even if data is different', async () => {
      const { rerender, container } = render(
        <HighlightedJson data={{ status: 'PENDING' }} trackingKey="order1" />
      )

      // Change both tracking key and data
      rerender(<HighlightedJson data={{ status: 'COMPLETED' }} trackingKey="order2" />)

      await waitFor(() => {
        // Should not highlight because tracking key changed
        expect(container.querySelector('.animate-pulse')).not.toBeInTheDocument()
      })
    })
  })

  describe('Type Changes', () => {
    it('highlights when value type changes', async () => {
      const initialData = { value: 'text' }
      const updatedData = { value: 42 }

      const { rerender, container } = render(<HighlightedJson data={initialData} />)
      rerender(<HighlightedJson data={updatedData} />)

      await waitFor(() => {
        expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
      })
    })

    it('highlights when value changes from object to primitive', async () => {
      const initialData = { value: { nested: 'object' } }
      const updatedData = { value: 'string' }

      const { rerender, container } = render(<HighlightedJson data={initialData} />)
      rerender(<HighlightedJson data={updatedData} />)

      await waitFor(() => {
        expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
      })
    })

    it('highlights when null becomes a value', async () => {
      const initialData = { value: null }
      const updatedData = { value: 'something' }

      const { rerender, container } = render(<HighlightedJson data={initialData} />)
      rerender(<HighlightedJson data={updatedData} />)

      await waitFor(() => {
        expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
      })
    })
  })

  describe('Complex Nested Structures', () => {
    it('handles deeply nested changes', async () => {
      const initialData = {
        level1: {
          level2: {
            level3: {
              value: 'old',
            },
          },
        },
      }
      const updatedData = {
        level1: {
          level2: {
            level3: {
              value: 'new',
            },
          },
        },
      }

      const { rerender, container } = render(<HighlightedJson data={initialData} />)
      rerender(<HighlightedJson data={updatedData} />)

      await waitFor(() => {
        expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
      })
    })

    it('handles arrays of objects', async () => {
      const initialData = {
        users: [
          { id: 1, name: 'John' },
          { id: 2, name: 'Jane' },
        ],
      }
      const updatedData = {
        users: [
          { id: 1, name: 'John' },
          { id: 2, name: 'Janet' },
        ],
      }

      const { rerender, container } = render(<HighlightedJson data={initialData} />)
      rerender(<HighlightedJson data={updatedData} />)

      await waitFor(() => {
        expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
      })
    })
  })

  describe('Edge Cases', () => {
    it('handles empty data object', () => {
      const { container } = render(<HighlightedJson data={{}} />)
      expect(container.textContent).toContain('{}')
    })

    it('handles data with special characters in strings', () => {
      const data = { message: 'Hello "world"', path: 'a/b/c' }
      render(<HighlightedJson data={data} />)

      expect(screen.getByText(/"message"/)).toBeInTheDocument()
      expect(screen.getByText(/"path"/)).toBeInTheDocument()
    })

    it('handles very large numbers', () => {
      const data = { big: 9007199254740991 }
      render(<HighlightedJson data={data} />)

      expect(screen.getByText(/9007199254740991/)).toBeInTheDocument()
    })

    it('handles zero values', () => {
      const data = { count: 0, price: 0.0 }
      render(<HighlightedJson data={data} />)

      const zeros = screen.getAllByText(/^0$/)
      expect(zeros.length).toBeGreaterThan(0)
    })
  })
})
