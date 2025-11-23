import { vi } from 'vitest'

// Sample mock data for testing
export const mockOntologyClasses = [
  {
    id: 1,
    class_name: 'Customer',
    prefix: 'customer',
    description: 'A customer entity',
    parent_class_id: null,
    created_at: '2024-01-15T10:00:00Z',
    updated_at: '2024-01-15T10:00:00Z',
  },
  {
    id: 2,
    class_name: 'Order',
    prefix: 'order',
    description: 'An order entity',
    parent_class_id: null,
    created_at: '2024-01-15T10:00:00Z',
    updated_at: '2024-01-15T10:00:00Z',
  },
  {
    id: 3,
    class_name: 'Store',
    prefix: 'store',
    description: 'A store location',
    parent_class_id: null,
    created_at: '2024-01-15T10:00:00Z',
    updated_at: '2024-01-15T10:00:00Z',
  },
]

export const mockOntologyProperties = [
  {
    id: 1,
    prop_name: 'customer_name',
    domain_class_id: 1,
    range_kind: 'string',
    range_class_id: null,
    is_multi_valued: false,
    is_required: true,
    description: 'Customer full name',
    domain_class_name: 'Customer',
    range_class_name: null,
    created_at: '2024-01-15T10:00:00Z',
    updated_at: '2024-01-15T10:00:00Z',
  },
  {
    id: 2,
    prop_name: 'order_status',
    domain_class_id: 2,
    range_kind: 'string',
    range_class_id: null,
    is_multi_valued: false,
    is_required: true,
    description: 'Order status',
    domain_class_name: 'Order',
    range_class_name: null,
    created_at: '2024-01-15T10:00:00Z',
    updated_at: '2024-01-15T10:00:00Z',
  },
]

export const mockOrders = [
  {
    order_id: 'order:FM-1001',
    order_number: 'FM-1001',
    order_status: 'OUT_FOR_DELIVERY',
    store_id: 'store:BK-01',
    customer_id: 'customer:101',
    delivery_window_start: '2024-01-15T14:00:00',
    delivery_window_end: '2024-01-15T16:00:00',
    order_total_amount: 45.99,
    customer_name: 'Alex Thompson',
    customer_address: '123 Main St, Brooklyn',
    store_name: 'FreshMart Brooklyn Heights',
    store_zone: 'Brooklyn',
    assigned_courier_id: 'courier:C-101',
    delivery_task_status: 'IN_PROGRESS',
  },
  {
    order_id: 'order:FM-1002',
    order_number: 'FM-1002',
    order_status: 'DELIVERED',
    store_id: 'store:MH-01',
    customer_id: 'customer:102',
    delivery_window_start: '2024-01-15T10:00:00',
    delivery_window_end: '2024-01-15T12:00:00',
    order_total_amount: 32.50,
    customer_name: 'Jordan Lee',
    customer_address: '456 Oak Ave, Manhattan',
    store_name: 'FreshMart Manhattan',
    store_zone: 'Manhattan',
    assigned_courier_id: 'courier:C-102',
    delivery_task_status: 'COMPLETED',
  },
]

export const mockStores = [
  {
    store_id: 'store:BK-01',
    store_name: 'FreshMart Brooklyn Heights',
    store_address: '100 Court St, Brooklyn',
    store_zone: 'Brooklyn',
    store_status: 'OPEN',
    store_capacity_orders_per_hour: 50,
    inventory_items: [],
  },
  {
    store_id: 'store:MH-01',
    store_name: 'FreshMart Manhattan',
    store_address: '200 Broadway, Manhattan',
    store_zone: 'Manhattan',
    store_status: 'OPEN',
    store_capacity_orders_per_hour: 75,
    inventory_items: [],
  },
]

export const mockCouriers = [
  {
    courier_id: 'courier:C-101',
    courier_name: 'Mike Johnson',
    home_store_id: 'store:BK-01',
    vehicle_type: 'bike',
    courier_status: 'ON_DELIVERY',
    tasks: [
      {
        task_id: 'task:T-1001',
        task_status: 'IN_PROGRESS',
        order_id: 'order:FM-1001',
        eta: '2024-01-15T15:30:00',
        route_sequence: 1,
      },
    ],
  },
  {
    courier_id: 'courier:C-102',
    courier_name: 'Sarah Davis',
    home_store_id: 'store:MH-01',
    vehicle_type: 'bike',
    courier_status: 'AVAILABLE',
    tasks: [],
  },
]

