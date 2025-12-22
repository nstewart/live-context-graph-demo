import { useState, useMemo } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { triplesApi, CourierSchedule, TripleCreate } from '../api/client'
import { useZero, useQuery } from '@rocicorp/zero/react'
import { Schema } from '../schema'
import { Truck, Bike, Car, Coffee, Plus, Edit2, Trash2, X, Search, ExternalLink, Wifi, WifiOff, Users, Clock, Package, AlertTriangle } from 'lucide-react'
import { CourierFormModal, CourierFormData } from '../components/CourierFormModal'

type StoreMetrics = {
  store_id: string
  store_name: string
  store_zone: string
  total_couriers: number
  available_couriers: number
  busy_couriers: number
  off_shift_couriers: number
  orders_in_queue: number
  orders_picking: number
  orders_delivering: number
  utilization_pct: number
  health_status: 'HEALTHY' | 'WARNING' | 'CRITICAL'
}

function StoreCapacityCard({ metrics, onClick, isSelected }: { metrics: StoreMetrics; onClick?: () => void; isSelected?: boolean }) {
  const statusColors = {
    HEALTHY: { bg: 'bg-green-50 border-green-200', indicator: 'bg-green-500', text: 'text-green-700' },
    WARNING: { bg: 'bg-yellow-50 border-yellow-200', indicator: 'bg-yellow-500', text: 'text-yellow-700' },
    CRITICAL: { bg: 'bg-red-50 border-red-200', indicator: 'bg-red-500', text: 'text-red-700' },
  }

  const colors = statusColors[metrics.health_status]
  const availabilityPct = metrics.total_couriers > 0
    ? (metrics.available_couriers / metrics.total_couriers) * 100
    : 0

  return (
    <div
      className={`rounded-lg border-2 p-4 ${colors.bg} ${onClick ? 'cursor-pointer hover:shadow-md transition-shadow' : ''} ${isSelected ? 'ring-2 ring-blue-500 ring-offset-2' : ''}`}
      onClick={onClick}
    >
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="font-semibold text-gray-900">{metrics.store_name}</h3>
          <span className="text-xs text-gray-500">{metrics.store_zone}</span>
        </div>
        <div className={`w-3 h-3 rounded-full ${colors.indicator}`} title={metrics.health_status} />
      </div>

      {/* Courier Availability Bar */}
      <div className="mb-3">
        <div className="flex items-center justify-between text-sm mb-1">
          <span className="text-gray-600 flex items-center gap-1">
            <Users className="h-3.5 w-3.5" />
            Couriers
          </span>
          <span className="font-medium">
            {metrics.available_couriers}/{metrics.total_couriers} available
          </span>
        </div>
        <div className="h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            className="h-full bg-green-500 transition-all duration-300"
            style={{ width: `${availabilityPct}%` }}
          />
        </div>
      </div>

      {/* Stats Grid */}
      <div className="grid grid-cols-2 gap-2 text-sm">
        <div className="flex items-center gap-1.5">
          <Package className="h-3.5 w-3.5 text-gray-400" />
          <span className="text-gray-600">Queue:</span>
          <span className="font-medium">{metrics.orders_in_queue}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Clock className="h-3.5 w-3.5 text-gray-400" />
          <span className="text-gray-600">Picking:</span>
          <span className="font-medium">{metrics.orders_picking}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <Truck className="h-3.5 w-3.5 text-gray-400" />
          <span className="text-gray-600">Delivering:</span>
          <span className="font-medium">{metrics.orders_delivering}</span>
        </div>
        <div className="flex items-center gap-1.5">
          <AlertTriangle className="h-3.5 w-3.5 text-gray-400" />
          <span className="text-gray-600">Util:</span>
          <span className={`font-medium ${metrics.utilization_pct >= 80 ? 'text-red-600' : metrics.utilization_pct >= 50 ? 'text-yellow-600' : 'text-green-600'}`}>
            {metrics.utilization_pct.toFixed(0)}%
          </span>
        </div>
      </div>
    </div>
  )
}

const vehicleIcons: Record<string, typeof Truck> = {
  BIKE: Bike,
  CAR: Car,
  VAN: Truck,
}

const statusColors: Record<string, string> = {
  AVAILABLE: 'bg-green-100 text-green-800',
  ON_DELIVERY: 'bg-purple-100 text-purple-800',
  OFF_SHIFT: 'bg-gray-100 text-gray-800',
}



