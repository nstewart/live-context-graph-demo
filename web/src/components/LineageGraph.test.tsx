import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LineageGraph, buildLineageLayout } from './LineageGraph'

// ReactFlow measures its container; jsdom has no layout engine.
beforeAll(() => {
  global.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as never
  // ReactFlow warns unless the pane reports a non-zero size
  Object.defineProperties(HTMLElement.prototype, {
    offsetWidth: { get: () => 1200, configurable: true },
    offsetHeight: { get: () => 800, configurable: true },
  })
})

describe('LineageGraph scenarios', () => {
  it('fans writes out to per-system sources in the default materialize scenario', () => {
    render(<LineageGraph scenario="materialize" />)

    expect(screen.getByText('Customers DB')).toBeInTheDocument()
    expect(screen.getByText('Operations DB')).toBeInTheDocument()
    expect(screen.getByText('Courier Stream')).toBeInTheDocument()
    expect(screen.queryByText('Agent Writes & Memories')).not.toBeInTheDocument()
  })

  it('routes writes through a single triple store in materialize_triples', () => {
    render(<LineageGraph scenario="materialize_triples" />)

    // The agent write store replaces the three per-system sources...
    expect(screen.getByText('Agent Writes & Memories')).toBeInTheDocument()
    expect(screen.queryByText('Customers DB')).not.toBeInTheDocument()
    expect(screen.queryByText('Operations DB')).not.toBeInTheDocument()
    expect(screen.queryByText('Courier Stream')).not.toBeInTheDocument()

    // ...while the medallion stack is unchanged from the materialize scenario
    expect(screen.getByText('orders_with_lines_mv')).toBeInTheDocument()
    expect(screen.getByText('store_inventory_mv')).toBeInTheDocument()
    expect(screen.getByText('dynamic_pricing_mv')).toBeInTheDocument()
  })

  it('keeps the postgres scenario on its own triples labelling', () => {
    render(<LineageGraph scenario="postgres" />)

    expect(screen.getByText('triples')).toBeInTheDocument()
    expect(screen.queryByText('Agent Writes & Memories')).not.toBeInTheDocument()
  })

  it('serves a vector DB instead of generic destinations in materialize_triples', () => {
    render(<LineageGraph scenario="materialize_triples" />)

    // Swim-lane band is relabelled, and the image carries the node itself
    expect(screen.getByText('Vector DB')).toBeInTheDocument()
    expect(screen.getByAltText('Vector DB')).toBeInTheDocument()
    expect(screen.queryByText('Destinations')).not.toBeInTheDocument()
    expect(screen.queryByText('Iceberg')).not.toBeInTheDocument()
  })

  it('keeps the generic destinations column in the default materialize scenario', () => {
    render(<LineageGraph scenario="materialize" />)

    expect(screen.getByText('Destinations')).toBeInTheDocument()
    expect(screen.getByText('Iceberg')).toBeInTheDocument()
    expect(screen.queryByText('Vector DB')).not.toBeInTheDocument()
    expect(screen.queryByAltText('Vector DB')).not.toBeInTheDocument()
  })

  it('draws the two-step RAG retrieval loop in materialize_triples', () => {
    const { edges } = buildLineageLayout('materialize_triples')
    const byId = Object.fromEntries(edges.map((e) => [e.id, e]))

    // Step 1: candidates come back from the vector store to the agent
    const recall = byId['e-vectordb-agent']
    expect(recall.source).toBe('destination_systems_box')
    expect(recall.target).toBe('__agent__')
    expect(recall.label).toBe('\u2460 kNN recall')
    // Top-to-top routing is what keeps it clear of the MCP node
    expect(recall.type).toBe('smoothstep')
    expect(recall.sourceHandle).toBe('top')
    expect(recall.targetHandle).toBe('top-in')

    // Step 2: the same line that used to say "Observe" now names the enrichment
    expect(byId['e-agent-mcp'].label).toBe('\u2461 Features from MZ + rerank')

    // Act is deliberately untouched
    expect(byId['e-agent-src'].label).toBe('Act')
  })

  it('keeps the plain observe/act loop in the default materialize scenario', () => {
    const { edges } = buildLineageLayout('materialize')
    const byId = Object.fromEntries(edges.map((e) => [e.id, e]))

    expect(byId['e-agent-mcp'].label).toBe('Observe')
    expect(byId['e-agent-src'].label).toBe('Act')
    expect(byId['e-vectordb-agent']).toBeUndefined()
  })

  it('keeps the vector store fed by the live medallion views', () => {
    const { edges } = buildLineageLayout('materialize_triples')
    const intoVectorDb = edges
      .filter((e) => e.target === 'destination_systems_box')
      .map((e) => e.source)

    expect(intoVectorDb).toEqual(
      expect.arrayContaining([
        'store_inventory_mv',
        'orders_with_lines_mv',
        'inventory_items_with_dynamic_pricing_mv',
      ])
    )
  })

  it('reports the clicked node id', async () => {
    const onNodeClick = vi.fn()
    render(<LineageGraph scenario="materialize_triples" onNodeClick={onNodeClick} />)

    screen.getByText('orders_with_lines_mv').click()
    expect(onNodeClick).toHaveBeenCalledWith('orders_with_lines_mv')
  })
})
