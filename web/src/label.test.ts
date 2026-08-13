import { describe, it, expect } from 'vitest'
import {
  label,
  brand,
  navItems,
  entity,
  Entity,
  Entities,
  enumLabel,
  enumOptions,
  aliasColumn,
  aliasView,
  aliasPredicate,
  pageText,
  copyText,
  placeholder,
  predicateSample,
  navLabel,
} from './label'

// These lock the contract every component relies on. The committed artifact is
// the resolved freshmart label, so the expected values here are freshmart's.
describe('label module', () => {
  it('loads the committed freshmart artifact', () => {
    expect(label.label).toBe('freshmart')
    expect(brand.name).toBe('FreshMart')
    expect(brand.tagline).toBe('Digital Twin Admin')
  })

  it('exposes every nav route the app renders', () => {
    const paths = navItems.map((n) => n.path)
    expect(paths).toEqual([
      '/', '/vector-search', '/orders', '/couriers', '/metrics',
      '/stores', '/ontology', '/triples', '/bundling', '/settings',
    ])
    expect(navLabel('/orders')).toBe('Orders')
  })

  it('resolves entity words in every form', () => {
    expect(entity('order')).toBe('order')
    expect(entity('order', 'many')).toBe('orders')
    expect(Entity('order')).toBe('Order')
    expect(Entities('courier')).toBe('Couriers')
  })

  it('falls back to the lowercase form when a title form is absent', () => {
    // zone defines title/title_many, so use a key that may not: the helper must
    // never return undefined for a defined entity.
    expect(typeof entity('store', 'title')).toBe('string')
    expect(entity('store', 'title')).not.toContain('⟪')
  })

  it('maps enum values to display labels and passes unknown values through', () => {
    expect(enumLabel('order_status', 'OUT_FOR_DELIVERY')).toBe('Out for Delivery')
    expect(enumLabel('zone', 'BK')).toBe('Brooklyn')
    // Live data must never be hidden just because a label forgot a key.
    expect(enumLabel('order_status', 'SOMETHING_NEW')).toBe('SOMETHING_NEW')
    expect(enumLabel('order_status', null)).toBe('')
    expect(enumLabel('order_status', undefined)).toBe('')
  })

  it('builds dropdown options preserving the internal value', () => {
    const zones = enumOptions('zone')
    expect(zones).toContainEqual({ value: 'MAN', label: 'Manhattan' })
    expect(zones.map((z) => z.value).sort()).toEqual(['BK', 'BX', 'MAN', 'QNS', 'SI'])
  })

  it('aliases identifiers for display only, identity by default', () => {
    // freshmart ships identity maps -- the wire format is never rewritten.
    expect(aliasColumn('store_zone')).toBe('store_zone')
    expect(aliasView('orders_with_lines_mv')).toBe('orders_with_lines_mv')
    expect(aliasPredicate('order_status')).toBe('order_status')
    // Unknown identifiers always pass through untouched.
    expect(aliasColumn('a_column_no_label_knows')).toBe('a_column_no_label_knows')
  })

  it('provides page, copy, and placeholder strings', () => {
    expect(pageText('orders', 'title')).toBe('Orders Dashboard')
    expect(copyText('triples', 'heading')).toBe('Agent Writes and Memories')
    expect(placeholder('subject')).toBe('order:FM-1001')
    expect(predicateSample('order_status')).toBe('DELIVERED')
    expect(predicateSample('a_predicate_with_no_sample')).toBe('value')
  })

  it('marks missing keys loudly instead of rendering an empty string', () => {
    // A silent '' is how half-translated screens ship; the marker is visible
    // in tests and in the UI.
    expect(pageText('orders', 'no_such_field')).toBe('⟪pages.orders.no_such_field⟫')
    expect(copyText('no_such_block', 'x')).toBe('⟪copy.no_such_block.x⟫')
  })

  it('carries no server-only sections into the browser bundle', () => {
    // The 760-row seed catalog, synonym list, and system prompt are stripped by
    // the resolver's web projection -- shipping them would bloat the bundle.
    const raw = label as unknown as Record<string, unknown>
    expect(raw.seed).toBeUndefined()
    expect(raw.search).toBeUndefined()
    // The type does not even declare system_prompt -- assert the runtime shape
    // matches, so a resolver change that started shipping it would fail here.
    expect((label.agent as Record<string, unknown>).system_prompt).toBeUndefined()
    expect(label.agent.persona).toBe('Operations Assistant')
  })
})
