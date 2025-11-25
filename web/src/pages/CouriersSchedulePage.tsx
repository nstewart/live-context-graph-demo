import { useState, useEffect, useMemo } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { triplesApi, CourierSchedule, TripleCreate, StoreInfo } from '../api/client'
import { useZero, useQuery } from '@rocicorp/zero/react'
import { Schema } from '../schema'
import { Truck, Bike, Car, Coffee, Plus, Edit2, Trash2, X, Search, ExternalLink, Wifi, WifiOff } from 'lucide-react'

const vehicleIcons: Record<string, typeof Truck> = {
  BIKE: Bike,
  CAR: Car,
  VAN: Truck,
}

const vehicleTypes = ['BIKE', 'CAR', 'VAN']
const courierStatuses = ['AVAILABLE', 'ON_DELIVERY', 'OFF_SHIFT']

const statusColors: Record<string, string> = {
  AVAILABLE: 'bg-green-100 text-green-800',
  ON_DELIVERY: 'bg-purple-100 text-purple-800',
  OFF_SHIFT: 'bg-gray-100 text-gray-800',
}

interface CourierFormData {
  courier_id: string
  courier_name: string
  vehicle_type: string
  home_store_id: string
  courier_status: string
}

const initialCourierForm: CourierFormData = {
  courier_id: '',
  courier_name: '',
  vehicle_type: 'CAR',
  home_store_id: '',
  courier_status: 'AVAILABLE',
}

