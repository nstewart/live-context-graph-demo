import axios from 'axios'

// Validate and provide fallback for API URL
const getApiUrl = (): string => {
  const url = import.meta.env.VITE_API_URL;
  if (url && typeof url === 'string' && url.trim() !== '') {
    return url;
  }
  // Fallback to localhost in development
  return 'http://localhost:8080';
};

const API_URL = getApiUrl();

export const apiClient = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Types
export interface OntologyClass {
  id: number
  class_name: string
  prefix: string
  description: string | null
  parent_class_id: number | null
  created_at: string
  updated_at: string
}

export interface OntologyProperty {
  id: number
  prop_name: string
  domain_class_id: number
  range_kind: string
  range_class_id: number | null
  is_multi_valued: boolean
  is_required: boolean
  description: string | null
  domain_class_name: string | null
  range_class_name: string | null
  created_at: string
  updated_at: string
}

export interface Triple {
  id: number
  subject_id: string
  predicate: string
  object_value: string
  object_type: string
  created_at: string
  updated_at: string
}

export interface SubjectInfo {
  subject_id: string
  class_name: string | null
  class_id: number | null
  triples: Triple[]
}

export interface OrderFlat {
  order_id: string
  order_number?: string | null
  order_status?: string | null
  store_id?: string | null
  customer_id?: string | null
  delivery_window_start?: string | null
  delivery_window_end?: string | null
  order_total_amount?: number | null
  customer_name?: string | null
  customer_email?: string | null
  customer_address?: string | null
  store_name?: string | null
  store_zone?: string | null
  store_address?: string | null
  assigned_courier_id?: string | null
  delivery_task_status?: string | null
  delivery_eta?: string | null
}

export interface StoreInfo {
  store_id: string
  store_name: string | null
  store_address: string | null
  store_zone: string | null
  store_status: string | null
  store_capacity_orders_per_hour: number | null
  inventory_items: StoreInventory[]
}

export interface StoreInventory {
  inventory_id: string
  store_id: string | null
  product_id: string | null
  product_name: string | null
  stock_level: number | null
  replenishment_eta: string | null
}

export interface CourierSchedule {
  courier_id: string
  courier_name: string | null
  home_store_id: string | null
  vehicle_type: string | null
  courier_status: string | null
  tasks: Array<{
    task_id: string
    task_status: string
    order_id: string
    eta: string | null
    wait_time_minutes: number | null
    order_created_at: string | null
  }>
}

export interface CustomerInfo {
  customer_id: string
  customer_name: string | null
  customer_email: string | null
  customer_address: string | null
}

export interface ProductInfo {
  product_id: string
  product_name: string | null
  category: string | null
  unit_price: number | null
  perishable: boolean | null
}

export interface OrderLineFlat {
  line_id: string
  order_id: string
  product_id: string
  quantity: number
  unit_price: number
  line_amount: number
  line_sequence: number
  perishable_flag: boolean
  product_name?: string
  category?: string
  effective_updated_at?: string
}

export interface OrderLineCreate {
  product_id: string
  quantity: number
  unit_price: number
  line_sequence?: number
  perishable_flag?: boolean
}

export interface OrderLineUpdate {
  quantity?: number
  unit_price?: number
}

// API functions
export interface OntologyPropertyCreate {
  prop_name: string
  domain_class_id: number
  range_kind: string
  range_class_id?: number | null
  is_multi_valued?: boolean
  is_required?: boolean
  description?: string | null
}

export interface OntologyPropertyUpdate {
  prop_name?: string
  domain_class_id?: number
  range_kind?: string
  range_class_id?: number | null
  is_multi_valued?: boolean
  is_required?: boolean
  description?: string | null
}

export const ontologyApi = {
  listClasses: () => apiClient.get<OntologyClass[]>('/ontology/classes'),
  createClass: (data: Partial<OntologyClass>) =>
    apiClient.post<OntologyClass>('/ontology/classes', data),
  listProperties: () => apiClient.get<OntologyProperty[]>('/ontology/properties'),
  getProperty: (propId: number) =>
    apiClient.get<OntologyProperty>(`/ontology/properties/${propId}`),
  createProperty: (data: OntologyPropertyCreate) =>
    apiClient.post<OntologyProperty>('/ontology/properties', data),
  updateProperty: (propId: number, data: OntologyPropertyUpdate) =>
    apiClient.patch<OntologyProperty>(`/ontology/properties/${propId}`, data),
  deleteProperty: (propId: number) =>
    apiClient.delete(`/ontology/properties/${propId}`),
}

export interface TripleCreate {
  subject_id: string
  predicate: string
  object_value: string
  object_type: 'string' | 'int' | 'float' | 'bool' | 'timestamp' | 'date' | 'entity_ref'
}

