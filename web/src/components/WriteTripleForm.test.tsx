import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { WriteTripleForm } from './WriteTripleForm'
import { queryStatsApi } from '../api/client'

vi.mock('lucide-react', () => ({
  Edit3: () => <div>Edit3</div>,
}))

vi.mock('../api/client', () => ({
  queryStatsApi: {
    writeTriple: vi.fn(),
  },
}))

const writeTriple = vi.mocked(queryStatsApi.writeTriple)

// Fill the form so the Write button becomes enabled, then click it.
const fillAndSubmit = (value = '5') => {
  fireEvent.change(screen.getByPlaceholderText('order:FM-1001'), {
    target: { value: 'order:FM-000503' },
  })
  // Predicate defaults to "quantity"; its placeholder is "5".
  const valueInput = screen.getByPlaceholderText('5')
  fireEvent.change(valueInput, { target: { value } })
  fireEvent.click(screen.getByRole('button', { name: 'Write' }))
}

describe('WriteTripleForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('disables the Write button until subject, predicate, and value are all set', () => {
    render(<WriteTripleForm />)
    const button = screen.getByRole('button', { name: 'Write' })
    expect(button).toBeDisabled()

    fireEvent.change(screen.getByPlaceholderText('order:FM-1001'), {
      target: { value: 'order:FM-000503' },
    })
    // Still disabled — value is empty.
    expect(button).toBeDisabled()

    fireEvent.change(screen.getByPlaceholderText('5'), { target: { value: '5' } })
    expect(button).toBeEnabled()
  })

  it('flashes a success message on a successful write', async () => {
    writeTriple.mockResolvedValueOnce({
      data: { mz_timestamp_lower_bound: 123 },
    } as never)

    render(<WriteTripleForm />)
    fillAndSubmit()

    await waitFor(() => {
      expect(screen.getByText(/^Written at/)).toBeInTheDocument()
    })
    expect(writeTriple).toHaveBeenCalledWith({
      subject_id: 'order:FM-000503',
      predicate: 'quantity',
      object_value: '5',
    })
  })

  it('surfaces the backend error detail instead of a generic failure', async () => {
    writeTriple.mockRejectedValueOnce({
      isAxiosError: true,
      message: 'Request failed with status code 404',
      response: { data: { detail: 'Triple not found: order:FM-000503 / quantity' } },
    })

    render(<WriteTripleForm />)
    fillAndSubmit()

    await waitFor(() => {
      expect(
        screen.getByText('Error: Triple not found: order:FM-000503 / quantity'),
      ).toBeInTheDocument()
    })
  })

  it('reports a timeout clearly when the request is aborted', async () => {
    writeTriple.mockRejectedValueOnce({
      isAxiosError: true,
      code: 'ECONNABORTED',
      message: 'timeout of 15000ms exceeded',
    })

    render(<WriteTripleForm />)
    fillAndSubmit()

    await waitFor(() => {
      expect(screen.getByText(/Timed out/)).toBeInTheDocument()
    })
  })
})