export const mockSubjectInfo = {
  subject_id: 'customer:101',
  class_name: 'Customer',
  class_id: 1,
  triples: [
    {
      id: 1,
      subject_id: 'customer:101',
      predicate: 'customer_name',
      object_value: 'Alex Thompson',
      object_type: 'string',
      created_at: '2024-01-15T10:00:00Z',
      updated_at: '2024-01-15T10:00:00Z',
    },
    {
      id: 2,
      subject_id: 'customer:101',
      predicate: 'customer_email',
      object_value: 'alex@example.com',
      object_type: 'string',
      created_at: '2024-01-15T10:00:00Z',
      updated_at: '2024-01-15T10:00:00Z',
    },
  ],
}

// Mock store with inventory for CRUD testing
export const mockStoreWithInventory = {
  store_id: 'store:BK-01',
  store_name: 'FreshMart Brooklyn Heights',
  store_address: '100 Court St, Brooklyn',
  store_zone: 'Brooklyn',
  store_status: 'OPEN',
  store_capacity_orders_per_hour: 50,
  inventory_items: [
    {
      inventory_id: 'inventory:INV-BK01-001',
      store_id: 'store:BK-01',
      product_id: 'product:MILK-001',
      stock_level: 50,
      replenishment_eta: null,
    },
    {
      inventory_id: 'inventory:INV-BK01-002',
      store_id: 'store:BK-01',
      product_id: 'product:BREAD-001',
      stock_level: 5,
      replenishment_eta: '2024-01-16T10:00:00Z',
    },
  ],
}

// Mock subject info for Order (for update operations)
export const mockOrderSubjectInfo = {
  subject_id: 'order:FM-1001',
  class_name: 'Order',
  class_id: 2,
  triples: [
    {
      id: 100,
      subject_id: 'order:FM-1001',
      predicate: 'order_number',
      object_value: 'FM-1001',
      object_type: 'string',
      created_at: '2024-01-15T10:00:00Z',
      updated_at: '2024-01-15T10:00:00Z',
    },
    {
      id: 101,
      subject_id: 'order:FM-1001',
      predicate: 'order_status',
      object_value: 'OUT_FOR_DELIVERY',
      object_type: 'string',
      created_at: '2024-01-15T10:00:00Z',
      updated_at: '2024-01-15T10:00:00Z',
    },
    {
      id: 102,
      subject_id: 'order:FM-1001',
      predicate: 'order_store',
      object_value: 'store:BK-01',
      object_type: 'entity_ref',
      created_at: '2024-01-15T10:00:00Z',
      updated_at: '2024-01-15T10:00:00Z',
    },
  ],
}

// Mock subject info for Store
export const mockStoreSubjectInfo = {
  subject_id: 'store:BK-01',
  class_name: 'Store',
  class_id: 3,
  triples: [
    {
      id: 200,
      subject_id: 'store:BK-01',
      predicate: 'store_name',
      object_value: 'FreshMart Brooklyn Heights',
      object_type: 'string',
      created_at: '2024-01-15T10:00:00Z',
      updated_at: '2024-01-15T10:00:00Z',
    },
    {
      id: 201,
      subject_id: 'store:BK-01',
      predicate: 'store_status',
      object_value: 'OPEN',
      object_type: 'string',
      created_at: '2024-01-15T10:00:00Z',
      updated_at: '2024-01-15T10:00:00Z',
    },
  ],
}

// Mock subject info for Courier
export const mockCourierSubjectInfo = {
  subject_id: 'courier:C-101',
  class_name: 'Courier',
  class_id: 4,
  triples: [
    {
      id: 300,
      subject_id: 'courier:C-101',
      predicate: 'courier_name',
      object_value: 'Mike Johnson',
      object_type: 'string',
      created_at: '2024-01-15T10:00:00Z',
      updated_at: '2024-01-15T10:00:00Z',
    },
    {
      id: 301,
      subject_id: 'courier:C-101',
      predicate: 'courier_status',
      object_value: 'ON_DELIVERY',
      object_type: 'string',
      created_at: '2024-01-15T10:00:00Z',
      updated_at: '2024-01-15T10:00:00Z',
    },
  ],
}

// Mock axios client
export const createMockApiClient = () => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  patch: vi.fn(),
  delete: vi.fn(),
})
