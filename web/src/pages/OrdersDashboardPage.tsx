import React, { useState, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { freshmartApi, triplesApi, OrderFlat, TripleCreate, StoreInfo, CustomerInfo, OrderLineFlat } from '../api/client'
import { useZeroQuery } from '../hooks/useZeroQuery'
import { useZeroContext } from '../contexts/ZeroContext'
import { formatAmount } from '../test/utils'
import { Package, Clock, CheckCircle, XCircle, Truck, Plus, Edit2, Trash2, X, Wifi, WifiOff, ChevronLeft, ChevronRight, AlertTriangle, ChevronDown, Snowflake, Loader } from 'lucide-react'
import { ProductSelector, ProductWithStock } from '../components/ProductSelector'
import { ShoppingCart } from '../components/ShoppingCart'
import { useShoppingCartStore } from '../stores/shoppingCartStore'

const statusConfig: Record<string, { color: string; icon: typeof Package }> = {
  CREATED: { color: 'bg-blue-100 text-blue-800', icon: Package },
  PICKING: { color: 'bg-yellow-100 text-yellow-800', icon: Clock },
  OUT_FOR_DELIVERY: { color: 'bg-purple-100 text-purple-800', icon: Truck },
  DELIVERED: { color: 'bg-green-100 text-green-800', icon: CheckCircle },
  CANCELLED: { color: 'bg-red-100 text-red-800', icon: XCircle },
}

const statusOrder = ['CREATED', 'PICKING', 'OUT_FOR_DELIVERY', 'DELIVERED', 'CANCELLED']

function StatusBadge({ status }: { status: string | null }) {
  const config = statusConfig[status || ''] || { color: 'bg-gray-100 text-gray-800', icon: Package }
  const Icon = config.icon
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${config.color}`}>
      <Icon className="h-3 w-3" />
      {status || 'Unknown'}
    </span>
  )
}

interface OrderFormData {
  order_number: string
  customer_id: string
  store_id: string
  order_status: string
  order_total_amount: string
  delivery_window_start: string
  delivery_window_end: string
}

const initialFormData: OrderFormData = {
  order_number: '',
  customer_id: '',
  store_id: '',
  order_status: 'CREATED',
  order_total_amount: '',
  delivery_window_start: '',
  delivery_window_end: '',
}

function OrderFormModal({
  isOpen,
  onClose,
  order,
  onSave,
  isLoading,
  stores,
  customers,
}: {
  isOpen: boolean
  onClose: () => void
  order?: OrderFlat
  onSave: (data: OrderFormData, isEdit: boolean) => void
  isLoading: boolean
  stores: StoreInfo[]
  customers: CustomerInfo[]
}) {
  const [formData, setFormData] = useState<OrderFormData>(initialFormData)
  const [showStoreChangeConfirm, setShowStoreChangeConfirm] = useState(false)
  const [pendingStoreId, setPendingStoreId] = useState<string>('')

  const {
    line_items,
    setStore,
    clearCart,
    addItem,
    getTotal
  } = useShoppingCartStore()

  useEffect(() => {
    if (order) {
      setFormData({
        order_number: order.order_number || '',
        customer_id: order.customer_id || '',
        store_id: order.store_id || '',
        order_status: order.order_status || 'CREATED',
        order_total_amount: order.order_total_amount?.toString() || '',
        delivery_window_start: order.delivery_window_start?.slice(0, 16) || '',
        delivery_window_end: order.delivery_window_end?.slice(0, 16) || '',
      })
      // Set store in cart when editing
      if (order.store_id) {
        setStore(order.store_id, true)
      }
      // TODO: Load existing line items when backend API is available
    } else {
      setFormData(initialFormData)
      clearCart()
    }
  }, [order, setStore, clearCart])

  // Sync cart total with form total
  useEffect(() => {
    const total = getTotal()
    if (total > 0) {
      setFormData(prev => ({ ...prev, order_total_amount: total.toFixed(2) }))
    }
  }, [line_items, getTotal])

  if (!isOpen) return null

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()

    // Validate that cart is not empty for new orders
    if (!order && line_items.length === 0) {
      alert('Please add at least one product to the order')
      return
    }

    onSave(formData, !!order)
  }

  const handleStoreChange = (newStoreId: string) => {
    // Try to set the store
    const success = setStore(newStoreId, false)

    if (!success) {
      // Store change requires confirmation
      setPendingStoreId(newStoreId)
      setShowStoreChangeConfirm(true)
    } else {
      // Store changed successfully
      setFormData({ ...formData, store_id: newStoreId })
    }
  }

  const confirmStoreChange = () => {
    setStore(pendingStoreId, true)
    setFormData({ ...formData, store_id: pendingStoreId })
    setShowStoreChangeConfirm(false)
    setPendingStoreId('')
  }

  const cancelStoreChange = () => {
    setShowStoreChangeConfirm(false)
    setPendingStoreId('')
  }

  const handleProductSelect = (product: ProductWithStock) => {
    try {
      addItem({
        product_id: product.product_id,
        product_name: product.product_name || 'Unknown Product',
        quantity: 1,
        unit_price: product.unit_price || 0,
        perishable_flag: product.perishable || false,
        available_stock: product.stock_level,
        category: product.category || undefined,
      })
    } catch (error) {
      alert(error instanceof Error ? error.message : 'Failed to add product')
    }
  }

  return (
    <>
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
        <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl mx-4 max-h-[90vh] overflow-y-auto">
        <div className="flex justify-between items-center p-4 border-b">
          <h2 className="text-lg font-semibold">{order ? 'Edit Order' : 'Create Order'}</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            <X className="h-5 w-5" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Order Number *</label>
              <input
                type="text"
                required
                disabled={!!order}
                value={formData.order_number}
                onChange={e => setFormData({ ...formData, order_number: e.target.value })}
                placeholder="FM-1001"
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 disabled:bg-gray-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Status *</label>
              <select
                required
                value={formData.order_status}
                onChange={e => setFormData({ ...formData, order_status: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
              >
                {statusOrder.map(status => (
                  <option key={status} value={status}>
                    {status.replace('_', ' ')}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Customer *</label>
              <select
                required
                value={formData.customer_id}
                onChange={e => setFormData({ ...formData, customer_id: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
              >
                <option value="">Select a customer...</option>
                {customers.map(customer => (
                  <option key={customer.customer_id} value={customer.customer_id}>
                    {customer.customer_name || 'Unknown'} ({customer.customer_id})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Store *</label>
              <select
                required
                value={formData.store_id}
                onChange={e => handleStoreChange(e.target.value)}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
              >
                <option value="">Select a store...</option>
                {stores.map(store => (
                  <option key={store.store_id} value={store.store_id}>
                    {store.store_name || 'Unknown'} ({store.store_id})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Product Selector */}
          <div>
            <ProductSelector
              storeId={formData.store_id || null}
              onProductSelect={handleProductSelect}
              disabled={!formData.store_id}
            />
          </div>

          {/* Shopping Cart */}
          <div>
            <ShoppingCart />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Total Amount
              <span className="ml-2 text-xs text-gray-500">(Auto-calculated from cart)</span>
            </label>
            <input
              type="number"
              step="0.01"
              value={formData.order_total_amount}
              readOnly
              placeholder="0.00"
              className="w-full px-3 py-2 border rounded-lg bg-gray-50 text-gray-700"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Delivery Window Start</label>
              <input
                type="datetime-local"
                value={formData.delivery_window_start}
                onChange={e => setFormData({ ...formData, delivery_window_start: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Delivery Window End</label>
              <input
                type="datetime-local"
                value={formData.delivery_window_end}
                onChange={e => setFormData({ ...formData, delivery_window_end: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
            >
              {isLoading ? 'Saving...' : order ? 'Update' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>

      {/* Store Change Confirmation Dialog */}
      {showStoreChangeConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-60">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-sm mx-4">
            <div className="flex items-start gap-3 mb-4">
              <div className="p-2 bg-orange-100 rounded-lg">
                <AlertTriangle className="h-5 w-5 text-orange-600" />
              </div>
              <div>
                <h3 className="text-lg font-semibold mb-1">Change Store?</h3>
                <p className="text-gray-600 text-sm">
                  Changing the store will clear all items from your cart. Are you sure?
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={cancelStoreChange}
                className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={confirmStoreChange}
                className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700"
              >
                Change Store
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

function OrdersTable({
  orders,
  onEdit,
  onDelete,
}: {
  orders: OrderFlat[]
  onEdit: (order: OrderFlat) => void
  onDelete: (order: OrderFlat) => void
}) {
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set())
  const [loadingLineItems, setLoadingLineItems] = useState<Set<string>>(new Set())
  const [lineItemsCache, setLineItemsCache] = useState<Map<string, OrderLineFlat[]>>(new Map())

  const toggleRow = async (orderId: string) => {
    const newExpanded = new Set(expandedRows)

    if (newExpanded.has(orderId)) {
      // Collapse
      newExpanded.delete(orderId)
    } else {
      // Expand and load line items if not cached
      newExpanded.add(orderId)

      if (!lineItemsCache.has(orderId)) {
        setLoadingLineItems(prev => new Set(prev).add(orderId))
        try {
          const response = await freshmartApi.listOrderLines(orderId)
          setLineItemsCache(prev => new Map(prev).set(orderId, response.data))
        } catch (error: any) {
          // If 404, the order has no line items yet - cache empty array
          if (error.response?.status === 404) {
            setLineItemsCache(prev => new Map(prev).set(orderId, []))
          } else {
            console.error('Failed to load line items:', error)
          }
        } finally {
          setLoadingLineItems(prev => {
            const next = new Set(prev)
            next.delete(orderId)
            return next
          })
        }
      }
    }

    setExpandedRows(newExpanded)
  }

  return (
    <div className="bg-white rounded-lg shadow overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-2 py-3 w-10"></th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Order
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Customer
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Store
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Delivery Window
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Amount
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Courier
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {orders.map((order) => (
              <React.Fragment key={order.order_id}>
                <tr className="hover:bg-gray-50">
                  <td className="px-2 py-3">
                    <button
                      onClick={() => toggleRow(order.order_id)}
                      className="p-1 hover:bg-gray-200 rounded transition-colors"
                      title="Toggle line items"
                    >
                      {expandedRows.has(order.order_id) ? (
                        <ChevronDown className="h-4 w-4 text-gray-600" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-gray-600" />
                      )}
                    </button>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900">{order.order_number}</div>
                    <div className="text-xs text-gray-400">{order.order_id}</div>
                  </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  <StatusBadge status={order.order_status} />
                </td>
                <td className="px-4 py-3">
                  <div className="text-sm text-gray-900">{order.customer_name || 'Unknown'}</div>
                  <div className="text-xs text-gray-500 truncate max-w-xs">{order.customer_address}</div>
                </td>
                <td className="px-4 py-3">
                  <div className="text-sm text-gray-900">{order.store_name || 'Unknown'}</div>
                  <div className="text-xs text-gray-500">{order.store_zone}</div>
                </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  <div className="text-sm text-gray-900">
                    {order.delivery_window_start?.slice(11, 16)} - {order.delivery_window_end?.slice(11, 16)}
                  </div>
                  <div className="text-xs text-gray-500">
                    {order.delivery_window_start?.slice(0, 10)}
                  </div>
                </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  <div className="text-sm font-medium text-gray-900">
                    ${formatAmount(order.order_total_amount)}
                  </div>
                </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  <div className="text-sm text-gray-900">
                    {order.assigned_courier_id ? (
                      <>
                        <div className="text-xs text-gray-500">{order.assigned_courier_id}</div>
                        {order.delivery_task_status && (
                          <span className="text-xs px-1.5 py-0.5 rounded bg-gray-100 text-gray-600">
                            {order.delivery_task_status}
                          </span>
                        )}
                      </>
                    ) : (
                      <span className="text-xs text-gray-400">Unassigned</span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-right text-sm font-medium">
                  <div className="flex items-center justify-end gap-2">
                    <button
                      onClick={() => onEdit(order)}
                      className="text-blue-600 hover:text-blue-900"
                      title="Edit order"
                    >
                      <Edit2 className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => onDelete(order)}
                      className="text-red-600 hover:text-red-900"
                      title="Delete order"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </tr>

              {/* Expanded Row - Line Items */}
              {expandedRows.has(order.order_id) && (
                <tr key={`${order.order_id}-expanded`}>
                  <td colSpan={8} className="px-0 py-0">
                    <div className="bg-gray-50 border-t border-b border-gray-200">
                      {loadingLineItems.has(order.order_id) ? (
                        <div className="px-8 py-6 text-center">
                          <Loader className="h-6 w-6 animate-spin inline-block text-gray-400 mb-2" />
                          <p className="text-sm text-gray-500">Loading line items...</p>
                        </div>
                      ) : (
                        <LineItemsTable
                          lineItems={lineItemsCache.get(order.order_id) || []}
                          orderId={order.order_id}
                        />
                      )}
                    </div>
                  </td>
                </tr>
              )}
            </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function LineItemsTable({
  lineItems,
}: {
  lineItems: OrderLineFlat[]
  orderId: string
}) {
  if (lineItems.length === 0) {
    return (
      <div className="px-8 py-6 text-center">
        <Package className="h-12 w-12 mx-auto mb-2 text-gray-300" />
        <p className="text-sm font-medium text-gray-700">No line items</p>
        <p className="text-xs text-gray-500 mt-1">This order has no products added yet</p>
      </div>
    )
  }

  return (
    <div className="px-8 py-4">
      <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
        <Package className="h-4 w-4" />
        Order Line Items ({lineItems.length})
      </h4>
      <table className="min-w-full text-sm">
        <thead className="bg-gray-100">
          <tr>
            <th className="text-left px-3 py-2 text-xs font-medium text-gray-600">Product</th>
            <th className="text-center px-3 py-2 text-xs font-medium text-gray-600">Quantity</th>
            <th className="text-right px-3 py-2 text-xs font-medium text-gray-600">Unit Price</th>
            <th className="text-right px-3 py-2 text-xs font-medium text-gray-600">Line Total</th>
            <th className="text-center px-3 py-2 text-xs font-medium text-gray-600 w-20">Status</th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-100">
          {lineItems.map((item) => (
            <tr key={item.line_id} className="hover:bg-gray-50">
              <td className="px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-900">
                    {item.product_name || item.product_id}
                  </span>
                  {item.perishable_flag && (
                    <span title="Perishable - requires cold chain">
                      <Snowflake className="h-4 w-4 text-blue-600" />
                    </span>
                  )}
                </div>
                {item.category && (
                  <div className="text-xs text-gray-500 mt-0.5">{item.category}</div>
                )}
              </td>
              <td className="px-3 py-2 text-center text-gray-900">{item.quantity}</td>
              <td className="px-3 py-2 text-right text-gray-900">
                ${formatAmount(item.unit_price)}
              </td>
              <td className="px-3 py-2 text-right font-medium text-gray-900">
                ${formatAmount(item.line_amount)}
              </td>
              <td className="px-3 py-2 text-center">
                {item.perishable_flag ? (
                  <Snowflake className="h-4 w-4 inline-block text-blue-600" />
                ) : (
                  <span className="text-gray-400">-</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="bg-gray-50 font-semibold">
            <td colSpan={3} className="px-3 py-2 text-right text-gray-700">
              Subtotal ({lineItems.reduce((sum, item) => sum + item.quantity, 0)} items):
            </td>
            <td className="px-3 py-2 text-right text-gray-900">
              ${formatAmount(lineItems.reduce((sum, item) => sum + item.line_amount, 0))}
            </td>
            <td></td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}

export default function OrdersDashboardPage() {
  const queryClient = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [editingOrder, setEditingOrder] = useState<OrderFlat | undefined>()
  const [deleteConfirm, setDeleteConfirm] = useState<OrderFlat | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const itemsPerPage = 100

  // 🔥 ZERO WebSocket - Real-time orders data
  const { connected: zeroConnected } = useZeroContext()
  const { data: orders, isLoading: zeroLoading, error: zeroError } = useZeroQuery<OrderFlat>({
    collection: 'orders',
  })

  // Track last update time for visual feedback
  const [lastUpdateTime, setLastUpdateTime] = useState<number>(Date.now())
  useEffect(() => {
    if (orders) {
      setLastUpdateTime(Date.now())
    }
  }, [orders])

  // Still using React Query for stores and customers (will migrate later)
  const { data: stores = [] } = useQuery({
    queryKey: ['stores'],
    queryFn: () => freshmartApi.listStores().then(r => r.data),
  })

  const { data: customers = [] } = useQuery({
    queryKey: ['customers'],
    queryFn: () => freshmartApi.listCustomers().then(r => r.data),
  })

  const isLoading = zeroLoading
  const error = zeroError

  const createMutation = useMutation({
    mutationFn: async (data: OrderFormData) => {
      const orderId = `order:${data.order_number}`
      const triples: TripleCreate[] = [
        { subject_id: orderId, predicate: 'order_number', object_value: data.order_number, object_type: 'string' },
        { subject_id: orderId, predicate: 'order_status', object_value: data.order_status, object_type: 'string' },
        { subject_id: orderId, predicate: 'placed_by', object_value: data.customer_id, object_type: 'entity_ref' },
        { subject_id: orderId, predicate: 'order_store', object_value: data.store_id, object_type: 'entity_ref' },
      ]
      if (data.order_total_amount) {
        triples.push({
          subject_id: orderId,
          predicate: 'order_total_amount',
          object_value: data.order_total_amount,
          object_type: 'float',
        })
      }
      if (data.delivery_window_start) {
        triples.push({
          subject_id: orderId,
          predicate: 'delivery_window_start',
          object_value: new Date(data.delivery_window_start).toISOString(),
          object_type: 'timestamp',
        })
      }
      if (data.delivery_window_end) {
        triples.push({
          subject_id: orderId,
          predicate: 'delivery_window_end',
          object_value: new Date(data.delivery_window_end).toISOString(),
          object_type: 'timestamp',
        })
      }

      // Create order first
      await triplesApi.createBatch(triples)

      // Then create line items if any exist in cart
      const cartItems = useShoppingCartStore.getState().line_items
      if (cartItems.length > 0) {
        const lineItemsToCreate = cartItems.map((item, index) => ({
          product_id: item.product_id,
          quantity: item.quantity,
          unit_price: item.unit_price,
          line_sequence: index + 1,
          perishable_flag: item.perishable_flag,
        }))

        await freshmartApi.createOrderLinesBatch(orderId, lineItemsToCreate)
      }

      return { orderId }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      useShoppingCartStore.getState().clearCart()
      setShowModal(false)
      setEditingOrder(undefined)
    },
  })

  const updateMutation = useMutation({
    mutationFn: async ({ order, data }: { order: OrderFlat; data: OrderFormData }) => {
      // Get existing triples for this order
      const subjectInfo = await triplesApi.getSubject(order.order_id).then(r => r.data)

      // Update each field by finding the triple and updating it, or creating new
      const updates: Promise<unknown>[] = []
      const fieldsToUpdate: { predicate: string; value: string; type: TripleCreate['object_type'] }[] = [
        { predicate: 'order_status', value: data.order_status, type: 'string' },
        { predicate: 'placed_by', value: data.customer_id, type: 'entity_ref' },
        { predicate: 'order_store', value: data.store_id, type: 'entity_ref' },
      ]
      if (data.order_total_amount) {
        fieldsToUpdate.push({ predicate: 'order_total_amount', value: data.order_total_amount, type: 'float' })
      }
      if (data.delivery_window_start) {
        fieldsToUpdate.push({
          predicate: 'delivery_window_start',
          value: new Date(data.delivery_window_start).toISOString(),
          type: 'timestamp',
        })
      }
      if (data.delivery_window_end) {
        fieldsToUpdate.push({
          predicate: 'delivery_window_end',
          value: new Date(data.delivery_window_end).toISOString(),
          type: 'timestamp',
        })
      }

      for (const field of fieldsToUpdate) {
        const existingTriple = subjectInfo.triples.find(t => t.predicate === field.predicate)
        if (existingTriple) {
          updates.push(triplesApi.update(existingTriple.id, { object_value: field.value }))
        } else {
          updates.push(
            triplesApi.create({
              subject_id: order.order_id,
              predicate: field.predicate,
              object_value: field.value,
              object_type: field.type,
            })
          )
        }
      }

      await Promise.all(updates)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      setShowModal(false)
      setEditingOrder(undefined)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (orderId: string) => triplesApi.deleteSubject(orderId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
      setDeleteConfirm(null)
    },
  })

  const handleSave = (data: OrderFormData, isEdit: boolean) => {
    if (isEdit && editingOrder) {
      updateMutation.mutate({ order: editingOrder, data })
    } else {
      createMutation.mutate(data)
    }
  }

  const handleEdit = (order: OrderFlat) => {
    setEditingOrder(order)
    setShowModal(true)
  }

  const handleDelete = (order: OrderFlat) => {
    setDeleteConfirm(order)
  }

  // Sort orders by order_number for stable display
  const sortedOrders = useMemo(() => {
    if (!orders) return []
    return [...orders].sort((a, b) => {
      const aNum = a.order_number || ''
      const bNum = b.order_number || ''
      return aNum.localeCompare(bNum)
    })
  }, [orders])

  // Calculate stats from ALL orders (not paginated)
  const ordersByStatus = useMemo(() => {
    return sortedOrders.reduce(
      (acc, order) => {
        const status = order.order_status || 'Unknown'
        if (!acc[status]) acc[status] = []
        acc[status].push(order)
        return acc
      },
      {} as Record<string, OrderFlat[]>
    )
  }, [sortedOrders])

  // Pagination calculations
  const totalOrders = sortedOrders.length
  const totalPages = Math.ceil(totalOrders / itemsPerPage)
  const startIndex = (currentPage - 1) * itemsPerPage
  const endIndex = startIndex + itemsPerPage
  const paginatedOrders = sortedOrders.slice(startIndex, endIndex)

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">Orders Dashboard</h1>
            {zeroConnected ? (
              <span className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-green-700 bg-green-100 rounded-full">
                <Wifi className="h-3 w-3" />
                Real-time
              </span>
            ) : (
              <span className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-amber-700 bg-amber-100 rounded-full">
                <WifiOff className="h-3 w-3" />
                Connecting...
              </span>
            )}
            <span className="text-xs text-gray-500">
              Last update: {new Date(lastUpdateTime).toLocaleTimeString()}
            </span>
          </div>
          <p className="text-gray-600">Monitor and manage FreshMart orders via WebSocket</p>
        </div>
        <button
          onClick={() => {
            setEditingOrder(undefined)
            setShowModal(true)
          }}
          className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
        >
          <Plus className="h-4 w-4" />
          Create Order
        </button>
      </div>

      {isLoading && <div className="text-center py-8 text-gray-500">Loading orders...</div>}

      {error && (
        <div className="bg-red-50 text-red-700 p-4 rounded-lg">
          Error loading orders. Make sure the API is running.
        </div>
      )}

      {orders && (
        <>
          {/* Stats */}
          <div className="grid grid-cols-5 gap-4 mb-6">
            {statusOrder.map(status => (
              <div key={status} className="bg-white rounded-lg shadow p-4">
                <div className="text-sm text-gray-500">{status.replace('_', ' ')}</div>
                <div className="text-2xl font-bold text-gray-900">{ordersByStatus[status]?.length || 0}</div>
              </div>
            ))}
          </div>

          {/* Orders table */}
          <OrdersTable orders={paginatedOrders} onEdit={handleEdit} onDelete={handleDelete} />

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="mt-6 flex items-center justify-between">
              <div className="text-sm text-gray-600">
                Showing {startIndex + 1}-{Math.min(endIndex, totalOrders)} of {totalOrders} orders
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="p-2 border rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  title="Previous page"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <div className="flex items-center gap-1">
                  {/* Show first page */}
                  {currentPage > 3 && (
                    <>
                      <button
                        onClick={() => setCurrentPage(1)}
                        className="px-3 py-1 border rounded hover:bg-gray-50"
                      >
                        1
                      </button>
                      <span className="px-2">...</span>
                    </>
                  )}

                  {/* Show pages around current */}
                  {Array.from({ length: totalPages }, (_, i) => i + 1)
                    .filter(page => page >= currentPage - 2 && page <= currentPage + 2)
                    .map(page => (
                      <button
                        key={page}
                        onClick={() => setCurrentPage(page)}
                        className={`px-3 py-1 border rounded ${
                          page === currentPage
                            ? 'bg-green-600 text-white'
                            : 'hover:bg-gray-50'
                        }`}
                      >
                        {page}
                      </button>
                    ))}

                  {/* Show last page */}
                  {currentPage < totalPages - 2 && (
                    <>
                      <span className="px-2">...</span>
                      <button
                        onClick={() => setCurrentPage(totalPages)}
                        className="px-3 py-1 border rounded hover:bg-gray-50"
                      >
                        {totalPages}
                      </button>
                    </>
                  )}
                </div>
                <button
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={currentPage === totalPages}
                  className="p-2 border rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  title="Next page"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Create/Edit Modal */}
      <OrderFormModal
        isOpen={showModal}
        onClose={() => {
          setShowModal(false)
          setEditingOrder(undefined)
        }}
        order={editingOrder}
        onSave={handleSave}
        isLoading={createMutation.isPending || updateMutation.isPending}
        stores={stores}
        customers={customers}
      />

      {/* Delete Confirmation */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-sm mx-4">
            <h3 className="text-lg font-semibold mb-2">Delete Order</h3>
            <p className="text-gray-600 mb-4">
              Are you sure you want to delete order <strong>{deleteConfirm.order_number}</strong>? This action cannot
              be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteMutation.mutate(deleteConfirm.order_id)}
                disabled={deleteMutation.isPending}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
              >
                {deleteMutation.isPending ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