export default function CouriersSchedulePage() {
  const queryClient = useQueryClient()
  const [showCourierModal, setShowCourierModal] = useState(false)
  const [editingCourier, setEditingCourier] = useState<CourierSchedule | undefined>()
  const [deleteCourierConfirm, setDeleteCourierConfirm] = useState<CourierSchedule | null>(null)
  const [courierIdSearch, setCourierIdSearch] = useState('')
  const [viewTasksCourier, setViewTasksCourier] = useState<CourierSchedule | null>(null)
  const [selectedStoreId, setSelectedStoreId] = useState<string | null>(null)

  // 🔥 ZERO - Real-time couriers data
  const z = useZero<Schema>()

  // Couriers sorted by courier_id (with tasks as JSON)
  const [couriersData] = useQuery(z.query.courier_schedule_mv.orderBy('courier_id', 'asc'))

  // Stores for home store lookup (still needed for display in table)
  const [storesData] = useQuery(z.query.stores_mv.orderBy('store_id', 'asc'))

  // Orders for queue/picking/delivering counts
  const [ordersData] = useQuery(z.query.orders_with_lines_mv)

  const zeroConnected = true // Zero handles connection internally

  // Compute store metrics from courier and order data
  const storeMetrics: StoreMetrics[] = useMemo(() => {
    if (storesData.length === 0) return []

    return storesData.map((store) => {
      // Count couriers by status for this store
      const storeCouriers = couriersData.filter(c => c.home_store_id === store.store_id)
      const total = storeCouriers.length
      const available = storeCouriers.filter(c => c.courier_status === 'AVAILABLE').length
      const busy = storeCouriers.filter(c => c.courier_status === 'PICKING' || c.courier_status === 'DELIVERING' || c.courier_status === 'ON_DELIVERY').length
      const offShift = storeCouriers.filter(c => c.courier_status === 'OFF_SHIFT').length

      // Count orders by status for this store
      const storeOrders = ordersData.filter(o => o.store_id === store.store_id)
      const inQueue = storeOrders.filter(o => o.order_status === 'CREATED').length
      const picking = storeOrders.filter(o => o.order_status === 'PICKING').length
      const delivering = storeOrders.filter(o => o.order_status === 'OUT_FOR_DELIVERY').length

      // Calculate utilization
      const utilization = total > 0 ? (busy / total) * 100 : 0

      // Determine health status
      let health: 'HEALTHY' | 'WARNING' | 'CRITICAL' = 'HEALTHY'
      if (available === 0 && inQueue > 0) {
        health = 'CRITICAL'
      } else if (utilization >= 80 || (inQueue > available * 5)) {
        health = 'WARNING'
      }

      return {
        store_id: store.store_id,
        store_name: store.store_name || store.store_id,
        store_zone: store.store_zone || '',
        total_couriers: total,
        available_couriers: available,
        busy_couriers: busy,
        off_shift_couriers: offShift,
        orders_in_queue: inQueue,
        orders_picking: picking,
        orders_delivering: delivering,
        utilization_pct: utilization,
        health_status: health,
      }
    }).sort((a, b) => a.store_name.localeCompare(b.store_name))
  }, [storesData, couriersData, ordersData])

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

  // Filter couriers by ID search, store filter, and merge with direct database search result
  const filteredCouriers = useMemo(() => {
    if (!couriers) return []

    let filtered = couriers

    // Filter by selected store
    if (selectedStoreId) {
      filtered = filtered.filter(c => c.home_store_id === selectedStoreId)
    }

    // Client-side filter for partial matches
    if (courierIdSearch) {
      const searchLower = courierIdSearch.toLowerCase()
      filtered = filtered.filter(c =>
        c.courier_id.toLowerCase().includes(searchLower)
      )
    }

    // Add the searched courier if it was found via direct database query and not already in the list
    if (searchedCourier && !filtered.find(c => c.courier_id === searchedCourier.courier_id)) {
      filtered = [searchedCourier, ...filtered]
    }

    return filtered
  }, [couriers, courierIdSearch, searchedCourier, selectedStoreId])

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

      {/* Store Capacity Cards */}
      {storeMetrics.length > 0 && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Store Demand vs Capacity</h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {storeMetrics.map((metrics) => (
              <StoreCapacityCard
                key={metrics.store_id}
                metrics={metrics}
                isSelected={selectedStoreId === metrics.store_id}
                onClick={() => {
                  setSelectedStoreId(selectedStoreId === metrics.store_id ? null : metrics.store_id)
                  setCourierIdSearch('')
                }}
              />
            ))}
          </div>
        </div>
      )}

      {couriers.length > 0 && (
        <>
          {/* Active Store Filter */}
          {selectedStoreId && (
            <div className="mb-4 flex items-center gap-2 text-sm">
              <span className="text-gray-600">Filtering by:</span>
              <span className="inline-flex items-center gap-1 px-3 py-1 bg-blue-100 text-blue-800 rounded-full font-medium">
                {storesData.find(s => s.store_id === selectedStoreId)?.store_name || selectedStoreId}
                <button
                  onClick={() => setSelectedStoreId(null)}
                  className="ml-1 hover:text-blue-900"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              </span>
              <span className="text-gray-500">({filteredCouriers.length} couriers)</span>
            </div>
          )}

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
                    const homeStore = storesData.find(s => s.store_id === courier.home_store_id)
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

      {/* Courier Modal - queries its own stores data */}
      <CourierFormModal
        isOpen={showCourierModal}
        onClose={() => {
          setShowCourierModal(false)
          setEditingCourier(undefined)
        }}
        courier={editingCourier}
        onSave={handleSaveCourier}
        isLoading={createCourierMutation.isPending || updateCourierMutation.isPending}
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
                        {task.wait_time_minutes !== undefined && task.wait_time_minutes !== null ? (
                          <div>
                            <span className="text-gray-500">Wait:</span>
                            <span className="ml-2 text-gray-900">{Math.round(task.wait_time_minutes)}m</span>
                          </div>
                        ) : task.order_created_at && (
                          <div>
                            <span className="text-gray-500">Wait:</span>
                            <span className="ml-2 text-gray-900">
                              {Math.round((Date.now() - new Date(task.order_created_at).getTime()) / 60000)}m
                            </span>
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
