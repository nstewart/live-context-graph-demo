import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState, useMemo, useEffect } from 'react'
import { triplesApi, ontologyApi, Triple, TripleCreate, OntologyProperty, OntologyClass } from '../api/client'
import { Search, ChevronRight, Filter, Plus, Edit2, Trash2, X } from 'lucide-react'

interface TripleFormData {
  subject_id: string
  predicate: string
  object_value: string
  object_type: 'string' | 'integer' | 'decimal' | 'boolean' | 'datetime' | 'entity_ref'
}

const initialFormData: TripleFormData = {
  subject_id: '',
  predicate: '',
  object_value: '',
  object_type: 'string',
}

function TripleFormModal({
  isOpen,
  onClose,
  triple,
  subjectId,
  onSave,
  isLoading,
  properties,
  classes,
  subjects,
}: {
  isOpen: boolean
  onClose: () => void
  triple?: Triple
  subjectId?: string
  onSave: (data: TripleFormData, isEdit: boolean, tripleId?: number) => void
  isLoading: boolean
  properties: OntologyProperty[]
  classes: OntologyClass[]
  subjects: string[]
}) {
  const [formData, setFormData] = useState<TripleFormData>(initialFormData)

  // Get class prefixes for subject ID validation
  const classPrefixes = useMemo(() => {
    return classes.map(c => c.prefix)
  }, [classes])

  // Get properties for selected subject's class
  const availableProperties = useMemo(() => {
    if (!formData.subject_id) return properties
    const prefix = formData.subject_id.split(':')[0]
    const subjectClass = classes.find(c => c.prefix === prefix)
    if (!subjectClass) return properties
    return properties.filter(p => p.domain_class_id === subjectClass.id)
  }, [formData.subject_id, properties, classes])

  // Get selected property details
  const selectedProperty = useMemo(() => {
    return properties.find(p => p.prop_name === formData.predicate)
  }, [formData.predicate, properties])

  // Get available subjects for entity_ref dropdown
  const entityRefSubjects = useMemo(() => {
    if (!selectedProperty || selectedProperty.range_kind !== 'entity_ref') return []
    const rangeClass = classes.find(c => c.id === selectedProperty.range_class_id)
    if (!rangeClass) return subjects
    return subjects.filter(s => s.startsWith(`${rangeClass.prefix}:`))
  }, [selectedProperty, classes, subjects])

  useEffect(() => {
    if (triple) {
      setFormData({
        subject_id: triple.subject_id,
        predicate: triple.predicate,
        object_value: triple.object_value,
        object_type: triple.object_type as TripleFormData['object_type'],
      })
    } else {
      setFormData({
        ...initialFormData,
        subject_id: subjectId || '',
      })
    }
  }, [triple, subjectId])

  // Update object_type when predicate changes
  useEffect(() => {
    if (selectedProperty && !triple) {
      setFormData(prev => ({
        ...prev,
        object_type: selectedProperty.range_kind as TripleFormData['object_type'],
        object_value: '',
      }))
    }
  }, [selectedProperty, triple])

  if (!isOpen) return null

  const isEdit = !!triple

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg shadow-xl w-full max-w-lg mx-4">
        <div className="flex justify-between items-center p-4 border-b">
          <h2 className="text-lg font-semibold">{isEdit ? 'Edit Triple' : 'Create Triple'}</h2>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-700">
            <X className="h-5 w-5" />
          </button>
        </div>
        <form
          onSubmit={e => {
            e.preventDefault()
            onSave(formData, isEdit, triple?.id)
          }}
          className="p-4 space-y-4"
        >
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Subject ID *</label>
            {isEdit ? (
              <input
                type="text"
                disabled
                value={formData.subject_id}
                className="w-full px-3 py-2 border rounded-lg bg-gray-100 text-gray-600"
              />
            ) : (
              <div className="flex gap-2">
                <select
                  value={formData.subject_id.split(':')[0] || ''}
                  onChange={e => {
                    const prefix = e.target.value
                    const id = formData.subject_id.split(':')[1] || ''
                    setFormData({ ...formData, subject_id: prefix ? `${prefix}:${id}` : id, predicate: '' })
                  }}
                  className="px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
                >
                  <option value="">Prefix...</option>
                  {classPrefixes.map(prefix => (
                    <option key={prefix} value={prefix}>{prefix}</option>
                  ))}
                </select>
                <input
                  type="text"
                  required
                  value={formData.subject_id.split(':')[1] || ''}
                  onChange={e => {
                    const prefix = formData.subject_id.split(':')[0] || ''
                    setFormData({ ...formData, subject_id: prefix ? `${prefix}:${e.target.value}` : e.target.value })
                  }}
                  placeholder="entity-id"
                  className="flex-1 px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
                />
              </div>
            )}
            <p className="text-xs text-gray-500 mt-1">Format: prefix:id (e.g., order:FM-1001)</p>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Predicate *</label>
            {isEdit ? (
              <input
                type="text"
                disabled
                value={formData.predicate}
                className="w-full px-3 py-2 border rounded-lg bg-gray-100 text-gray-600"
              />
            ) : (
              <select
                required
                value={formData.predicate}
                onChange={e => setFormData({ ...formData, predicate: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
              >
                <option value="">Select a predicate...</option>
                {availableProperties.map(prop => (
                  <option key={prop.id} value={prop.prop_name}>
                    {prop.prop_name} ({prop.range_kind})
                  </option>
                ))}
              </select>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Value * <span className="text-gray-400">({formData.object_type})</span>
            </label>
            {selectedProperty?.range_kind === 'entity_ref' ? (
              <select
                required
                value={formData.object_value}
                onChange={e => setFormData({ ...formData, object_value: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
              >
                <option value="">Select an entity...</option>
                {entityRefSubjects.map(s => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            ) : selectedProperty?.range_kind === 'boolean' ? (
              <select
                required
                value={formData.object_value}
                onChange={e => setFormData({ ...formData, object_value: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
              >
                <option value="">Select...</option>
                <option value="true">true</option>
                <option value="false">false</option>
              </select>
            ) : selectedProperty?.range_kind === 'datetime' ? (
              <input
                type="datetime-local"
                required
                value={formData.object_value ? formData.object_value.slice(0, 16) : ''}
                onChange={e => setFormData({ ...formData, object_value: e.target.value ? new Date(e.target.value).toISOString() : '' })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
              />
            ) : (
              <input
                type={selectedProperty?.range_kind === 'integer' || selectedProperty?.range_kind === 'decimal' ? 'number' : 'text'}
                step={selectedProperty?.range_kind === 'decimal' ? '0.01' : undefined}
                required
                value={formData.object_value}
                onChange={e => setFormData({ ...formData, object_value: e.target.value })}
                placeholder="Enter value..."
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
              />
            )}
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
              {isLoading ? 'Saving...' : isEdit ? 'Update' : 'Create'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export default function TriplesBrowserPage() {
  const queryClient = useQueryClient()
  const [subjectId, setSubjectId] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [entityTypeFilter, setEntityTypeFilter] = useState<string>('')
  const [showModal, setShowModal] = useState(false)
  const [editingTriple, setEditingTriple] = useState<Triple | undefined>()
  const [deleteConfirm, setDeleteConfirm] = useState<Triple | null>(null)
  const [deleteSubjectConfirm, setDeleteSubjectConfirm] = useState<string | null>(null)

  const { data: subjects = [] } = useQuery({
    queryKey: ['subjects'],
    queryFn: () => triplesApi.listSubjects().then(r => r.data),
  })

  const { data: subjectInfo, isLoading } = useQuery({
    queryKey: ['subject', subjectId],
    queryFn: () => triplesApi.getSubject(subjectId).then(r => r.data),
    enabled: !!subjectId,
  })

  const { data: properties = [] } = useQuery({
    queryKey: ['ontology-properties'],
    queryFn: () => ontologyApi.listProperties().then(r => r.data),
  })

  const { data: classes = [] } = useQuery({
    queryKey: ['ontology-classes'],
    queryFn: () => ontologyApi.listClasses().then(r => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (data: TripleCreate) => triplesApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['subjects'] })
      queryClient.invalidateQueries({ queryKey: ['subject', subjectId] })
      setShowModal(false)
      setEditingTriple(undefined)
    },
    onError: (error: Error & { response?: { data?: { detail?: { message?: string } } } }) => {
      console.error('Failed to create triple:', error)
      const message = error.response?.data?.detail?.message || 'Failed to create triple'
      alert(`${message}. Check the console for details.`)
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: { object_value: string } }) =>
      triplesApi.update(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['subject', subjectId] })
      setShowModal(false)
      setEditingTriple(undefined)
    },
    onError: (error) => {
      console.error('Failed to update triple:', error)
      alert('Failed to update triple. Check the console for details.')
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => triplesApi.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['subject', subjectId] })
      setDeleteConfirm(null)
    },
    onError: (error) => {
      console.error('Failed to delete triple:', error)
      alert('Failed to delete triple. Check the console for details.')
    },
  })

  const deleteSubjectMutation = useMutation({
    mutationFn: (subjectId: string) => triplesApi.deleteSubject(subjectId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['subjects'] })
      setSubjectId('')
      setDeleteSubjectConfirm(null)
    },
    onError: (error) => {
      console.error('Failed to delete subject:', error)
      alert('Failed to delete subject. Check the console for details.')
    },
  })

  const handleSave = (formData: TripleFormData, isEdit: boolean, tripleId?: number) => {
    if (isEdit && tripleId) {
      updateMutation.mutate({ id: tripleId, data: { object_value: formData.object_value } })
    } else {
      createMutation.mutate(formData)
    }
  }

  // Extract unique entity types from subject IDs (prefix before colon)
  const entityTypes = useMemo(() => {
    if (!subjects) return []
    const types = new Set<string>()
    subjects.forEach(s => {
      const prefix = s.split(':')[0]
      if (prefix) types.add(prefix)
    })
    return Array.from(types).sort()
  }, [subjects])

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    setSubjectId(searchInput)
  }

  const filteredSubjects = useMemo(() => {
    if (!subjects) return []
    return subjects.filter(s => {
      const matchesSearch = s.toLowerCase().includes(searchInput.toLowerCase())
      const matchesType = !entityTypeFilter || s.startsWith(`${entityTypeFilter}:`)
      return matchesSearch && matchesType
    })
  }, [subjects, searchInput, entityTypeFilter])

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Triples Browser</h1>
          <p className="text-gray-600">Explore and manage entities in the knowledge graph</p>
        </div>
        <button
          onClick={() => {
            setEditingTriple(undefined)
            setShowModal(true)
          }}
          className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
        >
          <Plus className="h-4 w-4" />
          Add Triple
        </button>
      </div>

      <div className="grid grid-cols-3 gap-6">
        {/* Subject list */}
        <div className="col-span-1">
          <form onSubmit={handleSearch} className="mb-4 space-y-2">
            <div className="relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <input
                type="text"
                value={searchInput}
                onChange={e => setSearchInput(e.target.value)}
                placeholder="Search subject ID..."
                className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
              />
            </div>
            <div className="relative">
              <Filter className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <select
                value={entityTypeFilter}
                onChange={e => setEntityTypeFilter(e.target.value)}
                className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 appearance-none bg-white"
              >
                <option value="">All entity types</option>
                {entityTypes.map(type => (
                  <option key={type} value={type}>
                    {type} ({subjects?.filter(s => s.startsWith(`${type}:`)).length || 0})
                  </option>
                ))}
              </select>
            </div>
          </form>

          <div className="bg-white rounded-lg shadow overflow-hidden">
            <div className="p-3 bg-gray-50 border-b font-medium text-sm text-gray-700 flex justify-between items-center">
              <span>Subjects</span>
              <span className="text-xs text-gray-500">{filteredSubjects.length} total</span>
            </div>
            <div className="max-h-96 overflow-y-auto">
              {filteredSubjects.map(s => (
                <button
                  key={s}
                  onClick={() => setSubjectId(s)}
                  className={`w-full text-left px-3 py-2 text-sm flex items-center justify-between hover:bg-gray-50 ${
                    subjectId === s ? 'bg-green-50 text-green-700' : ''
                  }`}
                >
                  <span className="truncate">{s}</span>
                  <ChevronRight className="h-4 w-4 flex-shrink-0" />
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Subject details */}
        <div className="col-span-2">
          {!subjectId && (
            <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
              Select a subject to view its triples
            </div>
          )}

          {subjectId && isLoading && (
            <div className="bg-white rounded-lg shadow p-8 text-center text-gray-500">
              Loading...
            </div>
          )}

          {subjectInfo && (
            <div className="bg-white rounded-lg shadow">
              <div className="p-4 border-b flex justify-between items-start">
                <div>
                  <h2 className="font-semibold text-lg">{subjectInfo.subject_id}</h2>
                  {subjectInfo.class_name && (
                    <span className="text-sm bg-green-100 text-green-700 px-2 py-0.5 rounded">
                      {subjectInfo.class_name}
                    </span>
                  )}
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => {
                      setEditingTriple(undefined)
                      setShowModal(true)
                    }}
                    className="flex items-center gap-1 px-3 py-1.5 text-sm bg-green-100 text-green-700 rounded hover:bg-green-200"
                    title="Add triple to this subject"
                  >
                    <Plus className="h-4 w-4" />
                    Add
                  </button>
                  <button
                    onClick={() => setDeleteSubjectConfirm(subjectInfo.subject_id)}
                    className="flex items-center gap-1 px-3 py-1.5 text-sm bg-red-100 text-red-700 rounded hover:bg-red-200"
                    title="Delete all triples for this subject"
                  >
                    <Trash2 className="h-4 w-4" />
                    Delete Subject
                  </button>
                </div>
              </div>
              <div className="p-4">
                <table className="w-full">
                  <thead>
                    <tr className="text-left text-sm text-gray-500 border-b">
                      <th className="pb-2">Predicate</th>
                      <th className="pb-2">Value</th>
                      <th className="pb-2">Type</th>
                      <th className="pb-2 w-20">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {subjectInfo.triples.map(triple => (
                      <tr key={triple.id} className="border-b last:border-0 hover:bg-gray-50">
                        <td className="py-2">
                          <code className="text-sm text-blue-600">{triple.predicate}</code>
                        </td>
                        <td className="py-2">
                          {triple.object_type === 'entity_ref' ? (
                            <button
                              onClick={() => setSubjectId(triple.object_value)}
                              className="text-green-600 hover:underline"
                            >
                              {triple.object_value}
                            </button>
                          ) : (
                            <span className="break-all">{triple.object_value}</span>
                          )}
                        </td>
                        <td className="py-2">
                          <span className="text-xs bg-gray-100 px-2 py-0.5 rounded">
                            {triple.object_type}
                          </span>
                        </td>
                        <td className="py-2">
                          <div className="flex gap-1">
                            <button
                              onClick={() => {
                                setEditingTriple(triple)
                                setShowModal(true)
                              }}
                              className="p-1 text-gray-400 hover:text-blue-600"
                              title="Edit triple"
                            >
                              <Edit2 className="h-4 w-4" />
                            </button>
                            <button
                              onClick={() => setDeleteConfirm(triple)}
                              className="p-1 text-gray-400 hover:text-red-600"
                              title="Delete triple"
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
            </div>
          )}
        </div>
      </div>

      <TripleFormModal
        isOpen={showModal}
        onClose={() => {
          setShowModal(false)
          setEditingTriple(undefined)
        }}
        triple={editingTriple}
        subjectId={subjectId}
        onSave={handleSave}
        isLoading={createMutation.isPending || updateMutation.isPending}
        properties={properties}
        classes={classes}
        subjects={subjects}
      />

      {/* Delete Triple Confirmation */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-sm mx-4">
            <h3 className="text-lg font-semibold mb-2">Delete Triple</h3>
            <p className="text-gray-600 mb-4">
              Are you sure you want to delete the triple <strong>{deleteConfirm.predicate}</strong> = <strong>{deleteConfirm.object_value}</strong>?
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

      {/* Delete Subject Confirmation */}
      {deleteSubjectConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-sm mx-4">
            <h3 className="text-lg font-semibold mb-2">Delete Subject</h3>
            <p className="text-gray-600 mb-4">
              Are you sure you want to delete <strong>{deleteSubjectConfirm}</strong> and all its triples? This action cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button onClick={() => setDeleteSubjectConfirm(null)} className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50">
                Cancel
              </button>
              <button
                onClick={() => deleteSubjectMutation.mutate(deleteSubjectConfirm)}
                disabled={deleteSubjectMutation.isPending}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
              >
                {deleteSubjectMutation.isPending ? 'Deleting...' : 'Delete All'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
