import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { freshmartApi, triplesApi, CourierSchedule, TripleCreate } from '../api/client'
import { Truck, Bike, Car, Coffee, Plus, Edit2, Trash2, X } from 'lucide-react'

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
}: {
  isOpen: boolean
  onClose: () => void
  courier?: CourierSchedule
  onSave: (data: CourierFormData, isEdit: boolean) => void
  isLoading: boolean
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
              <label className="block text-sm font-medium text-gray-700 mb-1">Home Store ID *</label>
              <input
                type="text"
                required
                value={formData.home_store_id}
                onChange={e => setFormData({ ...formData, home_store_id: e.target.value })}
                placeholder="store:BK-01"
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
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

  const { data: couriers, isLoading, error } = useQuery({
    queryKey: ['couriers'],
    queryFn: () => freshmartApi.listCouriers().then(r => r.data),
  })

  const createCourierMutation = useMutation({
    mutationFn: async (data: CourierFormData) => {
      const courierId = `courier:${data.courier_id}`
      const triples: TripleCreate[] = [
        { subject_id: courierId, predicate: 'courier_name', object_value: data.courier_name, object_type: 'string' },
        { subject_id: courierId, predicate: 'vehicle_type', object_value: data.vehicle_type, object_type: 'string' },
        { subject_id: courierId, predicate: 'home_store', object_value: data.home_store_id, object_type: 'entity_ref' },
        { subject_id: courierId, predicate: 'courier_status', object_value: data.courier_status, object_type: 'string' },
      ]
      return triplesApi.createBatch(triples)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['couriers'] })
      setShowCourierModal(false)
      setEditingCourier(undefined)
    },
  })

  const updateCourierMutation = useMutation({
    mutationFn: async ({ courier, data }: { courier: CourierSchedule; data: CourierFormData }) => {
      const subjectInfo = await triplesApi.getSubject(courier.courier_id).then(r => r.data)
      const updates: Promise<unknown>[] = []
      const fields: { predicate: string; value: string; type: TripleCreate['object_type'] }[] = [
        { predicate: 'courier_name', value: data.courier_name, type: 'string' },
        { predicate: 'vehicle_type', value: data.vehicle_type, type: 'string' },
        { predicate: 'home_store', value: data.home_store_id, type: 'entity_ref' },
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
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['couriers'] })
      setShowCourierModal(false)
      setEditingCourier(undefined)
    },
  })

  const deleteCourierMutation = useMutation({
    mutationFn: (courierId: string) => triplesApi.deleteSubject(courierId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['couriers'] })
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

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Couriers & Schedule</h1>
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

      {error && (
        <div className="bg-red-50 text-red-700 p-4 rounded-lg">
          Error loading couriers. Make sure the API is running.
        </div>
      )}

      {couriers && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {couriers.map(courier => {
            const VehicleIcon = vehicleIcons[courier.vehicle_type || ''] || Truck
            return (
              <div key={courier.courier_id} className="bg-white rounded-lg shadow p-4">
                <div className="flex items-start justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-blue-100 rounded-lg">
                      <VehicleIcon className="h-5 w-5 text-blue-600" />
                    </div>
                    <div>
                      <h3 className="font-semibold text-gray-900">{courier.courier_name}</h3>
                      <p className="text-sm text-gray-500">{courier.vehicle_type}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                      statusColors[courier.courier_status || ''] || 'bg-gray-100'
                    }`}>
                      {courier.courier_status?.replace('_', ' ')}
                    </span>
                    <button
                      onClick={() => {
                        setEditingCourier(courier)
                        setShowCourierModal(true)
                      }}
                      className="p-1 text-gray-400 hover:text-blue-600"
                      title="Edit courier"
                    >
                      <Edit2 className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => setDeleteCourierConfirm(courier)}
                      className="p-1 text-gray-400 hover:text-red-600"
                      title="Delete courier"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </div>

                <div className="text-sm text-gray-600 mb-4">
                  <p>Home Store: {courier.home_store_id}</p>
                </div>

                {/* Tasks */}
                <div>
                  <h4 className="text-sm font-medium text-gray-700 mb-2">
                    Assigned Tasks ({courier.tasks.length})
                  </h4>
                  {courier.tasks.length === 0 ? (
                    <div className="flex items-center gap-2 text-gray-500 text-sm">
                      <Coffee className="h-4 w-4" />
                      No active tasks
                    </div>
                  ) : (
                    <div className="space-y-2">
                      {courier.tasks.map((task, idx) => (
                        <div
                          key={task.task_id || idx}
                          className="bg-gray-50 rounded p-2 text-sm"
                        >
                          <div className="flex justify-between">
                            <span className="font-medium">{task.order_id}</span>
                            <span className={`text-xs px-1.5 py-0.5 rounded ${
                              task.task_status === 'IN_PROGRESS' ? 'bg-blue-100 text-blue-700' :
                              task.task_status === 'COMPLETED' ? 'bg-green-100 text-green-700' :
                              'bg-gray-100 text-gray-700'
                            }`}>
                              {task.task_status}
                            </span>
                          </div>
                          {task.eta && (
                            <p className="text-gray-500 text-xs mt-1">
                              ETA: {task.eta.slice(11, 16)}
                            </p>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>
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
    </div>
  )
}
