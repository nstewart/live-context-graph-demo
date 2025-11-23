import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { freshmartApi, triplesApi, OrderFlat, TripleCreate, StoreInfo, CustomerInfo } from '../api/client'
import { formatAmount } from '../test/utils'
import { Package, Clock, CheckCircle, XCircle, Truck, Plus, Edit2, Trash2, X } from 'lucide-react'

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
    } else {
      setFormData(initialFormData)
    }
  }, [order])

  if (!isOpen) return null

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onSave(formData, !!order)
  }

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4">
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
                onChange={e => setFormData({ ...formData, store_id: e.target.value })}
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
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Total Amount</label>
            <input
              type="number"
              step="0.01"
              value={formData.order_total_amount}
              onChange={e => setFormData({ ...formData, order_total_amount: e.target.value })}
              placeholder="45.99"
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
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
  )
}

function OrderCard({
  order,
  onEdit,
  onDelete,
}: {
  order: OrderFlat
  onEdit: (order: OrderFlat) => void
  onDelete: (order: OrderFlat) => void
}) {
  return (
    <div className="bg-white rounded-lg shadow p-4 hover:shadow-md transition-shadow">
      <div className="flex justify-between items-start mb-3">
        <div>
          <h3 className="font-semibold text-gray-900">{order.order_number}</h3>
          <p className="text-sm text-gray-500">{order.customer_name}</p>
        </div>
        <div className="flex items-center gap-2">
          <StatusBadge status={order.order_status} />
          <button
            onClick={() => onEdit(order)}
            className="p-1 text-gray-400 hover:text-blue-600"
            title="Edit order"
          >
            <Edit2 className="h-4 w-4" />
          </button>
          <button
            onClick={() => onDelete(order)}
            className="p-1 text-gray-400 hover:text-red-600"
            title="Delete order"
          >
            <Trash2 className="h-4 w-4" />
          </button>
        </div>
      </div>
      <div className="space-y-1 text-sm">
        <div className="text-gray-600">
          <p><span className="font-medium">Store:</span> {order.store_name || 'Unknown'}</p>
          <p className="text-xs text-gray-400">{order.store_id}</p>
        </div>
        <p className="text-gray-600">
          <span className="font-medium">Window:</span>{' '}
          {order.delivery_window_start?.slice(11, 16)} - {order.delivery_window_end?.slice(11, 16)}
        </p>
        <p className="text-gray-900 font-medium">${formatAmount(order.order_total_amount)}</p>
      </div>
    </div>
  )
}

export default function OrdersDashboardPage() {
  const queryClient = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [editingOrder, setEditingOrder] = useState<OrderFlat | undefined>()
  const [deleteConfirm, setDeleteConfirm] = useState<OrderFlat | null>(null)

  const { data: orders, isLoading, error } = useQuery({
    queryKey: ['orders'],
    queryFn: () => freshmartApi.listOrders().then(r => r.data),
  })

  const { data: stores = [] } = useQuery({
    queryKey: ['stores'],
    queryFn: () => freshmartApi.listStores().then(r => r.data),
  })

  const { data: customers = [] } = useQuery({
    queryKey: ['customers'],
    queryFn: () => freshmartApi.listCustomers().then(r => r.data),
  })

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
          object_type: 'decimal',
        })
      }
      if (data.delivery_window_start) {
        triples.push({
          subject_id: orderId,
          predicate: 'delivery_window_start',
          object_value: new Date(data.delivery_window_start).toISOString(),
          object_type: 'datetime',
        })
      }
      if (data.delivery_window_end) {
        triples.push({
          subject_id: orderId,
          predicate: 'delivery_window_end',
          object_value: new Date(data.delivery_window_end).toISOString(),
          object_type: 'datetime',
        })
      }
      return triplesApi.createBatch(triples)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['orders'] })
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
        fieldsToUpdate.push({ predicate: 'order_total_amount', value: data.order_total_amount, type: 'decimal' })
      }
      if (data.delivery_window_start) {
        fieldsToUpdate.push({
          predicate: 'delivery_window_start',
          value: new Date(data.delivery_window_start).toISOString(),
          type: 'datetime',
        })
      }
      if (data.delivery_window_end) {
        fieldsToUpdate.push({
          predicate: 'delivery_window_end',
          value: new Date(data.delivery_window_end).toISOString(),
          type: 'datetime',
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

  const ordersByStatus =
    orders?.reduce(
      (acc, order) => {
        const status = order.order_status || 'Unknown'
        if (!acc[status]) acc[status] = []
        acc[status].push(order)
        return acc
      },
      {} as Record<string, OrderFlat[]>
    ) || {}

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Orders Dashboard</h1>
          <p className="text-gray-600">Monitor and manage FreshMart orders</p>
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

          {/* Orders grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {orders.map(order => (
              <OrderCard key={order.order_id} order={order} onEdit={handleEdit} onDelete={handleDelete} />
            ))}
          </div>
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
