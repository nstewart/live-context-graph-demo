import { useState, useEffect, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { ontologyApi, OntologyProperty, OntologyPropertyCreate, OntologyClass } from '../api/client'
import { ArrowRight, Plus, Edit2, Trash2, X, ChevronDown, ChevronRight, Database } from 'lucide-react'
import { OntologyGraph } from '../components/OntologyGraph'
import { aliasClass, aliasPredicate } from '../label'
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
  presetDomainClassId,
}: {
  isOpen: boolean
  onClose: () => void
  property?: OntologyProperty
  onSave: (data: PropertyFormData, isEdit: boolean) => void
  isLoading: boolean
  classes: OntologyClass[]
  presetDomainClassId?: number
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
      setFormData({
        ...initialFormData,
        domain_class_id: presetDomainClassId || '',
      })
    }
  }, [property, presetDomainClassId])

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
                disabled={!!presetDomainClassId && !property}
              >
                <option value="">Select a class...</option>
                {classes.map(cls => (
                  <option key={cls.id} value={cls.id}>
                    {aliasClass(cls.class_name)}
                  </option>
                ))}
              </select>
              {presetDomainClassId && !property && (
                <p className="text-xs text-gray-500 mt-1">
                  Domain class is preset for this section
                </p>
              )}
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
                    {aliasClass(cls.class_name)}
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

