import { describe, it, expect, vi } from 'vitest'
import {
  mockOntologyClasses,
  mockOntologyProperties,
  mockOrders,
  mockStores,
  mockCouriers,
  mockSubjectInfo,
} from '../test/mocks'

// Mock axios
vi.mock('axios', () => ({
  default: {
    create: vi.fn(() => ({
      get: vi.fn(),
      post: vi.fn(),
      put: vi.fn(),
      delete: vi.fn(),
    })),
  },
}))

describe('API Client Types', () => {
  it('OntologyClass has correct structure', () => {
    const cls = mockOntologyClasses[0]
    expect(cls).toHaveProperty('id')
    expect(cls).toHaveProperty('class_name')
    expect(cls).toHaveProperty('prefix')
    expect(cls).toHaveProperty('description')
    expect(cls).toHaveProperty('created_at')
    expect(cls).toHaveProperty('updated_at')
  })

  it('OntologyProperty has correct structure', () => {
    const prop = mockOntologyProperties[0]
    expect(prop).toHaveProperty('id')
    expect(prop).toHaveProperty('prop_name')
    expect(prop).toHaveProperty('domain_class_id')
    expect(prop).toHaveProperty('range_kind')
    expect(prop).toHaveProperty('is_multi_valued')
    expect(prop).toHaveProperty('is_required')
  })

  it('OrderFlat has correct structure', () => {
    const order = mockOrders[0]
    expect(order).toHaveProperty('order_id')
    expect(order).toHaveProperty('order_status')
    expect(order).toHaveProperty('customer_name')
    expect(order).toHaveProperty('store_name')
    expect(order).toHaveProperty('delivery_window_start')
  })

  it('StoreInfo has correct structure', () => {
    const store = mockStores[0]
    expect(store).toHaveProperty('store_id')
    expect(store).toHaveProperty('store_name')
    expect(store).toHaveProperty('store_zone')
    expect(store).toHaveProperty('inventory_items')
  })

  it('CourierSchedule has correct structure', () => {
    const courier = mockCouriers[0]
    expect(courier).toHaveProperty('courier_id')
    expect(courier).toHaveProperty('courier_name')
    expect(courier).toHaveProperty('courier_status')
    expect(courier).toHaveProperty('tasks')
    expect(Array.isArray(courier.tasks)).toBe(true)
  })

  it('SubjectInfo has correct structure', () => {
    expect(mockSubjectInfo).toHaveProperty('subject_id')
    expect(mockSubjectInfo).toHaveProperty('class_name')
    expect(mockSubjectInfo).toHaveProperty('triples')
    expect(Array.isArray(mockSubjectInfo.triples)).toBe(true)
  })
})

describe('Mock Data Validity', () => {
  it('Orders have valid status values', () => {
    const validStatuses = ['CREATED', 'PICKING', 'OUT_FOR_DELIVERY', 'DELIVERED', 'CANCELLED']
    for (const order of mockOrders) {
      expect(validStatuses).toContain(order.order_status)
    }
  })

  it('Couriers have valid status values', () => {
    const validStatuses = ['OFF_SHIFT', 'AVAILABLE', 'ON_DELIVERY']
    for (const courier of mockCouriers) {
      expect(validStatuses).toContain(courier.courier_status)
    }
  })

  it('Order IDs follow prefix:id pattern', () => {
    for (const order of mockOrders) {
      expect(order.order_id).toMatch(/^order:.+/)
    }
  })

  it('Store IDs follow prefix:id pattern', () => {
    for (const store of mockStores) {
      expect(store.store_id).toMatch(/^store:.+/)
    }
  })

  it('Courier IDs follow prefix:id pattern', () => {
    for (const courier of mockCouriers) {
      expect(courier.courier_id).toMatch(/^courier:.+/)
    }
  })

  it('Subject triples have consistent subject_id', () => {
    for (const triple of mockSubjectInfo.triples) {
      expect(triple.subject_id).toBe(mockSubjectInfo.subject_id)
    }
  })
})
