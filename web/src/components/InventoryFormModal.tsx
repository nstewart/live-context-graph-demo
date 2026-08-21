import { useState, useEffect } from 'react'
import { useZero, useQuery } from '@rocicorp/zero/react'
import { Schema } from '../schema'
import { StoreInventory } from '../api/client'
import { X } from 'lucide-react'
import { Entity, aliasColumn, aliasPredicate, entity, placeholder } from '../label'
export interface InventoryFormData {
  inventory_id: string
  store_id: string
  product_id: string
  stock_level: string
  replenishment_eta: string
}

const initialInventoryForm: InventoryFormData = {
  inventory_id: '',
  store_id: '',
  product_id: '',
  stock_level: '',
  replenishment_eta: '',
}

interface InventoryFormModalProps {
  isOpen: boolean
  onClose: () => void
  inventory?: StoreInventory
  storeId: string
  onSave: (data: InventoryFormData, isEdit: boolean) => void
  isLoading: boolean
}

export function InventoryFormModal({
  isOpen,
  onClose,
  inventory,
  storeId,
  onSave,
  isLoading,
}: InventoryFormModalProps) {
  const [formData, setFormData] = useState<InventoryFormData>({ ...initialInventoryForm, store_id: storeId })

  // 🔥 COLOCATED ZERO QUERY - Component queries its own products data
  const z = useZero<Schema>()
  const [products] = useQuery(z.query.products_mv.orderBy('product_id', 'asc'))

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
          <h2 className="text-lg font-semibold">{inventory ? `Edit ${Entity('inventory')}` : `Add ${Entity('inventory')}`}</h2>
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
              <label className="block text-sm font-medium text-gray-700 mb-1">{Entity('inventory')} ID *</label>
              <input
                type="text"
                required
                value={formData.inventory_id}
                onChange={e => setFormData({ ...formData, inventory_id: e.target.value })}
                placeholder={placeholder("inventory_code")}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500"
              />
            </div>
          )}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{Entity('product')} *</label>
            <select
              required
              value={formData.product_id}
              onChange={e => setFormData({ ...formData, product_id: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500"
            >
              <option value="">Select a {entity('product')}...</option>
              {products.map(p => (
                <option key={p.product_id} value={p.product_id}>
                  {p.product_name || 'Unknown'} ({p.product_id})
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{aliasColumn('stock_level')} *</label>
            <input
              type="number"
              required
              value={formData.stock_level}
              onChange={e => setFormData({ ...formData, stock_level: e.target.value })}
              placeholder="100"
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">{aliasPredicate('replenishment_eta')}</label>
            <input
              type="datetime-local"
              value={formData.replenishment_eta}
              onChange={e => setFormData({ ...formData, replenishment_eta: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500"
            />
          </div>
          <div className="flex justify-end gap-2 pt-4">
            <button type="button" onClick={onClose} className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50">
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading}
              className="px-4 py-2 bg-brand-600 text-white rounded-lg hover:bg-brand-700 disabled:opacity-50"
            >
              {isLoading ? 'Saving...' : inventory ? 'Update' : 'Add'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