export default function OntologyPage() {
  const queryClient = useQueryClient()

  // Classes state
  const [showClassForm, setShowClassForm] = useState(false)
  const [classFormData, setClassFormData] = useState({ class_name: '', prefix: '', description: '' })

  // Properties state
  const [showPropertyModal, setShowPropertyModal] = useState(false)
  const [editingProperty, setEditingProperty] = useState<OntologyProperty | undefined>()
  const [deleteConfirm, setDeleteConfirm] = useState<OntologyProperty | null>(null)
  const [expandedClasses, setExpandedClasses] = useState<Set<string>>(new Set())
  const [presetDomainClassId, setPresetDomainClassId] = useState<number | undefined>()

  // Queries
  const { data: classes, isLoading: classesLoading, error: classesError } = useQuery({
    queryKey: ['ontology-classes'],
    queryFn: () => ontologyApi.listClasses().then(r => r.data),
  })

  const { data: properties, isLoading: propertiesLoading, error: propertiesError } = useQuery({
    queryKey: ['ontology-properties'],
    queryFn: () => ontologyApi.listProperties().then(r => r.data),
  })

  // Group properties by domain class
  const groupedProperties = useMemo(() => {
    if (!properties) return {}

    const grouped: Record<string, OntologyProperty[]> = {}
    properties.forEach(prop => {
      const className = prop.domain_class_name || 'Unknown'
      if (!grouped[className]) {
        grouped[className] = []
      }
      grouped[className].push(prop)
    })

    Object.keys(grouped).forEach(className => {
      grouped[className].sort((a, b) => a.prop_name.localeCompare(b.prop_name))
    })

    return grouped
  }, [properties])

  // Expand all classes by default on first load
  useEffect(() => {
    if (properties && expandedClasses.size === 0) {
      setExpandedClasses(new Set(Object.keys(groupedProperties)))
    }
  }, [properties, groupedProperties, expandedClasses.size])

  const toggleClass = (className: string) => {
    setExpandedClasses(prev => {
      const newSet = new Set(prev)
      if (newSet.has(className)) {
        newSet.delete(className)
      } else {
        newSet.add(className)
      }
      return newSet
    })
  }

  // Class mutations
  const createClassMutation = useMutation({
    mutationFn: (data: typeof classFormData) => ontologyApi.createClass(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ontology-classes'] })
      setShowClassForm(false)
      setClassFormData({ class_name: '', prefix: '', description: '' })
    },
  })

  // Property mutations
  const createPropertyMutation = useMutation({
    mutationFn: (data: OntologyPropertyCreate) => ontologyApi.createProperty(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ontology-properties'] })
      setShowPropertyModal(false)
      setEditingProperty(undefined)
    },
    onError: (error) => {
      console.error('Failed to create property:', error)
      alert('Failed to create property. Check the console for details.')
    },
  })

  const updatePropertyMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<OntologyPropertyCreate> }) =>
      ontologyApi.updateProperty(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ontology-properties'] })
      setShowPropertyModal(false)
      setEditingProperty(undefined)
    },
    onError: (error) => {
      console.error('Failed to update property:', error)
      alert('Failed to update property. Check the console for details.')
    },
  })

  const deletePropertyMutation = useMutation({
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

  const handleClassSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createClassMutation.mutate(classFormData)
  }

  const handlePropertySave = (formData: PropertyFormData, isEdit: boolean) => {
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
      updatePropertyMutation.mutate({ id: editingProperty.id, data })
    } else {
      createPropertyMutation.mutate(data)
    }
  }

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Ontology</h1>
        <p className="text-gray-600">Define entity types and their properties in the knowledge graph</p>
      </div>

      {/* Schema Visualization */}
      <div className="bg-white rounded-lg shadow p-6 mb-8">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Schema Visualization</h2>
        <OntologyGraph />
      </div>

      {/* Classes Section */}
      <div className="mb-8">
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Classes</h2>
          <button
            onClick={() => setShowClassForm(true)}
            className="flex items-center gap-2 px-3 py-1.5 bg-brand-600 text-white text-sm rounded-lg hover:bg-brand-700"
          >
            <Plus className="h-4 w-4" />
            Add Class
          </button>
        </div>

        {/* Add Class form */}
        {showClassForm && (
          <div className="bg-white rounded-lg shadow p-4 mb-4">
            <h3 className="font-semibold mb-4">New Ontology Class</h3>
            <form onSubmit={handleClassSubmit} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Class Name</label>
                  <input
                    type="text"
                    value={classFormData.class_name}
                    onChange={e => setClassFormData({ ...classFormData, class_name: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500"
                  placeholder={/* label-lint-ok: a fixed ontology class name, not a display word */ "e.g., Customer"}
                    required
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Prefix</label>
                  <input
                    type="text"
                    value={classFormData.prefix}
                    onChange={e => setClassFormData({ ...classFormData, prefix: e.target.value })}
                    className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500"
                  placeholder={/* label-lint-ok: a fixed subject prefix, not a display word */ "e.g., customer"}
                    required
                  />
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                <textarea
                  value={classFormData.description}
                  onChange={e => setClassFormData({ ...classFormData, description: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-brand-500"
                  rows={2}
                />
              </div>
              <div className="flex gap-2">
                <button
                  type="submit"
                  disabled={createClassMutation.isPending}
                  className="px-4 py-2 bg-brand-600 text-white rounded-lg hover:bg-brand-700 disabled:opacity-50"
                >
                  {createClassMutation.isPending ? 'Creating...' : 'Create Class'}
                </button>
                <button
                  type="button"
                  onClick={() => setShowClassForm(false)}
                  className="px-4 py-2 border rounded-lg hover:bg-gray-50"
                >
                  Cancel
                </button>
              </div>
            </form>
          </div>
        )}

        {classesLoading && <div className="text-center py-4 text-gray-500">Loading classes...</div>}
        {classesError && <div className="bg-red-50 text-red-700 p-4 rounded-lg">Error loading classes</div>}

        {classes && (
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Class</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Prefix</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Description</th>
                  <th className="px-4 py-3 text-left text-sm font-medium text-gray-500">Created</th>
                </tr>
              </thead>
              <tbody className="divide-y">
                {classes.map(cls => (
                  <tr key={cls.id} className="hover:bg-gray-50">
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <Database className="h-4 w-4 text-green-600" />
                        <span className="font-medium">{aliasClass(cls.class_name)}</span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <code className="text-sm bg-gray-100 px-2 py-0.5 rounded">{cls.prefix}</code>
                    </td>
                    <td className="px-4 py-3 text-gray-600">{cls.description || '-'}</td>
                    <td className="px-4 py-3 text-sm text-gray-500">
                      {new Date(cls.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Properties Section */}
      <div>
        <div className="flex justify-between items-center mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Properties</h2>
        </div>

        {propertiesLoading && <div className="text-center py-4 text-gray-500">Loading properties...</div>}
        {propertiesError && <div className="bg-red-50 text-red-700 p-4 rounded-lg">Error loading properties</div>}

        {properties && properties.length === 0 && (
          <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
            No properties defined yet. Click "Add Property" on a class to create one.
          </div>
        )}

        {properties && properties.length > 0 && (
          <div className="space-y-4">
            {Object.keys(groupedProperties).sort((a, b) => aliasClass(a).localeCompare(aliasClass(b))).map(className => {
              const classProperties = groupedProperties[className]
              const isExpanded = expandedClasses.has(className)
              const classInfo = classes?.find(c => c.class_name === className)

              return (
                <div
                  key={className}
                  className="bg-white rounded-lg shadow overflow-hidden"
                >
                  {/* Class Header */}
                  <div className="px-4 py-3 bg-gradient-to-r from-green-50 to-white border-b">
                    <div className="flex items-start justify-between gap-4">
                      <button
                        onClick={() => toggleClass(className)}
                        className="flex items-start gap-3 hover:opacity-70 transition-opacity flex-1"
                      >
                        <div className="pt-1">
                          {isExpanded ? (
                            <ChevronDown className="h-5 w-5 text-gray-500" />
                          ) : (
                            <ChevronRight className="h-5 w-5 text-gray-500" />
                          )}
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <span className="text-lg font-semibold text-gray-900">{aliasClass(className)}</span>
                            <span className="text-xs text-gray-500">Prefix:</span>
                            <span className="text-xs bg-green-100 text-green-700 px-2 py-0.5 rounded font-mono">
                              {classInfo?.prefix || '?'}:
                            </span>
                            <span className="text-sm text-gray-500">
                              ({classProperties.length} {classProperties.length === 1 ? 'property' : 'properties'})
                            </span>
                          </div>
                          {classInfo?.description && (
                            <p className="text-sm text-gray-600 mt-0.5">
                              {classInfo.description}
                            </p>
                          )}
                        </div>
                      </button>
                      <button
                        onClick={() => {
                          setEditingProperty(undefined)
                          setPresetDomainClassId(classInfo?.id)
                          setShowPropertyModal(true)
                        }}
                        className="flex items-center gap-1.5 px-3 py-1.5 text-sm bg-blue-600 text-white rounded-lg hover:bg-blue-700 flex-shrink-0"
                        title={`Add property to ${aliasClass(className)}`}
                      >
                        <Plus className="h-4 w-4" />
                        Add Property
                      </button>
                    </div>
                  </div>

                  {/* Properties Table */}
                  {isExpanded && (
                    <table className="w-full">
                      <thead className="bg-gray-50">
                        <tr>
                          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Property</th>
                          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Range</th>
                          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Flags</th>
                          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Description</th>
                          <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">Actions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {classProperties.map(prop => (
                          <tr key={prop.id} className="hover:bg-gray-50">
                            <td className="px-4 py-3">
                              <code className="text-sm font-medium text-blue-600">{aliasPredicate(prop.prop_name)}</code>
                            </td>
                            <td className="px-4 py-3">
                              <div className="flex items-center gap-1">
                                {prop.range_class_name ? (
                                  <>
                                    <ArrowRight className="h-4 w-4 text-gray-400" />
                                    <span className="bg-purple-100 text-purple-700 px-2 py-0.5 rounded text-sm">
                                      {aliasClass(prop.range_class_name)}
                                    </span>
                                  </>
                                ) : (
                                  <span className="bg-gray-100 text-gray-700 px-2 py-0.5 rounded text-sm">
                                    {prop.range_kind}
                                  </span>
                                )}
                              </div>
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
                                    setShowPropertyModal(true)
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
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* Property Form Modal */}
      <PropertyFormModal
        isOpen={showPropertyModal}
        onClose={() => {
          setShowPropertyModal(false)
          setEditingProperty(undefined)
          setPresetDomainClassId(undefined)
        }}
        property={editingProperty}
        onSave={handlePropertySave}
        isLoading={createPropertyMutation.isPending || updatePropertyMutation.isPending}
        classes={classes || []}
        presetDomainClassId={presetDomainClassId}
      />

      {/* Delete Confirmation Modal */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-sm mx-4">
            <h3 className="text-lg font-semibold mb-2">Delete Property</h3>
            <p className="text-gray-600 mb-4">
              Are you sure you want to delete <strong>{aliasPredicate(deleteConfirm.prop_name)}</strong>? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setDeleteConfirm(null)} className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50">
                Cancel
              </button>
              <button
                onClick={() => deletePropertyMutation.mutate(deleteConfirm.id)}
                disabled={deletePropertyMutation.isPending}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
              >
                {deletePropertyMutation.isPending ? 'Deleting...' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
