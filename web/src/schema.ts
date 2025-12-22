/**
 * Zero Schema Definition
  * Maps to Zero server's replicated tables (Materialize views)
*/

import {
  createSchema,
  table,
  string,
  number,
  boolean,
  json,
  definePermissions,
  relationships,
  ANYONE_CAN,
  NOBODY_CAN,
} from '@rocicorp/zero'

// orders_search_source_mv - full order view with customer/store info
const orders_search_source_mv = table('orders_search_source_mv')
  .columns({
    order_id: string(),
    order_number: string().optional(),
    order_status: string().optional(),
    store_id: string().optional(),
    customer_id: string().optional(),
    delivery_window_start: string().optional(),
    delivery_window_end: string().optional(),
    order_total_amount: number().optional(),
    customer_name: string().optional(),
    customer_email: string().optional(),
    customer_address: string().optional(),
    store_name: string().optional(),
    store_zone: string().optional(),
    store_address: string().optional(),
    assigned_courier_id: string().optional(),
    delivery_task_status: string().optional(),
    delivery_eta: string().optional(),
  })
  .primaryKey('order_id')

// Line item type for embedded JSON
export type OrderLineItem = {
  line_id: string
  product_id: string
  product_name: string | null
  category: string | null
  quantity: number
  unit_price: number
  line_amount: number
  line_sequence: number
  perishable_flag: boolean
  unit_weight_grams: number | null
  // Dynamic pricing fields from inventory
  inventory_id?: string | null
  base_price?: number | null
  live_price?: number | null
  price_change?: number | null
  zone_adjustment?: number | null
  perishable_adjustment?: number | null
  local_stock_adjustment?: number | null
  popularity_adjustment?: number | null
  scarcity_adjustment?: number | null
  demand_multiplier?: number | null
  demand_premium?: number | null
  product_sale_count?: number | null
  product_total_stock?: number | null
  current_stock_level?: number | null
}

// orders_with_lines_mv - orders with embedded line items as JSON
const orders_with_lines_mv = table('orders_with_lines_mv')
  .columns({
    order_id: string(),
    order_number: string().optional(),
    order_status: string().optional(),
    store_id: string().optional(),
    customer_id: string().optional(),
    delivery_window_start: string().optional(),
    delivery_window_end: string().optional(),
    order_total_amount: number().optional(),
    effective_updated_at: number().optional(),
    line_items: json<OrderLineItem[]>(),
    line_item_count: number().optional(),
    computed_total: number().optional(),
    has_perishable_items: boolean().optional(),
    total_weight_kg: number().optional(),
  })
  .primaryKey('order_id')

// stores_mv - store information
const stores_mv = table('stores_mv')
  .columns({
    store_id: string(),
    store_name: string().optional(),
    store_zone: string().optional(),
    store_address: string().optional(),
    store_status: string().optional(),
    store_capacity_orders_per_hour: number().optional(),
  })
  .primaryKey('store_id')

// store_inventory_mv - inventory by store
const store_inventory_mv = table('store_inventory_mv')
  .columns({
    inventory_id: string(),
    store_id: string().optional(),
    product_id: string().optional(),
    stock_level: number().optional(),
    replenishment_eta: string().optional(),
  })
  .primaryKey('inventory_id')

// courier_schedule_mv - couriers with their tasks as jsonb
const courier_schedule_mv = table('courier_schedule_mv')
  .columns({
    courier_id: string(),
    courier_name: string().optional(),
    home_store_id: string().optional(),
    vehicle_type: string().optional(),
    courier_status: string().optional(),
    tasks: json<Array<{
      task_id: string
      task_status: string
      order_id: string
      eta: string | null
      wait_time_minutes: number | null
      order_created_at: string | null
    }>>(),
  })
  .primaryKey('courier_id')

// customers_mv - customer information
const customers_mv = table('customers_mv')
  .columns({
    customer_id: string(),
    customer_name: string().optional(),
    customer_email: string().optional(),
    customer_address: string().optional(),
  })
  .primaryKey('customer_id')

// products_mv - product catalog
const products_mv = table('products_mv')
  .columns({
    product_id: string(),
    product_name: string().optional(),
    category: string().optional(),
    unit_price: number().optional(),
    perishable: boolean().optional(),
  })
  .primaryKey('product_id')

// inventory_items_with_dynamic_pricing - inventory with live pricing
const inventory_items_with_dynamic_pricing = table('inventory_items_with_dynamic_pricing')
  .columns({
    inventory_id: string(),
    store_id: string().optional(),
    store_name: string().optional(),
    store_zone: string().optional(),
    product_id: string().optional(),
    product_name: string().optional(),
    category: string().optional(),
    stock_level: number().optional(),
    perishable: boolean().optional(),
    base_price: number().optional(),
    zone_adjustment: number().optional(),
    perishable_adjustment: number().optional(),
    local_stock_adjustment: number().optional(),
    popularity_adjustment: number().optional(),
    scarcity_adjustment: number().optional(),
    demand_multiplier: number().optional(),
    demand_premium: number().optional(),
    product_sale_count: number().optional(),
    product_total_stock: number().optional(),
    live_price: number().optional(),
    price_change: number().optional(),
  })
  .primaryKey('inventory_id')

// pricing_yield_mv - pricing capture metrics (per line item)
const pricing_yield_mv = table('pricing_yield_mv')
  .columns({
    line_id: string(),
    order_id: string().optional(),
    store_id: string().optional(),
    store_zone: string().optional(),
    product_id: string().optional(),
    category: string().optional(),
    quantity: number().optional(),
    order_price: number().optional(),
    base_price: number().optional(),
    price_premium: number().optional(),
    order_status: string().optional(),
    effective_updated_at: number().optional(),
  })
  .primaryKey('line_id')