function CourierFormModal({
  isOpen,
  onClose,
  courier,
  onSave,
  isLoading,
  stores,
}: {
  isOpen: boolean
  onClose: () => void
  courier?: CourierSchedule
  onSave: (data: CourierFormData, isEdit: boolean) => void
  isLoading: boolean
  stores: StoreInfo[]
}) {
  const [formData, setFormData] = useState<CourierFormData>(initialCourierForm)

  useEffect(() => {
    if (courier) {
      setFormData({
        courier_id: courier.courier_id.replace('courier:', ''),
        courier_name: courier.courier_name || '',
        vehicle_type: courier.vehicle_type || 'CAR',
        home_store_id: courier.home_store_id || '',
        courier_status: courier.courier_status || 'AVAILABLE',
      })
    } else {
      setFormData(initialCourierForm)
    }
  }, [courier])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-md mx-4">
        <div className="flex justify-between items-center p-4 border-b">
          <h2 className="text-lg font-semibold">{courier ? 'Edit Courier' : 'Create Courier'}</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            <X className="h-5 w-5" />
          </button>
        </div>
        <form
          onSubmit={e => {
            e.preventDefault()
            onSave(formData, !!courier)
          }}
          className="p-4 space-y-4"
        >
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Courier ID *</label>
              <input
                type="text"
                required
                disabled={!!courier}
                value={formData.courier_id}
                onChange={e => setFormData({ ...formData, courier_id: e.target.value })}
                placeholder="CR-01"
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Status *</label>
              <select
                required
                value={formData.courier_status}
                onChange={e => setFormData({ ...formData, courier_status: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                {courierStatuses.map(status => (
                  <option key={status} value={status}>
                    {status.replace('_', ' ')}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Name *</label>
            <input
              type="text"
              required
              value={formData.courier_name}
              onChange={e => setFormData({ ...formData, courier_name: e.target.value })}
              placeholder="John Smith"
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Vehicle Type *</label>
              <select
                required
                value={formData.vehicle_type}
                onChange={e => setFormData({ ...formData, vehicle_type: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                {vehicleTypes.map(type => (
                  <option key={type} value={type}>
                    {type}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Home Store *</label>
              <select
                required
                value={formData.home_store_id}
                onChange={e => setFormData({ ...formData, home_store_id: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
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
          <div className="flex justify-end gap-2 pt-4">
            <button type="button" onClick={onClose} className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50">
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {isLoading ? 'Saving...' : courier ? 'Update' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function CouriersSchedulePage() {
  const queryClient = useQueryClient()
  const [showCourierModal, setShowCourierModal] = useState(false)
  const [editingCourier, setEditingCourier] = useState<CourierSchedule | undefined>()
  const [deleteCourierConfirm, setDeleteCourierConfirm] = useState<CourierSchedule | null>(null)
  const [courierIdSearch, setCourierIdSearch] = useState('')
  const [viewTasksCourier, setViewTasksCourier] = useState<CourierSchedule | null>(null)

  // 🔥 ZERO - Real-time couriers data
  const z = useZero<Schema>()

  // Couriers sorted by courier_id (with tasks as JSON)
  const [couriersData] = useQuery(z.query.courier_schedule_mv.orderBy('courier_id', 'asc'))

  // Stores for the dropdown
  const [storesData] = useQuery(z.query.stores_mv.orderBy('store_id', 'asc'))

  // Convert Zero data to API types for modal compatibility
  const stores: StoreInfo[] = storesData.map(s => ({
    store_id: s.store_id,
    store_name: s.store_name,
    store_zone: s.store_zone,
    store_address: s.store_address,
    store_status: s.store_status,
    store_capacity_orders_per_hour: s.store_capacity_orders_per_hour,
    inventory_items: [],
  }))

  const zeroConnected = true // Zero handles connection internally

  // Map couriers data (already sorted by Zero)
  const couriers = useMemo(() => {
    return couriersData.map((courier) => ({
      courier_id: courier.courier_id,
      courier_name: courier.courier_name,
      home_store_id: courier.home_store_id,
      vehicle_type: courier.vehicle_type,
      courier_status: courier.courier_status,
      tasks: (courier.tasks as any[]) || [], // Tasks come as JSON array from courier_schedule_mv
    }))
  }, [couriersData])

  const isLoading = couriersData.length === 0

  // Client-side search filtering (Zero handles the base query)
  const searchedCourier = courierIdSearch
    ? couriers.find(c => c.courier_id.toLowerCase().includes(courierIdSearch.toLowerCase()))
    : undefined

  const createCourierMutation = useMutation({
    mutationFn: async (data: CourierFormData) => {
      const courierId = `courier:${data.courier_id}`
      const triples: TripleCreate[] = [
        { subject_id: courierId, predicate: 'courier_name', object_value: data.courier_name, object_type: 'string' },
        { subject_id: courierId, predicate: 'vehicle_type', object_value: data.vehicle_type, object_type: 'string' },
        { subject_id: courierId, predicate: 'courier_home_store', object_value: data.home_store_id, object_type: 'entity_ref' },
        { subject_id: courierId, predicate: 'courier_status', object_value: data.courier_status, object_type: 'string' },
      ]
      await triplesApi.createBatch(triples)
    },
    onSuccess: async () => {
      await queryClient.refetchQueries({ queryKey: ['couriers'] })
      setCourierIdSearch('') // Clear search filter
      setShowCourierModal(false)
      setEditingCourier(undefined)
    },
    onError: (error) => {
      console.error('Failed to create courier:', error)
      alert('Failed to create courier. Check the console for details.')
    },
  })

  const updateCourierMutation = useMutation({
    mutationFn: async ({ courier, data }: { courier: CourierSchedule; data: CourierFormData }) => {
      const subjectInfo = await triplesApi.getSubject(courier.courier_id).then(r => r.data)
      const updates: Promise<unknown>[] = []
      const fields: { predicate: string; value: string; type: TripleCreate['object_type'] }[] = [
        { predicate: 'courier_name', value: data.courier_name, type: 'string' },
        { predicate: 'vehicle_type', value: data.vehicle_type, type: 'string' },
        { predicate: 'courier_home_store', value: data.home_store_id, type: 'entity_ref' },
        { predicate: 'courier_status', value: data.courier_status, type: 'string' },
      ]
      for (const field of fields) {
        const existing = subjectInfo.triples.find(t => t.predicate === field.predicate)
        if (existing) {
          updates.push(triplesApi.update(existing.id, { object_value: field.value }))
        } else {
          updates.push(triplesApi.create({ subject_id: courier.courier_id, predicate: field.predicate, object_value: field.value, object_type: field.type }))
        }
      }
      await Promise.all(updates)
    },
    onSuccess: async () => {
      // Force refetch instead of just invalidate
      await queryClient.refetchQueries({ queryKey: ['couriers'] })
      setCourierIdSearch('') // Clear search filter
      setShowCourierModal(false)
      setEditingCourier(undefined)
    },
    onError: (error) => {
      console.error('Failed to update courier:', error)
      alert('Failed to update courier. Check the console for details.')
    },
  })

  const deleteCourierMutation = useMutation({
    mutationFn: async (courierId: string) => {
      await triplesApi.deleteSubject(courierId)
    },
    onSuccess: async () => {
      await queryClient.refetchQueries({ queryKey: ['couriers'] })
      setDeleteCourierConfirm(null)
    },
  })

  const handleSaveCourier = (data: CourierFormData, isEdit: boolean) => {
    if (isEdit && editingCourier) {
      updateCourierMutation.mutate({ courier: editingCourier, data })
    } else {
      createCourierMutation.mutate(data)
    }
  }

  // Filter couriers by ID search and merge with direct database search result
  const filteredCouriers = useMemo(() => {
    if (!couriers) return []

    let filtered = couriers

    // Client-side filter for partial matches
    if (courierIdSearch) {
      const searchLower = courierIdSearch.toLowerCase()
      filtered = couriers.filter(c =>
        c.courier_id.toLowerCase().includes(searchLower)
      )
    }

    // Add the searched courier if it was found via direct database query and not already in the list
    if (searchedCourier && !filtered.find(c => c.courier_id === searchedCourier.courier_id)) {
      filtered = [searchedCourier, ...filtered]
    }

    return filtered
  }, [couriers, courierIdSearch, searchedCourier])

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">Couriers & Schedule</h1>
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
          <p className="text-gray-600">View courier status and assigned tasks</p>
        </div>
        <button
          onClick={() => {
            setEditingCourier(undefined)
            setShowCourierModal(true)
          }}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <Plus className="h-4 w-4" />
          Add Courier
        </button>
      </div>

      {isLoading && (
        <div className="text-center py-8 text-gray-500">Loading couriers...</div>
      )}

      {couriers.length > 0 && (
        <>
          <div className="mb-4 space-y-2">
            <div className="relative max-w-md">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                value={courierIdSearch}
                onChange={e => setCourierIdSearch(e.target.value)}
                placeholder="Search by courier ID (e.g., C-0057)..."
                className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              />
            </div>
            {!courierIdSearch && couriers.length >= 1000 && (
              <div className="text-sm text-amber-600 bg-amber-50 px-3 py-2 rounded-lg max-w-md">
                ⚠️ Showing first 1000 couriers only. Use search to find specific couriers.
              </div>
            )}
            {courierIdSearch && searchedCourier && !couriers.find(c => c.courier_id === searchedCourier.courier_id) && (
              <div className="text-sm text-blue-600 bg-blue-50 px-3 py-2 rounded-lg max-w-md">
                ℹ️ Found courier from database (not in displayed list)
              </div>
            )}
          </div>

          <div className="bg-white rounded-lg shadow overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Courier
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Vehicle
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Home Store
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Assigned Tasks
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {filteredCouriers.map(courier => {
                    const VehicleIcon = vehicleIcons[courier.vehicle_type || ''] || Truck
                    const homeStore = stores.find(s => s.store_id === courier.home_store_id)
                    const activeTasks = courier.tasks.filter(t => t.task_status !== 'COMPLETED')
                    const completedTasks = courier.tasks.filter(t => t.task_status === 'COMPLETED')

                    return (
                      <tr key={courier.courier_id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 whitespace-nowrap">
                          <div className="flex items-center gap-3">
                            <div className="p-2 bg-blue-100 rounded-lg">
                              <VehicleIcon className="h-4 w-4 text-blue-600" />
                            </div>
                            <div>
                              <div className="text-sm font-medium text-gray-900">{courier.courier_name}</div>
                              <div className="text-xs text-gray-400">{courier.courier_id.replace('courier:', '')}</div>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                            statusColors[courier.courier_status || ''] || 'bg-gray-100'
                          }`}>
                            {courier.courier_status?.replace('_', ' ')}
                          </span>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <div className="text-sm text-gray-900">{courier.vehicle_type}</div>
                        </td>
                        <td className="px-4 py-3">
                          <div className="text-sm text-gray-900">
                            {homeStore ? homeStore.store_name : 'Not assigned'}
                          </div>
                          <div className="text-xs text-gray-500">{homeStore?.store_zone}</div>
                        </td>
                        <td className="px-4 py-3">
                          {courier.tasks.length === 0 ? (
                            <div className="flex items-center gap-2 text-gray-500 text-sm">
                              <Coffee className="h-4 w-4" />
                              <span>No active tasks</span>
                            </div>
                          ) : (
                            <div className="space-y-1">
                              <div className="flex items-center gap-2 text-sm">
                                <span className="font-medium text-gray-900">{activeTasks.length}</span>
                                <span className="text-gray-500">active</span>
                                {completedTasks.length > 0 && (
                                  <>
                                    <span className="text-gray-300">•</span>
                                    <span className="text-gray-500">{completedTasks.length} completed</span>
                                  </>
                                )}
                              </div>
                              {activeTasks.length > 0 && (
                                <div className="text-xs text-gray-500">
                                  Next: {activeTasks[0].order_id}
                                  {activeTasks[0].eta && (
                                    <span className="ml-1">@ {activeTasks[0].eta.slice(11, 16)}</span>
                                  )}
                                </div>
                              )}
                            </div>
                          )}
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-right text-sm font-medium">
                          <div className="flex items-center justify-end gap-2">
                            {courier.tasks.length > 0 && (
                              <button
                                onClick={() => setViewTasksCourier(courier)}
                                className="text-purple-600 hover:text-purple-900"
                                title="View all tasks"
                              >
                                <ExternalLink className="h-4 w-4" />
                              </button>
                            )}
                            <button
                              onClick={() => {
                                setEditingCourier(courier)
                                setShowCourierModal(true)
                              }}
                              className="text-blue-600 hover:text-blue-900"
                              title="Edit courier"
                            >
                              <Edit2 className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => setDeleteCourierConfirm(courier)}
                              className="text-red-600 hover:text-red-900"
                              title="Delete courier"
                            >
                              <Trash2 className="h-4 w-4" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      <CourierFormModal
        isOpen={showCourierModal}
        onClose={() => {
          setShowCourierModal(false)
          setEditingCourier(undefined)
        }}
        courier={editingCourier}
        onSave={handleSaveCourier}
        isLoading={createCourierMutation.isPending || updateCourierMutation.isPending}
        stores={stores}
      />

      {deleteCourierConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-sm mx-4">
            <h3 className="text-lg font-semibold mb-2">Delete Courier</h3>
            <p className="text-gray-600 mb-4">
              Are you sure you want to delete <strong>{deleteCourierConfirm.courier_name}</strong>? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setDeleteCourierConfirm(null)} className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50">
                Cancel
              </button>
              <button
                onClick={() => deleteCourierMutation.mutate(deleteCourierConfirm.courier_id)}
                disabled={deleteCourierMutation.isPending}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
              >
                {deleteCourierMutation.isPending ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* View All Tasks Modal */}
      {viewTasksCourier && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl w-full max-w-2xl mx-4 max-h-[80vh] overflow-hidden flex flex-col">
            <div className="flex justify-between items-center p-4 border-b">
              <div>
                <h2 className="text-lg font-semibold">
                  {viewTasksCourier.courier_name} - All Tasks
                </h2>
                <p className="text-sm text-gray-500">
                  {viewTasksCourier.courier_id.replace('courier:', '')} • {viewTasksCourier.tasks.length} total tasks
                </p>
              </div>
              <button onClick={() => setViewTasksCourier(null)} className="text-gray-500 hover:text-gray-700">
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="p-4 overflow-y-auto">
              {viewTasksCourier.tasks.length === 0 ? (
                <div className="text-center py-8 text-gray-500">
                  <Coffee className="h-8 w-8 mx-auto mb-2" />
                  <p>No tasks assigned</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {viewTasksCourier.tasks.map((task, idx) => (
                    <div
                      key={task.task_id || idx}
                      className="bg-gray-50 rounded-lg p-4 border border-gray-200"
                    >
                      <div className="flex justify-between items-start mb-2">
                        <div>
                          <h3 className="font-medium text-gray-900">{task.order_id}</h3>
                          {task.task_id && (
                            <p className="text-xs text-gray-500 mt-0.5">{task.task_id}</p>
                          )}
                        </div>
                        <span className={`px-2 py-1 rounded text-xs font-medium ${
                          task.task_status === 'IN_PROGRESS' ? 'bg-blue-100 text-blue-700' :
                          task.task_status === 'COMPLETED' ? 'bg-green-100 text-green-700' :
                          task.task_status === 'PENDING' ? 'bg-yellow-100 text-yellow-700' :
                          'bg-gray-100 text-gray-700'
                        }`}>
                          {task.task_status}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-3 text-sm">
                        {task.eta && (
                          <div>
                            <span className="text-gray-500">ETA:</span>
                            <span className="ml-2 text-gray-900">{task.eta.slice(0, 16).replace('T', ' ')}</span>
                          </div>
                        )}
                        {task.route_sequence !== undefined && task.route_sequence !== null && (
                          <div>
                            <span className="text-gray-500">Sequence:</span>
                            <span className="ml-2 text-gray-900">#{task.route_sequence}</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="p-4 border-t bg-gray-50">
              <button
                onClick={() => setViewTasksCourier(null)}
                className="w-full px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
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
