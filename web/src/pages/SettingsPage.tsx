import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { healthApi, loadgenApi, LoadGenProfile, LoadGenProfileInfo } from '../api/client'
import { CheckCircle, XCircle, Server, Database, Search, ExternalLink, BarChart3, FileText, Layers, Play, Square, Loader2, Zap } from 'lucide-react'

export default function SettingsPage() {
  const queryClient = useQueryClient()
  const [selectedProfile, setSelectedProfile] = useState<LoadGenProfile>('demo')
  const [durationOverride, setDurationOverride] = useState<string>('')

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

  // Load generator queries
  const { data: loadgenStatus, isLoading: statusLoading, error: statusError } = useQuery({
    queryKey: ['loadgen-status'],
    queryFn: () => loadgenApi.getStatus().then(r => r.data),
    refetchInterval: 2000, // Poll every 2 seconds
    retry: 3,
  })

  const { data: profiles, error: profilesError } = useQuery({
    queryKey: ['loadgen-profiles'],
    queryFn: () => loadgenApi.getProfiles().then(r => r.data),
    retry: 3,
  })

  const startMutation = useMutation({
    mutationFn: () => loadgenApi.start({
      profile: selectedProfile,
      duration_minutes: durationOverride ? parseInt(durationOverride, 10) : undefined,
    }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['loadgen-status'] })
    },
  })

  const stopMutation = useMutation({
    mutationFn: () => loadgenApi.stop(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['loadgen-status'] })
    },
  })

  const isRunning = loadgenStatus?.status === 'running' || loadgenStatus?.status === 'starting'
  const isStopping = loadgenStatus?.status === 'stopping'
  const selectedProfileInfo = profiles?.find((p: LoadGenProfileInfo) => p.name === selectedProfile)

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

      {/* Load Generator Controls */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-lg flex items-center gap-2">
            <Zap className="h-5 w-5 text-yellow-500" />
            Load Generator
          </h2>
          <div className="flex items-center gap-2">
            {statusError || profilesError ? (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-sm font-medium bg-red-100 text-red-800">
                <XCircle className="h-3 w-3" />
                Service Unavailable
              </span>
            ) : statusLoading ? (
              <span className="text-sm text-gray-500">Loading...</span>
            ) : isRunning ? (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-sm font-medium bg-green-100 text-green-800">
                <span className="relative flex h-2 w-2">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-green-500"></span>
                </span>
                Running
              </span>
            ) : isStopping ? (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-sm font-medium bg-yellow-100 text-yellow-800">
                <Loader2 className="h-3 w-3 animate-spin" />
                Stopping
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-sm font-medium bg-gray-100 text-gray-600">
                <span className="h-2 w-2 rounded-full bg-gray-400"></span>
                Stopped
              </span>
            )}
          </div>
        </div>

        {/* Running Info */}
        {isRunning && loadgenStatus && (
          <div className="mb-4 p-3 bg-green-50 border border-green-200 rounded-lg">
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-gray-500">Profile:</span>
                <span className="ml-2 font-medium text-green-800">{loadgenStatus.profile}</span>
              </div>
              <div>
                <span className="text-gray-500">Duration:</span>
                <span className="ml-2 font-medium text-green-800">
                  {loadgenStatus.duration_minutes ? `${loadgenStatus.duration_minutes} min` : 'Unlimited'}
                </span>
              </div>
              <div>
                <span className="text-gray-500">Started:</span>
                <span className="ml-2 font-medium text-green-800">
                  {loadgenStatus.started_at ? new Date(loadgenStatus.started_at).toLocaleTimeString() : '-'}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Controls */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Profile Selection */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Profile</label>
            <select
              value={selectedProfile}
              onChange={(e) => setSelectedProfile(e.target.value as LoadGenProfile)}
              disabled={isRunning || isStopping}
              className="w-full px-3 py-2 border rounded-lg bg-white disabled:bg-gray-100 disabled:text-gray-500"
            >
              {profiles?.map((profile: LoadGenProfileInfo) => (
                <option key={profile.name} value={profile.name}>
                  {profile.name.charAt(0).toUpperCase() + profile.name.slice(1)} - {profile.orders_per_minute} orders/min
                </option>
              ))}
            </select>
            {selectedProfileInfo && (
              <p className="text-xs text-gray-500 mt-1">{selectedProfileInfo.description}</p>
            )}
          </div>

          {/* Duration Override */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Duration (minutes)</label>
            <input
              type="number"
              value={durationOverride}
              onChange={(e) => {
                const value = e.target.value
                // Only allow positive integers or empty string
                if (value === '' || (!isNaN(Number(value)) && Number(value) > 0)) {
                  setDurationOverride(value)
                }
              }}
              placeholder={selectedProfileInfo?.duration_minutes?.toString() || 'Unlimited'}
              disabled={isRunning || isStopping}
              className="w-full px-3 py-2 border rounded-lg disabled:bg-gray-100 disabled:text-gray-500"
              min="1"
            />
            <p className="text-xs text-gray-500 mt-1">Leave empty for profile default</p>
          </div>
        </div>

        {/* Start/Stop Button */}
        <div className="mt-4">
          {isRunning || isStopping ? (
            <button
              onClick={() => stopMutation.mutate()}
              disabled={isStopping || stopMutation.isPending}
              className="flex items-center justify-center gap-2 px-6 py-2 bg-red-600 hover:bg-red-700 disabled:bg-red-400 text-white font-medium rounded-lg transition-colors"
            >
              {stopMutation.isPending || isStopping ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Stopping...
                </>
              ) : (
                <>
                  <Square className="h-4 w-4" />
                  Stop Traffic
                </>
              )}
            </button>
          ) : (
            <button
              onClick={() => startMutation.mutate()}
              disabled={startMutation.isPending}
              className="flex items-center justify-center gap-2 px-6 py-2 bg-green-600 hover:bg-green-700 disabled:bg-green-400 text-white font-medium rounded-lg transition-colors"
            >
              {startMutation.isPending ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Starting...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4" />
                  Start Traffic
                </>
              )}
            </button>
          )}
        </div>

        {/* Error Display */}
        {(startMutation.isError || stopMutation.isError || statusError || profilesError) && (
          <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg">
            <div className="flex items-start gap-2">
              <XCircle className="h-5 w-5 text-red-600 mt-0.5 flex-shrink-0" />
              <div className="text-sm">
                <p className="font-medium text-red-800">Load Generator Error</p>
                <p className="text-red-700 mt-1">
                  {startMutation.error?.message ||
                   stopMutation.error?.message ||
                   statusError?.message ||
                   profilesError?.message ||
                   'Failed to connect to load generator service. Please check that the service is running.'}
                </p>
              </div>
            </div>
          </div>
        )}
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
            href="http://localhost:5601"
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col items-center gap-2 p-4 bg-orange-50 rounded-lg hover:bg-orange-100 transition-colors group"
          >
            <Search className="h-8 w-8 text-orange-600" />
            <span className="font-medium text-orange-900">OpenSearch Dashboards</span>
            <span className="text-xs text-orange-600 flex items-center gap-1">
              localhost:5601 <ExternalLink className="h-3 w-3" />
            </span>
          </a>
        </div>
      </div>

      {/* OpenSearch Dashboards Guide */}
      <div className="bg-white rounded-lg shadow p-6 mb-6">
        <h2 className="font-semibold text-lg mb-4 flex items-center gap-2">
          <Search className="h-5 w-5 text-orange-600" />
          Using OpenSearch Dashboards
        </h2>
        <div className="space-y-4 text-sm">
          <p className="text-gray-700">
            OpenSearch Dashboards provides powerful search and visualization capabilities for your indexed order data.
          </p>

          <div className="border-l-4 border-orange-500 bg-orange-50 p-4 rounded">
            <h3 className="font-semibold text-orange-900 mb-2">Quick Start: Dev Tools Console</h3>
            <ol className="list-decimal list-inside space-y-2 text-gray-700">
              <li>Open <a href="http://localhost:5601" target="_blank" rel="noopener noreferrer" className="text-orange-600 hover:underline font-medium">OpenSearch Dashboards</a></li>
              <li>Click the menu icon (☰) → "Management" → "Dev Tools"</li>
              <li>Run queries in the console</li>
            </ol>
          </div>

          <div>
            <h3 className="font-semibold text-gray-900 mb-2">Example Queries</h3>
            <div className="space-y-3">
              <div className="bg-gray-50 p-3 rounded font-mono text-xs">
                <div className="text-gray-500 mb-1"># Search all orders</div>
                <div className="text-purple-600">GET orders/_search</div>
                <div>{'{'}</div>
                <div className="ml-4">"size": 10</div>
                <div>{'}'}</div>
              </div>

              <div className="bg-gray-50 p-3 rounded font-mono text-xs">
                <div className="text-gray-500 mb-1"># Find orders by status</div>
                <div className="text-purple-600">GET orders/_search</div>
                <div>{'{'}</div>
                <div className="ml-4">"query": {'{'}</div>
                <div className="ml-8">"match": {'{'}</div>
                <div className="ml-12">"order_status": "OUT_FOR_DELIVERY"</div>
                <div className="ml-8">{'}'}</div>
                <div className="ml-4">{'}'}</div>
                <div>{'}'}</div>
              </div>

              <div className="bg-gray-50 p-3 rounded font-mono text-xs">
                <div className="text-gray-500 mb-1"># Search by customer name</div>
                <div className="text-purple-600">GET orders/_search</div>
                <div>{'{'}</div>
                <div className="ml-4">"query": {'{'}</div>
                <div className="ml-8">"match": {'{'}</div>
                <div className="ml-12">"customer_name": "Sarah"</div>
                <div className="ml-8">{'}'}</div>
                <div className="ml-4">{'}'}</div>
                <div>{'}'}</div>
              </div>

              <div className="bg-gray-50 p-3 rounded font-mono text-xs">
                <div className="text-gray-500 mb-1"># Count total orders</div>
                <div className="text-purple-600">GET orders/_count</div>
              </div>
            </div>
          </div>

          <div className="border-l-4 border-blue-500 bg-blue-50 p-4 rounded">
            <h3 className="font-semibold text-blue-900 mb-2">Alternative: Discover (Visual)</h3>
            <ol className="list-decimal list-inside space-y-1 text-gray-700">
              <li>Click "Discover" in the left sidebar</li>
              <li>Create an index pattern: <code className="bg-white px-2 py-0.5 rounded">orders*</code></li>
              <li>Browse and filter your data visually</li>
            </ol>
          </div>

          <div className="text-xs text-gray-500 pt-2 border-t">
            <strong>Note:</strong> All orders are automatically synced to OpenSearch for full-text search capabilities.
            Currently indexing orders with customer names, addresses, and order details.
          </div>
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