// inventory_risk_mv - inventory at risk metrics
const inventory_risk_mv = table('inventory_risk_mv')
  .columns({
    inventory_id: string(),
    store_id: string().optional(),
    store_name: string().optional(),
    store_zone: string().optional(),
    product_id: string().optional(),
    product_name: string().optional(),
    category: string().optional(),
    stock_level: number().optional(),
    pending_reservations: number().optional(),
    revenue_at_risk: number().optional(),
    perishable: boolean().optional(),
    risk_level: string().optional(),
    risk_weighted_value: number().optional(),
    effective_updated_at: number().optional(),
  })
  .primaryKey('inventory_id')

// store_capacity_health_mv - store capacity metrics
const store_capacity_health_mv = table('store_capacity_health_mv')
  .columns({
    store_id: string(),
    store_name: string().optional(),
    store_zone: string().optional(),
    store_capacity_orders_per_hour: number().optional(),
    current_active_orders: number().optional(),
    current_utilization_pct: number().optional(),
    headroom: number().optional(),
    health_status: string().optional(),
    recommended_action: string().optional(),
    effective_updated_at: number().optional(),
  })
  .primaryKey('store_id')

// Define relationships
const storeRelationships = relationships(stores_mv, ({ many }) => ({
  inventory: many({
    sourceField: ['store_id'],
    destSchema: store_inventory_mv,
    destField: ['store_id'],
  }),
}))

const courierRelationships = relationships(courier_schedule_mv, ({ one }) => ({
  homeStore: one({
    sourceField: ['home_store_id'],
    destSchema: stores_mv,
    destField: ['store_id'],
  }),
}))

// Join orders_with_lines to search source for customer/store names
const orderWithLinesRelationships = relationships(orders_with_lines_mv, ({ one }) => ({
  searchData: one({
    sourceField: ['order_id'],
    destSchema: orders_search_source_mv,
    destField: ['order_id'],
  }),
}))

// Join inventory to products for product details
const inventoryRelationships = relationships(store_inventory_mv, ({ one }) => ({
  product: one({
    sourceField: ['product_id'],
    destSchema: products_mv,
    destField: ['product_id'],
  }),
}))

export const schema = createSchema({
  tables: [orders_search_source_mv, orders_with_lines_mv, stores_mv, store_inventory_mv, courier_schedule_mv, customers_mv, products_mv, inventory_items_with_dynamic_pricing, pricing_yield_mv, inventory_risk_mv, store_capacity_health_mv],
  relationships: [storeRelationships, courierRelationships, orderWithLinesRelationships, inventoryRelationships],
})

export type Schema = typeof schema

export const permissions = definePermissions<unknown, Schema>(schema, () => ({
  orders_search_source_mv: {
    row: {
      select: ANYONE_CAN,
      insert: NOBODY_CAN,
      update: { preMutation: NOBODY_CAN },
      delete: NOBODY_CAN,
    },
  },
  orders_with_lines_mv: {
    row: {
      select: ANYONE_CAN,
      insert: NOBODY_CAN,
      update: { preMutation: NOBODY_CAN },
      delete: NOBODY_CAN,
    },
  },
  stores_mv: {
    row: {
      select: ANYONE_CAN,
      insert: NOBODY_CAN,
      update: { preMutation: NOBODY_CAN },
      delete: NOBODY_CAN,
    },
  },
  store_inventory_mv: {
    row: {
      select: ANYONE_CAN,
      insert: NOBODY_CAN,
      update: { preMutation: NOBODY_CAN },
      delete: NOBODY_CAN,
    },
  },
  courier_schedule_mv: {
    row: {
      select: ANYONE_CAN,
      insert: NOBODY_CAN,
      update: { preMutation: NOBODY_CAN },
      delete: NOBODY_CAN,
    },
  },
  customers_mv: {
    row: {
      select: ANYONE_CAN,
      insert: NOBODY_CAN,
      update: { preMutation: NOBODY_CAN },
      delete: NOBODY_CAN,
    },
  },
  products_mv: {
    row: {
      select: ANYONE_CAN,
      insert: NOBODY_CAN,
      update: { preMutation: NOBODY_CAN },
      delete: NOBODY_CAN,
    },
  },
  inventory_items_with_dynamic_pricing: {
    row: {
      select: ANYONE_CAN,
      insert: NOBODY_CAN,
      update: { preMutation: NOBODY_CAN },
      delete: NOBODY_CAN,
    },
  },
  pricing_yield_mv: {
    row: {
      select: ANYONE_CAN,
      insert: NOBODY_CAN,
      update: { preMutation: NOBODY_CAN },
      delete: NOBODY_CAN,
    },
  },
  inventory_risk_mv: {
    row: {
      select: ANYONE_CAN,
      insert: NOBODY_CAN,
      update: { preMutation: NOBODY_CAN },
      delete: NOBODY_CAN,
    },
  },
  store_capacity_health_mv: {
    row: {
      select: ANYONE_CAN,
      insert: NOBODY_CAN,
      update: { preMutation: NOBODY_CAN },
      delete: NOBODY_CAN,
    },
  },
}))

export type OrderStatus =
  | 'CREATED'
  | 'PICKING'
  | 'OUT_FOR_DELIVERY'
  | 'DELIVERED'
  | 'CANCELLED'

export type StoreStatus = 'OPEN' | 'LIMITED' | 'CLOSED'

export type CourierStatus = 'AVAILABLE' | 'BUSY' | 'OFF_DUTY'