export interface SubjectCounts {
  total: number
  by_type: Record<string, number>
}

export const triplesApi = {
  list: (params?: { subject_id?: string; predicate?: string }) =>
    apiClient.get<Triple[]>('/triples', { params }),
  create: (data: TripleCreate) => apiClient.post<Triple>('/triples', data),
  createBatch: (triples: TripleCreate[]) => apiClient.post<Triple[]>('/triples/batch', triples),
  upsertBatch: (triples: TripleCreate[]) => apiClient.put<Triple[]>('/triples/batch', triples),
  update: (tripleId: number, data: { object_value: string }) =>
    apiClient.patch<Triple>(`/triples/${tripleId}`, data),
  delete: (tripleId: number) => apiClient.delete(`/triples/${tripleId}`),
  getSubject: (subjectId: string) =>
    apiClient.get<SubjectInfo>(`/triples/subjects/${encodeURIComponent(subjectId)}`),
  listSubjects: (params?: { class_name?: string; prefix?: string; limit?: number; offset?: number }) =>
    apiClient.get<string[]>('/triples/subjects/list', { params }),
  getSubjectCounts: () => apiClient.get<SubjectCounts>('/triples/subjects/counts'),
  deleteSubject: (subjectId: string) =>
    apiClient.delete(`/triples/subjects/${encodeURIComponent(subjectId)}`),
}

export const freshmartApi = {
  listOrders: (params?: { status?: string; store_id?: string }) =>
    apiClient.get<OrderFlat[]>('/freshmart/orders', { params }),
  getOrder: (orderId: string) =>
    apiClient.get<OrderFlat>(`/freshmart/orders/${encodeURIComponent(orderId)}`),
  listStores: () => apiClient.get<StoreInfo[]>('/freshmart/stores'),
  getStore: (storeId: string) =>
    apiClient.get<StoreInfo>(`/freshmart/stores/${encodeURIComponent(storeId)}`),
  listCustomers: () => apiClient.get<CustomerInfo[]>('/freshmart/customers'),
  listProducts: () => apiClient.get<ProductInfo[]>('/freshmart/products'),
  listCouriers: (params?: { status?: string }) =>
    apiClient.get<CourierSchedule[]>('/freshmart/couriers', { params: { ...params, limit: 1000 } }),
  getCourier: (courierId: string) =>
    apiClient.get<CourierSchedule>(`/freshmart/couriers/${encodeURIComponent(courierId)}`),

  // Order Line Items
  createOrderLinesBatch: (orderId: string, lineItems: OrderLineCreate[]) =>
    apiClient.post<OrderLineFlat[]>(`/freshmart/orders/${encodeURIComponent(orderId)}/line-items/batch`, {
      line_items: lineItems,
    }),
  listOrderLines: (orderId: string) =>
    apiClient.get<OrderLineFlat[]>(`/freshmart/orders/${encodeURIComponent(orderId)}/line-items`),
  getOrderLine: (orderId: string, lineId: string) =>
    apiClient.get<OrderLineFlat>(
      `/freshmart/orders/${encodeURIComponent(orderId)}/line-items/${encodeURIComponent(lineId)}`
    ),
  updateOrderLine: (orderId: string, lineId: string, data: OrderLineUpdate) =>
    apiClient.put<OrderLineFlat>(
      `/freshmart/orders/${encodeURIComponent(orderId)}/line-items/${encodeURIComponent(lineId)}`,
      data
    ),
  deleteOrderLine: (orderId: string, lineId: string) =>
    apiClient.delete(`/freshmart/orders/${encodeURIComponent(orderId)}/line-items/${encodeURIComponent(lineId)}`),

  // Smart-patch order update (only updates what changed)
  updateOrderFields: (orderId: string, data: {
    order_status?: string
    customer_id?: string
    store_id?: string
    delivery_window_start?: string
    delivery_window_end?: string
    line_items?: OrderLineCreate[]
  }) =>
    apiClient.patch(`/freshmart/orders/${encodeURIComponent(orderId)}`, data),

  // Atomic order update (order fields + line items in single transaction)
  atomicUpdateOrder: (orderId: string, data: {
    order_status?: string
    customer_id?: string
    store_id?: string
    delivery_window_start?: string
    delivery_window_end?: string
    line_items: OrderLineCreate[]
  }) =>
    apiClient.put(`/freshmart/orders/${encodeURIComponent(orderId)}/atomic`, data),
}

export const healthApi = {
  check: () => apiClient.get('/health'),
  ready: () => apiClient.get('/ready'),
}

// Query Statistics Types
export interface QueryStatsMetrics {
  median: number
  max: number
  p99: number
}

