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

    // The write edge survives but sheds its label; see the sources-column test
    expect(byId['e-agent-src']).toBeTruthy()
    expect(byId['e-agent-src'].label).toBeUndefined()
  })

  it('keeps the plain observe/act loop in the default materialize scenario', () => {
    const { edges } = buildLineageLayout('materialize')
    const byId = Object.fromEntries(edges.map((e) => [e.id, e]))

    expect(byId['e-agent-mcp'].label).toBe('Observe')
    expect(byId['e-agent-src'].label).toBe('Act')  // still labelled on the home page
    expect(byId['e-vectordb-agent']).toBeUndefined()
  })

  it('feeds the vector store from the sink views, not the MVs upstream', () => {
    const { edges } = buildLineageLayout('materialize_triples')
    const intoVectorDb = edges
      .filter((e) => e.target === 'destination_systems_box')
      .map((e) => e.source)
      .sort()

    // One sink view per OpenSearch collection. store_inventory_mv and
    // orders_with_lines_mv reach search only by way of a sink, so they must not
    // be drawn as feeding it directly.
    expect(intoVectorDb).toEqual(['inventory_sink_v', 'orders_sink_v'])
  })

  it('puts the sink views in gold and dynamic pricing back in silver', () => {
    const { nodes } = buildLineageLayout('materialize_triples')
    const bandFor = (layer: string) => nodes.find((n) => n.id === `__band__${layer}`)

    // Both bands are drawn, and gold sits to the right of silver
    expect(bandFor('gold')).toBeTruthy()
    expect(bandFor('silver')).toBeTruthy()
    expect(bandFor('gold')!.position.x).toBeGreaterThan(bandFor('silver')!.position.x)

    const xOf = (id: string) => nodes.find((n) => n.id === id)!.position.x
    const goldLeft = bandFor('gold')!.position.x

    // The sink views are the only nodes in the gold column...
    expect(xOf('orders_sink_v')).toBeGreaterThanOrEqual(goldLeft)
    expect(xOf('inventory_sink_v')).toBeGreaterThanOrEqual(goldLeft)
    // ...and dynamic pricing has moved left of it, into silver
    expect(xOf('inventory_items_with_dynamic_pricing_mv')).toBeLessThan(goldLeft)
    expect(xOf('inventory_items_with_dynamic_pricing')).toBeLessThan(goldLeft)
  })

  it('keeps the medallion bands from overlapping', () => {
    const { nodes } = buildLineageLayout('materialize_triples')
    const span = (layer: string) => {
      const b = nodes.find((n) => n.id === `__band__${layer}`)!
      return [b.position.x, b.position.x + Number(b.style!.width)]
    }

    // dagre ranks the pricing chain one hop longer than the orders chain, which
    // would otherwise stretch silver across gold. Each band must end before the
    // next begins, or the swim lanes read as mush.
    const order = ['sources', 'bronze', 'silver', 'gold', 'destination_systems']
    for (let i = 0; i < order.length - 1; i++) {
      const [, end] = span(order[i])
      const [nextStart] = span(order[i + 1])
      expect(end).toBeLessThanOrEqual(nextStart)
    }
  })

  it('chains each silver MV into its own sink view', () => {
    const { edges } = buildLineageLayout('materialize_triples')
    const pairs = edges.map((e) => `${e.source}->${e.target}`)

    expect(pairs).toContain('orders_with_lines_mv->orders_sink_v')
    expect(pairs).toContain('inventory_items_with_dynamic_pricing_mv->inventory_sink_v')
  })

  it('drops the source systems box and writes straight into the sources column', () => {
    const { nodes, edges } = buildLineageLayout('materialize_triples')

    expect(nodes.find((n) => n.id === 'source_systems_box')).toBeUndefined()
    expect(nodes.find((n) => n.id === '__band__source_systems')).toBeUndefined()
    expect(edges.find((e) => e.id === 'e-src-triples')).toBeUndefined()

    // Act now lands on the triple store itself, entering from above
    const act = edges.find((e) => e.id === 'e-agent-src')!
    expect(act.source).toBe('__agent__')
    expect(act.target).toBe('triples')
    // Unlabelled here — the target node already reads "Agent Writes & Memories"
    expect(act.label).toBeUndefined()

    // The agent sits above the node, so the write arrives on the top edge
    const triples = nodes.find((n) => n.id === 'triples')!
    expect(triples.targetPosition).toBe('top')
    // Everything else still flows left-to-right
    expect(nodes.find((n) => n.id === 'orders_sink_v')!.targetPosition).toBe('left')
  })

  it('leaves the default materialize scenario structurally untouched', () => {
    const { nodes, edges } = buildLineageLayout('materialize')

    // Source systems box and its feeds survive
    expect(nodes.find((n) => n.id === 'source_systems_box')).toBeTruthy()
    expect(edges.find((e) => e.id === 'e-agent-src')!.target).toBe('source_systems_box')
    // Sink views are RAG-only
    expect(nodes.find((n) => n.id === 'orders_sink_v')).toBeUndefined()
    expect(nodes.find((n) => n.id === 'inventory_sink_v')).toBeUndefined()
    // And the destinations column keeps its original three feeds
    const intoDest = edges.filter((e) => e.target === 'destination_systems_box').map((e) => e.source)
    expect(intoDest).toHaveLength(3)
    expect(intoDest).toContain('inventory_items_with_dynamic_pricing_mv')
  })

  it('leaves the postgres query-offload scenario structurally untouched', () => {
    const { nodes } = buildLineageLayout('postgres')

    // Sink views are RAG-only. Postgres has no destination column for them to
    // feed, so their edges are filtered out — leaving them as orphans at dagre
    // rank 0 if the nodes come through, which drags the biz_logic band left
    // across "Base Tables".
    expect(nodes.find((n) => n.id === 'orders_sink_v')).toBeUndefined()
    expect(nodes.find((n) => n.id === 'inventory_sink_v')).toBeUndefined()

    const span = (layer: string) => {
      const b = nodes.find((n) => n.id === `__band__${layer}`)!
      return [b.position.x, b.position.x + Number(b.style!.width)]
    }
    const [, bronzeEnd] = span('bronze')
    const [bizStart] = span('biz_logic')
    expect(bronzeEnd).toBeLessThanOrEqual(bizStart)
  })

  it('reports the clicked node id', async () => {
    const onNodeClick = vi.fn()
    render(<LineageGraph scenario="materialize_triples" onNodeClick={onNodeClick} />)

    screen.getByText('orders_with_lines_mv').click()
    expect(onNodeClick).toHaveBeenCalledWith('orders_with_lines_mv')
  })
})
