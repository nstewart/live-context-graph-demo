import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ontologyApi, OntologyProperty, OntologyPropertyCreate, OntologyClass } from '../api/client'
import { ArrowRight, Plus, Edit2, Trash2, X } from 'lucide-react'

const rangeKindOptions = ['string', 'int', 'float', 'bool', 'timestamp', 'date', 'entity_ref']

interface PropertyFormData {
  prop_name: string
  domain_class_id: number | ''
  range_kind: string
  range_class_id: number | '' | null
  is_multi_valued: boolean
  is_required: boolean
  description: string
}

const initialFormData: PropertyFormData = {
  prop_name: '',
  domain_class_id: '',
  range_kind: 'string',
  range_class_id: null,
  is_multi_valued: false,
  is_required: false,
  description: '',
}

function PropertyFormModal({
  isOpen,
  onClose,
  property,
  onSave,
  isLoading,
  classes,
}: {
  isOpen: boolean
  onClose: () => void
  property?: OntologyProperty
  onSave: (data: PropertyFormData, isEdit: boolean) => void
  isLoading: boolean
  classes: OntologyClass[]
}) {
  const [formData, setFormData] = useState<PropertyFormData>(initialFormData)

  useEffect(() => {
    if (property) {
      setFormData({
        prop_name: property.prop_name,
        domain_class_id: property.domain_class_id,
        range_kind: property.range_kind,
        range_class_id: property.range_class_id,
        is_multi_valued: property.is_multi_valued,
        is_required: property.is_required,
        description: property.description || '',
      })
    } else {
      setFormData(initialFormData)
    }
  }, [property])

  if (!isOpen) return null

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4">
        <div className="flex justify-between items-center p-4 border-b">
          <h2 className="text-lg font-semibold">{property ? 'Edit Property' : 'Create Property'}</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            <X className="h-5 w-5" />
          </button>
        </div>
        <form
          onSubmit={e => {
            e.preventDefault()
            onSave(formData, !!property)
          }}
          className="p-4 space-y-4"
        >
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Property Name *</label>
            <input
              type="text"
              required
              value={formData.prop_name}
              onChange={e => setFormData({ ...formData, prop_name: e.target.value })}
              placeholder="order_status"
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Domain Class *</label>
              <select
                required
                value={formData.domain_class_id}
                onChange={e => setFormData({ ...formData, domain_class_id: e.target.value ? parseInt(e.target.value) : '' })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Select a class...</option>
                {classes.map(cls => (
                  <option key={cls.id} value={cls.id}>
                    {cls.class_name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Range Kind *</label>
              <select
                required
                value={formData.range_kind}
                onChange={e => setFormData({
                  ...formData,
                  range_kind: e.target.value,
                  range_class_id: e.target.value === 'entity_ref' ? formData.range_class_id : null
                })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                {rangeKindOptions.map(kind => (
                  <option key={kind} value={kind}>
                    {kind}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {formData.range_kind === 'entity_ref' && (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Range Class *</label>
              <select
                required
                value={formData.range_class_id || ''}
                onChange={e => setFormData({ ...formData, range_class_id: e.target.value ? parseInt(e.target.value) : null })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
              >
                <option value="">Select a class...</option>
                {classes.map(cls => (
                  <option key={cls.id} value={cls.id}>
                    {cls.class_name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <input
              type="text"
              value={formData.description}
              onChange={e => setFormData({ ...formData, description: e.target.value })}
              placeholder="Brief description of the property"
              className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="flex gap-4">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={formData.is_required}
                onChange={e => setFormData({ ...formData, is_required: e.target.checked })}
                className="rounded border-gray-300"
              />
              <span className="text-sm text-gray-700">Required</span>
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={formData.is_multi_valued}
                onChange={e => setFormData({ ...formData, is_multi_valued: e.target.checked })}
                className="rounded border-gray-300"
              />
              <span className="text-sm text-gray-700">Multi-valued</span>
            </label>
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
              {isLoading ? 'Saving...' : property ? 'Update' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function OntologyPropertiesPage() {
  const queryClient = useQueryClient()
  const [showModal, setShowModal] = useState(false)
  const [editingProperty, setEditingProperty] = useState<OntologyProperty | undefined>()
  const [deleteConfirm, setDeleteConfirm] = useState<OntologyProperty | null>(null)

  const { data: properties, isLoading, error } = useQuery({
    queryKey: ['ontology-properties'],
    queryFn: () => ontologyApi.listProperties().then(r => r.data),
  })

  const { data: classes = [] } = useQuery({
    queryKey: ['ontology-classes'],
    queryFn: () => ontologyApi.listClasses().then(r => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (data: OntologyPropertyCreate) => ontologyApi.createProperty(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ontology-properties'] })
      setShowModal(false)
      setEditingProperty(undefined)
    },
    onError: (error) => {
      console.error('Failed to create property:', error)
      alert('Failed to create property. Check the console for details.')
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<OntologyPropertyCreate> }) =>
      ontologyApi.updateProperty(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ontology-properties'] })
      setShowModal(false)
      setEditingProperty(undefined)
    },
    onError: (error) => {
      console.error('Failed to update property:', error)
      alert('Failed to update property. Check the console for details.')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => ontologyApi.deleteProperty(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ontology-properties'] })
      setDeleteConfirm(null)
    },
    onError: (error) => {
      console.error('Failed to delete property:', error)
      alert('Failed to delete property. Check the console for details.')
    },
  })

  const handleSave = (formData: PropertyFormData, isEdit: boolean) => {
    const data: OntologyPropertyCreate = {
      prop_name: formData.prop_name,
      domain_class_id: formData.domain_class_id as number,
      range_kind: formData.range_kind,
      range_class_id: formData.range_kind === 'entity_ref' ? (formData.range_class_id as number) : null,
      is_multi_valued: formData.is_multi_valued,
      is_required: formData.is_required,
      description: formData.description || null,
    }

    if (isEdit && editingProperty) {
      updateMutation.mutate({ id: editingProperty.id, data })
    } else {
      createMutation.mutate(data)
    }
  }

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Ontology Properties</h1>
          <p className="text-gray-600">Define relationships and attributes for entity classes</p>
        </div>
        <button
          onClick={() => {
            setEditingProperty(undefined)
            setShowModal(true)
          }}
          className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
        >
          <Plus className="h-4 w-4" />
          Add Property
        </button>
      </div>

      {isLoading && <div className="text-center py-8 text-gray-500">Loading...</div>}
      {error && <div className="bg-red-50 text-red-700 p-4 rounded-lg">Error loading properties</div>}

      {properties && (
        <div className="bg-white rounded-lg shadow overflow-hidden">
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Property</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Domain</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Range</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Flags</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Description</th>
                <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {properties.map(prop => (
                <tr key={prop.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3">
                    <code className="text-sm font-medium text-blue-600">{prop.prop_name}</code>
                  </td>
                  <td className="px-4 py-3">
                    <span className="inline-flex items-center gap-1 text-sm">
                      <span className="bg-green-100 text-green-700 px-2 py-0.5 rounded">
                        {prop.domain_class_name}
                      </span>
                      <ArrowRight className="h-4 w-4 text-gray-400" />
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {prop.range_class_name ? (
                      <span className="bg-purple-100 text-purple-700 px-2 py-0.5 rounded text-sm">
                        {prop.range_class_name}
                      </span>
                    ) : (
                      <span className="bg-gray-100 text-gray-700 px-2 py-0.5 rounded text-sm">
                        {prop.range_kind}
                      </span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      {prop.is_required && (
                        <span className="text-xs bg-red-100 text-red-700 px-1.5 py-0.5 rounded">required</span>
                      )}
                      {prop.is_multi_valued && (
                        <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded">multi</span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-600 max-w-xs truncate">
                    {prop.description || '-'}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      <button
                        onClick={() => {
                          setEditingProperty(prop)
                          setShowModal(true)
                        }}
                        className="p-1 text-gray-400 hover:text-blue-600"
                        title="Edit property"
                      >
                        <Edit2 className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => setDeleteConfirm(prop)}
                        className="p-1 text-gray-400 hover:text-red-600"
                        title="Delete property"
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
      )}

      <PropertyFormModal
        isOpen={showModal}
        onClose={() => {
          setShowModal(false)
          setEditingProperty(undefined)
        }}
        property={editingProperty}
        onSave={handleSave}
        isLoading={createMutation.isPending || updateMutation.isPending}
        classes={classes}
      />

      {deleteConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-sm mx-4">
            <h3 className="text-lg font-semibold mb-2">Delete Property</h3>
            <p className="text-gray-600 mb-4">
              Are you sure you want to delete <strong>{deleteConfirm.prop_name}</strong>? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setDeleteConfirm(null)} className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50">
                Cancel
              </button>
              <button
                onClick={() => deleteMutation.mutate(deleteConfirm.id)}
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
