import { useState, useEffect } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { triplesApi, StoreInfo, StoreInventory, TripleCreate, ProductInfo } from '../api/client'
import { useZero, useQuery } from '@rocicorp/zero/react'
import { Schema } from '../schema'
import { Warehouse, AlertTriangle, Plus, Edit2, Trash2, X, Package, Wifi, WifiOff } from 'lucide-react'

const storeStatuses = ['OPEN', 'LIMITED', 'CLOSED']

interface StoreFormData {
  store_id: string
  store_name: string
  store_address: string
  store_zone: string
  store_status: string
  store_capacity_orders_per_hour: string
}

interface InventoryFormData {
  inventory_id: string
  store_id: string
  product_id: string
  stock_level: string
  replenishment_eta: string
}

const initialStoreForm: StoreFormData = {
  store_id: '',
  store_name: '',
  store_address: '',
  store_zone: '',
  store_status: 'OPEN',
  store_capacity_orders_per_hour: '',
}

const initialInventoryForm: InventoryFormData = {
  inventory_id: '',
  store_id: '',
  product_id: '',
  stock_level: '',
  replenishment_eta: '',
}

function StoreFormModal({
  isOpen,
  onClose,
  store,
  onSave,
  isLoading,
}: {
  isOpen: boolean
  onClose: () => void
  store?: StoreInfo
  onSave: (data: StoreFormData, isEdit: boolean) => void
  isLoading: boolean
}) {
  const [formData, setFormData] = useState<StoreFormData>(initialStoreForm)

  useEffect(() => {
    if (store) {
      setFormData({
        store_id: store.store_id.replace('store:', ''),
        store_name: store.store_name || '',
        store_address: store.store_address || '',
        store_zone: store.store_zone || '',
        store_status: store.store_status || 'OPEN',
        store_capacity_orders_per_hour: store.store_capacity_orders_per_hour?.toString() || '',
      })
    } else {
      setFormData(initialStoreForm)
    }
  }, [store])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4">
        <div className="flex justify-between items-center p-4 border-b">
          <h2 className="text-lg font-semibold">{store ? 'Edit Store' : 'Create Store'}</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            <X className="h-5 w-5" />
          </button>
        </div>
        <form
          onSubmit={e => {
            e.preventDefault()
            onSave(formData, !!store)
          }}
          className="p-4 space-y-4"
        >
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Store ID *</label>
              <input
                type="text"
                required
                disabled={!!store}
                value={formData.store_id}
                onChange={e => setFormData({ ...formData, store_id: e.target.value })}
                placeholder="BK-01"
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 disabled:bg-gray-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Status *</label>
              <select
                required
                value={formData.store_status}
                onChange={e => setFormData({ ...formData, store_status: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
              >
                {storeStatuses.map(status => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Store Name *</label>
            <input
              type="text"
              required
              value={formData.store_name}
              onChange={e => setFormData({ ...formData, store_name: e.target.value })}
              placeholder="FreshMart Brooklyn"
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Address *</label>
            <input
              type="text"
              required
              value={formData.store_address}
              onChange={e => setFormData({ ...formData, store_address: e.target.value })}
              placeholder="123 Main St, Brooklyn, NY"
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Zone *</label>
              <input
                type="text"
                required
                value={formData.store_zone}
                onChange={e => setFormData({ ...formData, store_zone: e.target.value })}
                placeholder="BK"
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Capacity (orders/hr)</label>
              <input
                type="number"
                value={formData.store_capacity_orders_per_hour}
                onChange={e => setFormData({ ...formData, store_capacity_orders_per_hour: e.target.value })}
                placeholder="50"
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-4">
            <button type="button" onClick={onClose} className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50">
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
            >
              {isLoading ? 'Saving...' : store ? 'Update' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

function InventoryFormModal({
  isOpen,
  onClose,
  inventory,
  storeId,
  products,
  onSave,
  isLoading,
}: {
  isOpen: boolean
  onClose: () => void
  inventory?: StoreInventory
  storeId: string
  products: ProductInfo[]
  onSave: (data: InventoryFormData, isEdit: boolean) => void
  isLoading: boolean
}) {
  const [formData, setFormData] = useState<InventoryFormData>({ ...initialInventoryForm, store_id: storeId })

  useEffect(() => {
    if (inventory) {
      setFormData({
        inventory_id: inventory.inventory_id.replace('inventory:', ''),
        store_id: inventory.store_id || storeId,
        product_id: inventory.product_id || '',
        stock_level: inventory.stock_level?.toString() || '',
        replenishment_eta: inventory.replenishment_eta?.slice(0, 16) || '',
      })
    } else {
      setFormData({ ...initialInventoryForm, store_id: storeId })
    }
  }, [inventory, storeId])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-60">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4">
        <div className="flex justify-between items-center p-4 border-b">
          <h2 className="text-lg font-semibold">{inventory ? 'Edit Inventory' : 'Add Inventory Item'}</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            <X className="h-5 w-5" />
          </button>
        </div>
        <form
          onSubmit={e => {
            e.preventDefault()
            onSave(formData, !!inventory)
          }}
          className="p-4 space-y-4"
        >
          {!inventory && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Inventory ID *</label>
              <input
                type="text"
                required
                value={formData.inventory_id}
                onChange={e => setFormData({ ...formData, inventory_id: e.target.value })}
                placeholder="INV-BK01-001"
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
              />
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Product *</label>
            <select
              required
              value={formData.product_id}
              onChange={e => setFormData({ ...formData, product_id: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
            >
              <option value="">Select a product...</option>
              {products.map(p => (
                <option key={p.product_id} value={p.product_id}>
                  {p.product_name || 'Unknown'} ({p.product_id})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Stock Level *</label>
            <input
              type="number"
              required
              value={formData.stock_level}
              onChange={e => setFormData({ ...formData, stock_level: e.target.value })}
              placeholder="100"
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Replenishment ETA</label>
            <input
              type="datetime-local"
              value={formData.replenishment_eta}
              onChange={e => setFormData({ ...formData, replenishment_eta: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
            />
          </div>
          <div className="flex justify-end gap-2 pt-4">
            <button type="button" onClick={onClose} className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50">
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
            >
              {isLoading ? 'Saving...' : inventory ? 'Update' : 'Add'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function StoresInventoryPage() {
  const queryClient = useQueryClient()
  const [showStoreModal, setShowStoreModal] = useState(false)
  const [editingStore, setEditingStore] = useState<StoreInfo | undefined>()
  const [deleteStoreConfirm, setDeleteStoreConfirm] = useState<StoreInfo | null>(null)
  const [showInventoryModal, setShowInventoryModal] = useState(false)
  const [editingInventory, setEditingInventory] = useState<{ inventory?: StoreInventory; storeId: string } | null>(null)
  const [deleteInventoryConfirm, setDeleteInventoryConfirm] = useState<StoreInventory | null>(null)
  const [_expandedStores, _setExpandedStores] = useState<Set<string>>(new Set()) // TODO: implement store expansion
  const [viewAllInventoryStore, setViewAllInventoryStore] = useState<StoreInfo | null>(null)

  // 🔥 ZERO - Real-time stores with inventory via relationship
  const z = useZero<Schema>()

  // Stores with related inventory - Zero handles the join!
  const [storesData] = useQuery(
    z.query.stores_mv
      .related('inventory', q => q.orderBy('inventory_id', 'asc'))
      .orderBy('store_id', 'asc')
  )

  // Products sorted by product_id
  const [products] = useQuery(z.query.products_mv.orderBy('product_id', 'asc'))

  const zeroConnected = true // Zero handles connection internally

  // Convert Zero data to StoreInfo format (inventory comes from relationship)
  const stores: StoreInfo[] = storesData.map(store => ({
    store_id: store.store_id,
    store_name: store.store_name ?? null,
    store_zone: store.store_zone ?? null,
    store_address: store.store_address ?? null,
    store_status: store.store_status ?? null,
    store_capacity_orders_per_hour: store.store_capacity_orders_per_hour ?? null,
    inventory_items: store.inventory.map(inv => ({
      inventory_id: inv.inventory_id,
      store_id: inv.store_id ?? null,
      product_id: inv.product_id ?? null,
      stock_level: inv.stock_level ?? null,
      replenishment_eta: inv.replenishment_eta ?? null,
    })),
  }))

  const isLoading = storesData.length === 0

  const createStoreMutation = useMutation({
    mutationFn: async (data: StoreFormData) => {
      const storeId = `store:${data.store_id}`
      const triples: TripleCreate[] = [
        { subject_id: storeId, predicate: 'store_name', object_value: data.store_name, object_type: 'string' },
        { subject_id: storeId, predicate: 'store_address', object_value: data.store_address, object_type: 'string' },
        { subject_id: storeId, predicate: 'store_zone', object_value: data.store_zone, object_type: 'string' },
        { subject_id: storeId, predicate: 'store_status', object_value: data.store_status, object_type: 'string' },
      ]
      if (data.store_capacity_orders_per_hour && data.store_capacity_orders_per_hour.trim() !== '') {
        triples.push({
          subject_id: storeId,
          predicate: 'store_capacity_orders_per_hour',
          object_value: String(data.store_capacity_orders_per_hour),
          object_type: 'int',
        })
      }
      return triplesApi.createBatch(triples)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stores'] })
      setShowStoreModal(false)
      setEditingStore(undefined)
    },
  })

  const updateStoreMutation = useMutation({
    mutationFn: async ({ store, data }: { store: StoreInfo; data: StoreFormData }) => {
      const subjectInfo = await triplesApi.getSubject(store.store_id).then(r => r.data)
      const updates: Promise<unknown>[] = []
      const fields: { predicate: string; value: string; type: TripleCreate['object_type'] }[] = [
        { predicate: 'store_name', value: data.store_name, type: 'string' },
        { predicate: 'store_address', value: data.store_address, type: 'string' },
        { predicate: 'store_zone', value: data.store_zone, type: 'string' },
        { predicate: 'store_status', value: data.store_status, type: 'string' },
      ]
      if (data.store_capacity_orders_per_hour) {
        fields.push({ predicate: 'store_capacity_orders_per_hour', value: data.store_capacity_orders_per_hour, type: 'int' })
      }
      for (const field of fields) {
        const existing = subjectInfo.triples.find(t => t.predicate === field.predicate)
        if (existing) {
          updates.push(triplesApi.update(existing.id, { object_value: field.value }))
        } else {
          updates.push(triplesApi.create({ subject_id: store.store_id, predicate: field.predicate, object_value: field.value, object_type: field.type }))
        }
      }
      await Promise.all(updates)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stores'] })
      setShowStoreModal(false)
      setEditingStore(undefined)
    },
  })

  const deleteStoreMutation = useMutation({
    mutationFn: (storeId: string) => triplesApi.deleteSubject(storeId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stores'] })
      setDeleteStoreConfirm(null)
    },
  })

  const createInventoryMutation = useMutation({
    mutationFn: async (data: InventoryFormData) => {
      const inventoryId = `inventory:${data.inventory_id}`
      const triples: TripleCreate[] = [
        { subject_id: inventoryId, predicate: 'inventory_store', object_value: data.store_id, object_type: 'entity_ref' },
        { subject_id: inventoryId, predicate: 'inventory_product', object_value: data.product_id, object_type: 'entity_ref' },
        { subject_id: inventoryId, predicate: 'stock_level', object_value: String(data.stock_level), object_type: 'int' },
      ]
      if (data.replenishment_eta) {
        triples.push({
          subject_id: inventoryId,
          predicate: 'replenishment_eta',
          object_value: new Date(data.replenishment_eta).toISOString(),
          object_type: 'timestamp',
        })
      }
      return triplesApi.createBatch(triples)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stores'] })
      setShowInventoryModal(false)
      setEditingInventory(null)
    },
  })

  const updateInventoryMutation = useMutation({
    mutationFn: async ({ inventory, data }: { inventory: StoreInventory; data: InventoryFormData }) => {
      const subjectInfo = await triplesApi.getSubject(inventory.inventory_id).then(r => r.data)
      const updates: Promise<unknown>[] = []
      const fields: { predicate: string; value: string; type: TripleCreate['object_type'] }[] = [
        { predicate: 'inventory_product', value: data.product_id, type: 'entity_ref' },
        { predicate: 'stock_level', value: String(data.stock_level), type: 'int' },
      ]
      if (data.replenishment_eta) {
        fields.push({ predicate: 'replenishment_eta', value: new Date(data.replenishment_eta).toISOString(), type: 'timestamp' })
      }
      for (const field of fields) {
        const existing = subjectInfo.triples.find(t => t.predicate === field.predicate)
        if (existing) {
          updates.push(triplesApi.update(existing.id, { object_value: field.value }))
        } else {
          updates.push(triplesApi.create({ subject_id: inventory.inventory_id, predicate: field.predicate, object_value: field.value, object_type: field.type }))
        }
      }
      await Promise.all(updates)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stores'] })
      setShowInventoryModal(false)
      setEditingInventory(null)
    },
  })

  const deleteInventoryMutation = useMutation({
    mutationFn: (inventoryId: string) => triplesApi.deleteSubject(inventoryId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['stores'] })
      setDeleteInventoryConfirm(null)
    },
  })

  const handleSaveStore = (data: StoreFormData, isEdit: boolean) => {
    if (isEdit && editingStore) {
      updateStoreMutation.mutate({ store: editingStore, data })
    } else {
      createStoreMutation.mutate(data)
    }
  }

  const handleSaveInventory = (data: InventoryFormData, isEdit: boolean) => {
    if (isEdit && editingInventory?.inventory) {
      updateInventoryMutation.mutate({ inventory: editingInventory.inventory, data })
    } else {
      createInventoryMutation.mutate(data)
    }
  }

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">Stores & Inventory</h1>
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
          </div>
          <p className="text-gray-600">Real-time store updates with inventory data</p>
        </div>
        <button
          onClick={() => {
            setEditingStore(undefined)
            setShowStoreModal(true)
          }}
          className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
        >
          <Plus className="h-4 w-4" />
          Add Store
        </button>
      </div>

      {isLoading && <div className="text-center py-8 text-gray-500">Loading stores...</div>}

      {stores.length > 0 && (
        <div className="space-y-6">
          {stores.map(store => (
            <div key={store.store_id} className="bg-white rounded-lg shadow">
              <div className="p-4 border-b flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-green-100 rounded-lg">
                    <Warehouse className="h-6 w-6 text-green-600" />
                  </div>
                  <div>
                    <h2 className="font-semibold text-gray-900">{store.store_name}</h2>
                    <p className="text-sm text-gray-500">{store.store_address}</p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="text-right">
                    <span
                      className={`inline-block px-2 py-1 rounded text-xs font-medium ${
                        store.store_status === 'OPEN'
                          ? 'bg-green-100 text-green-800'
                          : store.store_status === 'LIMITED'
                            ? 'bg-yellow-100 text-yellow-800'
                            : 'bg-red-100 text-red-800'
                      }`}
                    >
                      {store.store_status}
                    </span>
                    <p className="text-sm text-gray-500 mt-1">Zone: {store.store_zone}</p>
                  </div>
                  <div className="flex gap-1">
                    <button
                      onClick={() => {
                        setEditingStore(store)
                        setShowStoreModal(true)
                      }}
                      className="p-2 text-gray-400 hover:text-blue-600"
                      title="Edit store"
                    >
                      <Edit2 className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => setDeleteStoreConfirm(store)}
                      className="p-2 text-gray-400 hover:text-red-600"
                      title="Delete store"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </div>

              <div className="p-4">
                <div className="flex justify-between items-center mb-3">
                  <h3 className="font-medium text-gray-700">Inventory</h3>
                  <button
                    onClick={() => {
                      setEditingInventory({ storeId: store.store_id })
                      setShowInventoryModal(true)
                    }}
                    className="flex items-center gap-1 text-sm text-green-600 hover:text-green-700"
                  >
                    <Plus className="h-4 w-4" />
                    Add Item
                  </button>
                </div>
                {store.inventory_items.length === 0 ? (
                  <p className="text-gray-500 text-sm">No inventory data available</p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-gray-500 border-b">
                          <th className="pb-2">Product</th>
                          <th className="pb-2">Stock Level</th>
                          <th className="pb-2">Replenishment ETA</th>
                          <th className="pb-2 w-20">Actions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {store.inventory_items.slice(0, 5).map(item => (
                          <tr key={item.inventory_id} className="border-b last:border-0">
                            <td className="py-2 flex items-center gap-2">
                              <Package className="h-4 w-4 text-gray-400" />
                              {item.product_id}
                            </td>
                            <td className="py-2">
                              <span className={`flex items-center gap-1 ${(item.stock_level || 0) < 10 ? 'text-red-600' : 'text-gray-900'}`}>
                                {(item.stock_level || 0) < 10 && <AlertTriangle className="h-4 w-4" />}
                                {item.stock_level}
                              </span>
                            </td>
                            <td className="py-2 text-gray-500">{item.replenishment_eta || '-'}</td>
                            <td className="py-2">
                              <div className="flex gap-1">
                                <button
                                  onClick={() => {
                                    setEditingInventory({ inventory: item, storeId: store.store_id })
                                    setShowInventoryModal(true)
                                  }}
                                  className="p-1 text-gray-400 hover:text-blue-600"
                                  title="Edit"
                                >
                                  <Edit2 className="h-4 w-4" />
                                </button>
                                <button
                                  onClick={() => setDeleteInventoryConfirm(item)}
                                  className="p-1 text-gray-400 hover:text-red-600"
                                  title="Delete"
                                >
                                  <Trash2 className="h-4 w-4" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    {store.inventory_items.length > 5 && (
                      <button
                        onClick={() => setViewAllInventoryStore(store)}
                        className="mt-3 w-full px-4 py-2 text-sm text-green-600 hover:text-green-700 hover:bg-green-50 rounded-lg border border-green-200 transition-colors"
                      >
                        View All {store.inventory_items.length} Items
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <StoreFormModal
        isOpen={showStoreModal}
        onClose={() => {
          setShowStoreModal(false)
          setEditingStore(undefined)
        }}
        store={editingStore}
        onSave={handleSaveStore}
        isLoading={createStoreMutation.isPending || updateStoreMutation.isPending}
      />

      {editingInventory && (
        <InventoryFormModal
          isOpen={showInventoryModal}
          onClose={() => {
            setShowInventoryModal(false)
            setEditingInventory(null)
          }}
          inventory={editingInventory.inventory}
          storeId={editingInventory.storeId}
          products={products}
          onSave={handleSaveInventory}
          isLoading={createInventoryMutation.isPending || updateInventoryMutation.isPending}
        />
      )}

      {deleteStoreConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-sm mx-4">
            <h3 className="text-lg font-semibold mb-2">Delete Store</h3>
            <p className="text-gray-600 mb-4">
              Are you sure you want to delete <strong>{deleteStoreConfirm.store_name}</strong>? This will also delete all inventory items.
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setDeleteStoreConfirm(null)} className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50">
                Cancel
              </button>
              <button
                onClick={() => deleteStoreMutation.mutate(deleteStoreConfirm.store_id)}
                disabled={deleteStoreMutation.isPending}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
              >
                {deleteStoreMutation.isPending ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {deleteInventoryConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-sm mx-4">
            <h3 className="text-lg font-semibold mb-2">Delete Inventory Item</h3>
            <p className="text-gray-600 mb-4">
              Are you sure you want to delete inventory for <strong>{deleteInventoryConfirm.product_id}</strong>?
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setDeleteInventoryConfirm(null)} className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50">
                Cancel
              </button>
              <button
                onClick={() => deleteInventoryMutation.mutate(deleteInventoryConfirm.inventory_id)}
                disabled={deleteInventoryMutation.isPending}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
              >
                {deleteInventoryMutation.isPending ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {viewAllInventoryStore && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl max-h-[90vh] flex flex-col">
            <div className="flex justify-between items-center p-4 border-b">
              <div>
                <h2 className="text-lg font-semibold">All Inventory Items</h2>
                <p className="text-sm text-gray-600">{viewAllInventoryStore.store_name} - {viewAllInventoryStore.inventory_items.length} items</p>
              </div>
              <button
                onClick={() => setViewAllInventoryStore(null)}
                className="text-gray-500 hover:text-gray-700"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="flex-1 overflow-auto p-4">
              <table className="w-full text-sm">
                <thead className="sticky top-0 bg-white">
                  <tr className="text-left text-gray-500 border-b">
                    <th className="pb-2">Product</th>
                    <th className="pb-2">Stock Level</th>
                    <th className="pb-2">Replenishment ETA</th>
                    <th className="pb-2 w-20">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {viewAllInventoryStore.inventory_items.map(item => (
                    <tr key={item.inventory_id} className="border-b last:border-0">
                      <td className="py-2 flex items-center gap-2">
                        <Package className="h-4 w-4 text-gray-400" />
                        {item.product_id}
                      </td>
                      <td className="py-2">
                        <span className={`flex items-center gap-1 ${(item.stock_level || 0) < 10 ? 'text-red-600' : 'text-gray-900'}`}>
                          {(item.stock_level || 0) < 10 && <AlertTriangle className="h-4 w-4" />}
                          {item.stock_level}
                        </span>
                      </td>
                      <td className="py-2 text-gray-500">{item.replenishment_eta || '-'}</td>
                      <td className="py-2">
                        <div className="flex gap-1">
                          <button
                            onClick={() => {
                              setEditingInventory({ inventory: item, storeId: viewAllInventoryStore.store_id })
                              setShowInventoryModal(true)
                            }}
                            className="p-1 text-gray-400 hover:text-blue-600"
                            title="Edit"
                          >
                            <Edit2 className="h-4 w-4" />
                          </button>
                          <button
                            onClick={() => setDeleteInventoryConfirm(item)}
                            className="p-1 text-gray-400 hover:text-red-600"
                            title="Delete"
                          >
                            <Trash2 className="h-4 w-4" />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="p-4 border-t">
              <button
                onClick={() => setViewAllInventoryStore(null)}
                className="w-full px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
