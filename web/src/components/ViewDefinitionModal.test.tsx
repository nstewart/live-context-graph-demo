import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { ViewDefinitionModal, MZ_CONSOLE_URL } from './ViewDefinitionModal'

const definition = (over = {}) => ({
  view_name: 'orders_with_lines_mv',
  object_type: 'materialized_view',
  sql: 'CREATE MATERIALIZED VIEW orders_with_lines_mv AS SELECT 1',
  ...over,
})

const writeText = vi.fn(() => Promise.resolve())

beforeEach(() => {
  vi.clearAllMocks()
  Object.assign(navigator, { clipboard: { writeText } })
})

describe('ViewDefinitionModal', () => {
  it('renders nothing until a node is selected', () => {
    const { container } = render(
      <ViewDefinitionModal viewName={null} definition={null} isLoading={false} onClose={() => {}} />
    )
    expect(container).toBeEmptyDOMElement()
  })

  it('copies the SHOW command for the selected object', async () => {
    render(
      <ViewDefinitionModal
        viewName="orders_with_lines_mv"
        definition={definition()}
        isLoading={false}
        onClose={() => {}}
      />
    )

    screen.getByText('Copy SHOW').click()

    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(
        'SHOW CREATE MATERIALIZED VIEW orders_with_lines_mv;'
      )
    )
    // Confirms back to the user so a demo click isn't a silent no-op
    await waitFor(() => expect(screen.getByText('Copied')).toBeInTheDocument())
  })

  it('uses the plain VIEW keyword for a non-materialized object', async () => {
    render(
      <ViewDefinitionModal
        viewName="stores_flat"
        definition={definition({ view_name: 'stores_flat', object_type: 'view' })}
        isLoading={false}
        onClose={() => {}}
      />
    )

    screen.getByText('Copy SHOW').click()
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith('SHOW CREATE VIEW stores_flat;')
    )
  })

  it('copies a command even while the definition is still loading', async () => {
    // object_type is unknown until the fetch lands; VIEW is the safe default
    render(
      <ViewDefinitionModal
        viewName="stores_flat"
        definition={null}
        isLoading={true}
        onClose={() => {}}
      />
    )

    screen.getByText('Copy SHOW').click()
    await waitFor(() =>
      expect(writeText).toHaveBeenCalledWith('SHOW CREATE VIEW stores_flat;')
    )
  })

  it('links out to the Materialize console SQL shell', () => {
    render(
      <ViewDefinitionModal
        viewName="orders_with_lines_mv"
        definition={definition()}
        isLoading={false}
        onClose={() => {}}
      />
    )

    const link = screen.getByText('SQL Shell').closest('a')
    expect(link).toHaveAttribute('href', MZ_CONSOLE_URL)
    expect(link).toHaveAttribute('target', '_blank')
    // Opening a new tab without this leaks window.opener to the console origin
    expect(link).toHaveAttribute('rel', 'noopener noreferrer')
  })

  it('stays usable when the clipboard is unavailable', async () => {
    writeText.mockRejectedValueOnce(new Error('blocked on http'))
    const error = vi.spyOn(console, 'error').mockImplementation(() => {})

    render(
      <ViewDefinitionModal
        viewName="stores_flat"
        definition={definition({ object_type: 'view' })}
        isLoading={false}
        onClose={() => {}}
      />
    )

    screen.getByText('Copy SHOW').click()
    await waitFor(() => expect(error).toHaveBeenCalled())
    // No false confirmation, and the SQL is still on screen to read
    expect(screen.queryByText('Copied')).not.toBeInTheDocument()
    expect(screen.getByText('Copy SHOW')).toBeInTheDocument()
    error.mockRestore()
  })

  it('drops the copied confirmation when a different node is opened', async () => {
    const { rerender } = render(
      <ViewDefinitionModal
        viewName="stores_flat"
        definition={definition({ object_type: 'view' })}
        isLoading={false}
        onClose={() => {}}
      />
    )

    screen.getByText('Copy SHOW').click()
    await waitFor(() => expect(screen.getByText('Copied')).toBeInTheDocument())

    rerender(
      <ViewDefinitionModal
        viewName="products_flat"
        definition={definition({ view_name: 'products_flat', object_type: 'view' })}
        isLoading={false}
        onClose={() => {}}
      />
    )

    expect(screen.queryByText('Copied')).not.toBeInTheDocument()
  })
})
