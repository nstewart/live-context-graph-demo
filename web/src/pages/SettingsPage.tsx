import { useQuery } from '@tanstack/react-query'
import { healthApi } from '../api/client'
import { CheckCircle, XCircle, Server, Database, Search, ExternalLink, BarChart3, FileText, Layers } from 'lucide-react'

export default function SettingsPage() {
  const { data: health, error: healthError } = useQuery({
    queryKey: ['health'],
    queryFn: () => healthApi.check().then(r => r.data),
    retry: false,
  })

  const { data: ready } = useQuery({
    queryKey: ['ready'],
    queryFn: () => healthApi.ready().then(r => r.data),
    retry: false,
  })

  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8080'

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="text-gray-600">System configuration and health status</p>
      </div>

      {/* Health Status */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="font-semibold text-lg mb-4">Service Health</h2>
        <div className="grid grid-cols-3 gap-4">
          <div className="flex items-center gap-3 p-4 bg-gray-50 rounded-lg">
            <Server className="h-8 w-8 text-gray-400" />
            <div>
              <p className="font-medium">API Server</p>
              <div className="flex items-center gap-1 text-sm">
                {health && !healthError ? (
                  <>
                    <CheckCircle className="h-4 w-4 text-green-500" />
                    <span className="text-green-600">Healthy</span>
                  </>
                ) : (
                  <>
                    <XCircle className="h-4 w-4 text-red-500" />
                    <span className="text-red-600">Unreachable</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 p-4 bg-gray-50 rounded-lg">
            <Database className="h-8 w-8 text-gray-400" />
            <div>
              <p className="font-medium">Database</p>
              <div className="flex items-center gap-1 text-sm">
                {ready?.database === 'connected' ? (
                  <>
                    <CheckCircle className="h-4 w-4 text-green-500" />
                    <span className="text-green-600">Connected</span>
                  </>
                ) : (
                  <>
                    <XCircle className="h-4 w-4 text-red-500" />
                    <span className="text-red-600">Disconnected</span>
                  </>
                )}
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3 p-4 bg-gray-50 rounded-lg">
            <Search className="h-8 w-8 text-gray-400" />
            <div>
              <p className="font-medium">OpenSearch</p>
              <div className="flex items-center gap-1 text-sm text-gray-500">
                See search-sync logs
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Dashboard Links */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="font-semibold text-lg mb-4">Dashboards & Tools</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <a
            href="http://localhost:6874"
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col items-center gap-2 p-4 bg-purple-50 rounded-lg hover:bg-purple-100 transition-colors group"
          >
            <Layers className="h-8 w-8 text-purple-600" />
            <span className="font-medium text-purple-900">Materialize Console</span>
            <span className="text-xs text-purple-600 flex items-center gap-1">
              localhost:6874 <ExternalLink className="h-3 w-3" />
            </span>
          </a>

          <a
            href={`${apiUrl}/docs`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col items-center gap-2 p-4 bg-blue-50 rounded-lg hover:bg-blue-100 transition-colors group"
          >
            <FileText className="h-8 w-8 text-blue-600" />
            <span className="font-medium text-blue-900">API Documentation</span>
            <span className="text-xs text-blue-600 flex items-center gap-1">
              Swagger UI <ExternalLink className="h-3 w-3" />
            </span>
          </a>

          <a
            href={`${apiUrl}/stats`}
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col items-center gap-2 p-4 bg-green-50 rounded-lg hover:bg-green-100 transition-colors group"
          >
            <BarChart3 className="h-8 w-8 text-green-600" />
            <span className="font-medium text-green-900">Query Statistics</span>
            <span className="text-xs text-green-600 flex items-center gap-1">
              Performance metrics <ExternalLink className="h-3 w-3" />
            </span>
          </a>

          <a
            href="http://localhost:9200"
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col items-center gap-2 p-4 bg-orange-50 rounded-lg hover:bg-orange-100 transition-colors group"
          >
            <Search className="h-8 w-8 text-orange-600" />
            <span className="font-medium text-orange-900">OpenSearch</span>
            <span className="text-xs text-orange-600 flex items-center gap-1">
              localhost:9200 <ExternalLink className="h-3 w-3" />
            </span>
          </a>
        </div>
      </div>

      {/* Configuration */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="font-semibold text-lg mb-4">Configuration</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">API URL</label>
            <input
              type="text"
              value={apiUrl}
              readOnly
              className="w-full px-3 py-2 bg-gray-50 border rounded-lg text-gray-600"
            />
            <p className="text-sm text-gray-500 mt-1">
              Set via VITE_API_URL environment variable
            </p>
          </div>

          <div className="pt-4 border-t">
            <h3 className="font-medium mb-2">Environment</h3>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div className="text-gray-500">Mode:</div>
              <div>{import.meta.env.MODE}</div>
              <div className="text-gray-500">Production:</div>
              <div>{import.meta.env.PROD ? 'Yes' : 'No'}</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