export interface SourceStats {
  response_time: QueryStatsMetrics
  reaction_time: QueryStatsMetrics
  sample_count: number
  qps: number  // Queries per second (Freshmart approach)
}

export interface QueryStatsResponse {
  order_id: string | null
  is_polling: boolean
  postgresql_view: SourceStats
  batch_cache: SourceStats
  materialize: SourceStats
  timestamp: string
}

export interface QueryStatsHistoryResponse {
  order_id: string | null
  postgresql_view: { reaction_times: number[]; response_times: number[]; timestamps: number[] }
  batch_cache: { reaction_times: number[]; response_times: number[]; timestamps: number[] }
  materialize: { reaction_times: number[]; response_times: number[]; timestamps: number[] }
}

export interface QueryStatsOrder {
  order_id: string
  order_number: string | null
  order_status: string | null
  customer_name: string | null
  store_name: string | null
}

export interface OrderLineItem {
  line_id: string
  product_id: string
  product_name: string | null
  category: string | null
  quantity: number
  unit_price: number
  line_amount: number
  line_sequence: number
  perishable_flag: boolean
  // Live pricing fields (from dynamic pricing view)
  live_price: number | null
  base_price: number | null
  price_change: number | null
  current_stock: number | null
}

export interface OrderWithLinesData {
  order_id: string
  order_number: string | null
  order_status: string | null
  store_id: string | null
  customer_id: string | null
  delivery_window_start: string | null
  delivery_window_end: string | null
  order_total_amount: number | null
  customer_name: string | null
  customer_email: string | null
  customer_address: string | null
  store_name: string | null
  store_zone: string | null
  store_address: string | null
  delivery_task_id: string | null
  assigned_courier_id: string | null
  delivery_task_status: string | null
  delivery_eta: string | null
  line_items: OrderLineItem[]
  line_item_count: number
  computed_total: number | null
  has_perishable_items: boolean
  effective_updated_at: string
}

export interface OrderDataResponse {
  order_id: string | null
  is_polling: boolean
  postgresql_view: OrderWithLinesData | null
  batch_cache: OrderWithLinesData | null
  materialize: OrderWithLinesData | null
}

export interface OrderPredicate {
  predicate: string
  description: string | null
}

export interface TripleWriteRequest {
  subject_id: string
  predicate: string
  object_value: string
}

export const queryStatsApi = {
  // Get orders for dropdown selection
  getOrders: () =>
    apiClient.get<QueryStatsOrder[]>('/api/query-stats/orders'),
  // Get predicates for the write triple form
  getOrderPredicates: () =>
    apiClient.get<OrderPredicate[]>('/api/query-stats/order-predicates'),
  // Start polling for an order
  startPolling: (orderId: string) =>
    apiClient.post(`/api/query-stats/start/${encodeURIComponent(orderId)}`),
  stopPolling: () =>
    apiClient.post('/api/query-stats/stop'),
  getMetrics: () =>
    apiClient.get<QueryStatsResponse>('/api/query-stats/metrics'),
  getMetricsHistory: () =>
    apiClient.get<QueryStatsHistoryResponse>('/api/query-stats/metrics/history'),
  // Get order data from all 3 sources for display cards
  getOrderData: () =>
    apiClient.get<OrderDataResponse>('/api/query-stats/order-data'),
  writeTriple: (data: TripleWriteRequest) =>
    apiClient.post('/api/query-stats/write-triple', data),
}

// Load Generator Types
export type LoadGenStatus = 'stopped' | 'running' | 'starting' | 'stopping'
export type LoadGenProfile = 'demo' | 'standard' | 'peak' | 'stress'

export interface LoadGenProfileInfo {
  name: string
  description: string
  orders_per_minute: number
  concurrent_workflows: number
  duration_minutes: number | null
}

export interface LoadGenStatusResponse {
  status: LoadGenStatus
  profile: string | null
  started_at: string | null
  duration_minutes: number | null
  pid: number | null
}

export interface LoadGenStartRequest {
  profile: LoadGenProfile
  duration_minutes?: number | null
  api_url?: string | null
}

export const loadgenApi = {
  getProfiles: () =>
    apiClient.get<LoadGenProfileInfo[]>('/loadgen/profiles'),
  getStatus: () =>
    apiClient.get<LoadGenStatusResponse>('/loadgen/status'),
  start: (request: LoadGenStartRequest) =>
    apiClient.post<LoadGenStatusResponse>('/loadgen/start', request),
  stop: () =>
    apiClient.post<LoadGenStatusResponse>('/loadgen/stop'),
  getOutput: () =>
    apiClient.get<{ lines: string[] }>('/loadgen/output'),
}
