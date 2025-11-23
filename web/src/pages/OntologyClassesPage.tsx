import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { ontologyApi } from '../api/client'
import { Plus, Database } from 'lucide-react'

export default function OntologyClassesPage() {
  const queryClient = useQueryClient()
  const [showForm, setShowForm] = useState(false)
  const [formData, setFormData] = useState({ class_name: '', prefix: '', description: '' })

  const { data: classes, isLoading, error } = useQuery({
    queryKey: ['ontology-classes'],
    queryFn: () => ontologyApi.listClasses().then(r => r.data),
  })

  const createMutation = useMutation({
    mutationFn: (data: typeof formData) => ontologyApi.createClass(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['ontology-classes'] })
      setShowForm(false)
      setFormData({ class_name: '', prefix: '', description: '' })
    },
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    createMutation.mutate(formData)
  }

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Ontology Classes</h1>
          <p className="text-gray-600">Define entity types in the knowledge graph</p>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
        >
          <Plus className="h-4 w-4" />
          Add Class
        </button>
      </div>

      {/* Add form */}
      {showForm && (
        <div className="bg-white rounded-lg shadow p-4 mb-6">
          <h2 className="font-semibold mb-4">New Ontology Class</h2>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Class Name</label>
                <input
                  type="text"
                  value={formData.class_name}
                  onChange={e => setFormData({ ...formData, class_name: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
                  placeholder="e.g., Customer"
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Prefix</label>
                <input
                  type="text"
                  value={formData.prefix}
                  onChange={e => setFormData({ ...formData, prefix: e.target.value })}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
                  placeholder="e.g., customer"
                  required
                />
              </div>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
              <textarea
                value={formData.description}
                onChange={e => setFormData({ ...formData, description: e.target.value })}
                className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
                rows={2}
              />
            </div>
            <div className="flex gap-2">
              <button
                type="submit"
                disabled={createMutation.isPending}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
              >
                {createMutation.isPending ? 'Creating...' : 'Create Class'}
              </button>
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="px-4 py-2 border rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {isLoading && <div className="text-center py-8 text-gray-500">Loading...</div>}
      {error && <div className="bg-red-50 text-red-700 p-4 rounded-lg">Error loading classes</div>}

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
                      <span className="font-medium">{cls.class_name}</span>
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
  )
}
