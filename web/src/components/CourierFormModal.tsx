import { useState, useEffect } from 'react'
import { useZero, useQuery } from '@rocicorp/zero/react'
import { Schema } from '../schema'
import { CourierSchedule } from '../api/client'
import { X } from 'lucide-react'
import { Entity, aliasColumn, entity, placeholder } from '../label'

const vehicleTypes = ['BIKE', 'CAR', 'VAN']
const courierStatuses = ['AVAILABLE', 'ON_DELIVERY', 'OFF_SHIFT']

export interface CourierFormData {
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

interface CourierFormModalProps {
  isOpen: boolean
  onClose: () => void
  courier?: CourierSchedule
  onSave: (data: CourierFormData, isEdit: boolean) => void
  isLoading: boolean
}

export function CourierFormModal({
  isOpen,
  onClose,
  courier,
  onSave,
  isLoading,
}: CourierFormModalProps) {
  const [formData, setFormData] = useState<CourierFormData>(initialCourierForm)

  // 🔥 COLOCATED ZERO QUERY - Component queries its own stores data
  const z = useZero<Schema>()
  const [storesData] = useQuery(z.query.stores_mv.orderBy('store_id', 'asc'))

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
          <h2 className="text-lg font-semibold">{courier ? `Edit ${Entity('courier')}` : `Create ${Entity('courier')}`}</h2>
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
              <label className="block text-sm font-medium text-gray-700 mb-1">{Entity('courier')} ID *</label>
              <input
                type="text"
                required
                disabled={!!courier}
                value={formData.courier_id}
                onChange={e => setFormData({ ...formData, courier_id: e.target.value })}
                placeholder={placeholder("courier_code")}
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
              placeholder={placeholder("courier_name")}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">{aliasColumn('vehicle_type')} *</label>
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
              <label className="block text-sm font-medium text-gray-700 mb-1">Home {Entity('store')} *</label>
              <select
                required
                value={formData.home_store_id}
                onChange={e => setFormData({ ...formData, home_store_id: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Select a {entity('store')}...</option>
                {storesData.map(store => (
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
