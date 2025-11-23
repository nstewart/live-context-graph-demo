import { useQuery } from '@tanstack/react-query'
import { useState, useMemo } from 'react'
import { triplesApi } from '../api/client'
import { Search, ChevronRight, Filter } from 'lucide-react'

export default function TriplesBrowserPage() {
  const [subjectId, setSubjectId] = useState('')
  const [searchInput, setSearchInput] = useState('')
  const [entityTypeFilter, setEntityTypeFilter] = useState<string>('')

  const { data: subjects } = useQuery({
    queryKey: ['subjects'],
    queryFn: () => triplesApi.listSubjects().then(r => r.data),
  })

  const { data: subjectInfo, isLoading } = useQuery({
    queryKey: ['subject', subjectId],
    queryFn: () => triplesApi.getSubject(subjectId).then(r => r.data),
    enabled: !!subjectId,
  })

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
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Triples Browser</h1>
        <p className="text-gray-600">Explore entities in the knowledge graph</p>
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
              <div className="p-4 border-b">
                <h2 className="font-semibold text-lg">{subjectInfo.subject_id}</h2>
                {subjectInfo.class_name && (
                  <span className="text-sm bg-green-100 text-green-700 px-2 py-0.5 rounded">
                    {subjectInfo.class_name}
                  </span>
                )}
              </div>
              <div className="p-4">
                <table className="w-full">
                  <thead>
                    <tr className="text-left text-sm text-gray-500 border-b">
                      <th className="pb-2">Predicate</th>
                      <th className="pb-2">Value</th>
                      <th className="pb-2">Type</th>
                    </tr>
                  </thead>
                  <tbody>
                    {subjectInfo.triples.map(triple => (
                      <tr key={triple.id} className="border-b last:border-0">
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
                            <span>{triple.object_value}</span>
                          )}
                        </td>
                        <td className="py-2">
                          <span className="text-xs bg-gray-100 px-2 py-0.5 rounded">
                            {triple.object_type}
                          </span>
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
    </div>
  )
}
