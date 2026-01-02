import { useState, useMemo, useEffect } from 'react'
import { useZero, useQuery } from '@rocicorp/zero/react'
import {
  Truck,
  Package,
  ChevronDown,
  ChevronRight,
  Info,
  Store,
  ShoppingCart,
  Check,
  Clock,
  Scale,
  AlertTriangle,
  AlertCircle,
  Terminal,
} from 'lucide-react'
import { Schema } from '../schema'
import { apiClient } from '../api/client'

// Feature status type
interface FeatureStatus {
  feature: string
  enabled: boolean
  description: string
  enable_command: string | null
}

// Bundle type from Zero
interface Bundle {
  bundle_id: string
  store_id: string | null
  store_name: string | null
  orders: string[] | null
  bundle_size: number | null
}

// Compatible pair type from Zero
interface CompatiblePair {
  order_a: string
  order_b: string
  store_id: string | null
  store_name: string | null
  overlap_start: string | null
  overlap_end: string | null
  order_a_weight_grams: number | null
  order_b_weight_grams: number | null
  combined_weight_grams: number | null
}

// Format weight for display
function formatWeight(grams: number | null): string {
  if (grams === null || grams === 0) return '0g'
  if (grams >= 1000) return `${(grams / 1000).toFixed(1)}kg`
  return `${grams}g`
}

// Format time for display
function formatTime(isoString: string | null): string {
  if (!isoString) return '—'
  try {
    const date = new Date(isoString)
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  } catch {
    return '—'
  }
}

// Get vehicle compatibility based on weight
function getVehicleCompatibility(weightGrams: number | null): { bike: boolean; car: boolean; van: boolean } {
  const weight = weightGrams || 0
  return {
    bike: weight <= 5000,
    car: weight <= 20000,
    van: weight <= 50000,
  }
}

export default function BundlingPage() {
  const [howItWorksOpen, setHowItWorksOpen] = useState(true)
  const [expandedBundles, setExpandedBundles] = useState<Set<string>>(new Set())
  const [featureStatus, setFeatureStatus] = useState<FeatureStatus | null>(null)
  const [featureLoading, setFeatureLoading] = useState(true)

  // Check if bundling feature is enabled
  useEffect(() => {
    const checkFeature = async () => {
      try {
        const response = await apiClient.get('/api/features/bundling')
        setFeatureStatus(response.data)
      } catch (error) {
        console.error('Failed to check bundling feature status:', error)
      } finally {
        setFeatureLoading(false)
      }
    }
    checkFeature()
  }, [])

  // Zero queries
  const z = useZero<Schema>()

  // Query all bundles
  const bundlesQuery = useMemo(() => z.query.delivery_bundles_mv, [z])
  const [bundlesData] = useQuery(bundlesQuery)
  const bundles = (bundlesData || []) as Bundle[]

  // Query compatible pairs for bundle explanations
  const pairsQuery = useMemo(() => z.query.compatible_pairs_mv, [z])
  const [pairsData] = useQuery(pairsQuery)
  const compatiblePairs = (pairsData || []) as CompatiblePair[]

  // Index compatible pairs by order for quick lookup
  const pairsByOrder = useMemo(() => {
    const index: Record<string, CompatiblePair[]> = {}
    for (const pair of compatiblePairs) {
      if (!index[pair.order_a]) index[pair.order_a] = []
      if (!index[pair.order_b]) index[pair.order_b] = []
      index[pair.order_a].push(pair)
      index[pair.order_b].push(pair)
    }
    return index
  }, [compatiblePairs])

  // Group bundles by store
  const bundlesByStore = useMemo(() => {
    const grouped: Record<string, Bundle[]> = {}
    for (const bundle of bundles) {
      const storeKey = bundle.store_id || 'unknown'
      if (!grouped[storeKey]) {
        grouped[storeKey] = []
      }
      grouped[storeKey].push(bundle)
    }
    for (const storeKey of Object.keys(grouped)) {
      grouped[storeKey].sort((a, b) => (b.bundle_size || 0) - (a.bundle_size || 0))
    }
    return grouped
  }, [bundles])

  // Filter to multi-order bundles (size > 1)
  const multiBundles = bundles.filter((b) => (b.bundle_size || 0) > 1)
  const singletonBundles = bundles.filter((b) => (b.bundle_size || 0) === 1)

  // Toggle bundle expansion
  const toggleBundle = (bundleId: string) => {
    setExpandedBundles((prev) => {
      const next = new Set(prev)
      if (next.has(bundleId)) {
        next.delete(bundleId)
      } else {
        next.add(bundleId)
      }
      return next
    })
  }

  // Get bundle details from compatible pairs
  const getBundleDetails = (orders: string[]) => {
    if (orders.length < 2) return null

    // Find all pairs within this bundle
    const bundlePairs: CompatiblePair[] = []
    for (let i = 0; i < orders.length; i++) {
      for (let j = i + 1; j < orders.length; j++) {
        const ordersInPair = [orders[i], orders[j]].sort()
        const pair = compatiblePairs.find(
          (p) => p.order_a === ordersInPair[0] && p.order_b === ordersInPair[1]
        )
        if (pair) bundlePairs.push(pair)
      }
    }

    if (bundlePairs.length === 0) return null

    // Calculate aggregate stats
    const allOverlapStarts = bundlePairs.map((p) => p.overlap_start).filter(Boolean) as string[]
    const allOverlapEnds = bundlePairs.map((p) => p.overlap_end).filter(Boolean) as string[]

    // Shared window is the intersection of all overlaps
    const sharedStart = allOverlapStarts.length > 0
      ? allOverlapStarts.reduce((max, s) => (s > max ? s : max))
      : null
    const sharedEnd = allOverlapEnds.length > 0
      ? allOverlapEnds.reduce((min, s) => (s < min ? s : min))
      : null

    // Total weight (sum of all unique orders)
    const uniqueOrders = new Set(orders)
    let totalWeight = 0
    for (const pair of bundlePairs) {
      if (uniqueOrders.has(pair.order_a)) {
        totalWeight += pair.order_a_weight_grams || 0
        uniqueOrders.delete(pair.order_a)
      }
      if (uniqueOrders.has(pair.order_b)) {
        totalWeight += pair.order_b_weight_grams || 0
        uniqueOrders.delete(pair.order_b)
      }
    }

    return {
      sharedStart,
      sharedEnd,
      totalWeight,
      pairCount: bundlePairs.length,
      vehicles: getVehicleCompatibility(totalWeight),
    }
  }

  // Get reason why a singleton order is not bundled
  const getUnbundledReason = (orderId: string, storeId: string | null) => {
    // Check if this order has any compatible pairs
    const pairs = pairsByOrder[orderId] || []

    if (pairs.length > 0) {
      // Has compatible pairs but still singleton - might be transitive incompatibility
      return {
        type: 'transitive',
        message: 'Compatible with some orders individually, but no complete bundle possible',
      }
    }

    // Check if there are other orders at the same store
    const sameStoreOrders = singletonBundles.filter(
      (b) => b.store_id === storeId && b.bundle_id !== orderId
    )

    if (sameStoreOrders.length === 0) {
      return {
        type: 'only_order',
        message: 'Only CREATED order at this store',
      }
    }

    // There are other orders but no compatible pairs
    return {
      type: 'no_overlap',
      message: `No time overlap with ${sameStoreOrders.length} other order${sameStoreOrders.length !== 1 ? 's' : ''} at this store`,
    }
  }

  // Show loading state
  if (featureLoading) {
    return (
      <div className="p-6">
        <div className="flex items-center gap-3 mb-6">
          <Truck className="h-8 w-8 text-green-600" />
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Delivery Bundling</h1>
            <p className="text-gray-600">Loading feature status...</p>
          </div>
        </div>
      </div>
    )
  }

  // Show disabled state if feature is not enabled
  if (featureStatus && !featureStatus.enabled) {
    return (
      <div className="p-6">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-3">
            <Truck className="h-8 w-8 text-gray-400" />
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Delivery Bundling</h1>
              <p className="text-gray-600">
                Mutually recursive constraint satisfaction
              </p>
            </div>
          </div>
        </div>

        {/* Feature Disabled Notice */}
        <div className="bg-amber-50 border border-amber-200 rounded-lg p-6 max-w-2xl">
          <div className="flex items-start gap-4">
            <AlertCircle className="h-6 w-6 text-amber-500 flex-shrink-0 mt-0.5" />
            <div>
              <h3 className="text-lg font-semibold text-amber-800 mb-2">
                Feature Not Enabled
              </h3>
              <p className="text-amber-700 mb-4">
                Delivery bundling uses Materialize's <code className="bg-amber-100 px-1 rounded">WITH MUTUALLY RECURSIVE</code> to
                group compatible orders. This feature is disabled by default because it's CPU intensive
                (~460 seconds of compute time).
              </p>
              <div className="bg-gray-900 rounded-lg p-4 mb-4">
                <div className="flex items-center gap-2 text-gray-400 text-sm mb-2">
                  <Terminal className="h-4 w-4" />
                  <span>To enable, restart with:</span>
                </div>
                <code className="text-green-400 font-mono">
                  make up-agent-bundling
                </code>
              </div>
              <p className="text-sm text-amber-600">
                This will create the recursive materialized views for order bundling optimization.
              </p>
            </div>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3">
          <Truck className="h-8 w-8 text-green-600" />
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Delivery Bundling</h1>
            <p className="text-gray-600">
              Mutually recursive constraint satisfaction
            </p>
          </div>
        </div>
      </div>

      {/* How It Works Section */}
      <div className="bg-white rounded-lg shadow mb-6">
        <button
          onClick={() => setHowItWorksOpen(!howItWorksOpen)}
          className="w-full p-4 flex items-center justify-between hover:bg-gray-50 transition-colors"
        >
          <div className="flex items-center gap-2">
            {howItWorksOpen ? (
              <ChevronDown className="h-5 w-5 text-gray-500" />
            ) : (
              <ChevronRight className="h-5 w-5 text-gray-500" />
            )}
            <Info className="h-5 w-5 text-blue-500" />
            <div className="text-left">
              <h3 className="text-lg font-semibold text-gray-900">How It Works</h3>
              <p className="text-xs text-gray-500">
                Understanding Materialize's WITH MUTUALLY RECURSIVE
              </p>
            </div>
          </div>
        </button>
        {howItWorksOpen && (
          <div className="p-6 pt-0 border-t">
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
              {/* Left: Mutual Recursion Explanation */}
              <div>
                <h4 className="font-medium text-gray-900 mb-4">What is Mutual Recursion?</h4>
                <p className="text-sm text-gray-600 mb-4">
                  Traditional queries run once and return results. Mutually recursive queries have
                  multiple definitions that <span className="font-semibold text-gray-900">reference each other</span> and
                  run repeatedly until no new results are found (a "fixed point").
                </p>

                {/* Visual Diagram */}
                <div className="bg-gradient-to-br from-blue-50 to-green-50 rounded-xl p-6 mb-4">
                  <div className="flex items-center justify-center gap-4">
                    <div className="bg-white rounded-lg shadow-md p-4 w-40 text-center border-2 border-blue-300">
                      <div className="text-blue-600 font-semibold text-sm mb-1">Compatible Pairs</div>
                      <div className="text-xs text-gray-500">Which orders CAN be bundled?</div>
                    </div>
                    <div className="flex flex-col items-center gap-1">
                      <span className="text-green-500 text-lg">→</span>
                      <div className="text-xs text-gray-400 font-medium">feeds into</div>
                      <span className="text-blue-500 text-lg">←</span>
                    </div>
                    <div className="bg-white rounded-lg shadow-md p-4 w-40 text-center border-2 border-green-300">
                      <div className="text-green-600 font-semibold text-sm mb-1">Bundle Membership</div>
                      <div className="text-xs text-gray-500">Which bundle does each order join?</div>
                    </div>
                  </div>
                  <div className="mt-4 flex items-center justify-center gap-2">
                    <div className="flex items-center gap-1">
                      <span className="inline-block w-2 h-2 rounded-full bg-gray-300"></span>
                      <span className="inline-block w-2 h-2 rounded-full bg-gray-400"></span>
                      <span className="inline-block w-2 h-2 rounded-full bg-gray-500"></span>
                      <span className="inline-block w-2 h-2 rounded-full bg-green-500"></span>
                    </div>
                    <span className="text-xs text-gray-500">Iterates until stable</span>
                  </div>
                </div>

                <div className="bg-amber-50 border border-amber-200 rounded-lg p-3">
                  <div className="flex items-start gap-2">
                    <span className="text-amber-500 mt-0.5">💡</span>
                    <p className="text-xs text-amber-800">
                      <span className="font-semibold">Why Materialize?</span> Most databases can't handle mutual recursion.
                      Materialize maintains these complex recursive results incrementally—when an order changes,
                      only affected bundles recompute, not everything.
                    </p>
                  </div>
                </div>
              </div>

              {/* Right: How Bundling Works */}
              <div>
                <h4 className="font-medium text-gray-900 mb-4">How Orders Get Bundled</h4>
                <div className="space-y-3 mb-4">
                  <div className="flex gap-3">
                    <div className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold">1</div>
                    <div>
                      <div className="text-sm font-medium text-gray-900">Each order starts alone</div>
                      <div className="text-xs text-gray-500">Every CREATED order begins in its own bundle</div>
                    </div>
                  </div>
                  <div className="flex gap-3">
                    <div className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold">2</div>
                    <div>
                      <div className="text-sm font-medium text-gray-900">Find compatible pairs</div>
                      <div className="text-xs text-gray-500">Check all constraints between every two orders</div>
                    </div>
                  </div>
                  <div className="flex gap-3">
                    <div className="flex-shrink-0 w-6 h-6 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center text-xs font-bold">3</div>
                    <div>
                      <div className="text-sm font-medium text-gray-900">Merge compatible orders</div>
                      <div className="text-xs text-gray-500">Orders join the smallest compatible bundle</div>
                    </div>
                  </div>
                  <div className="flex gap-3">
                    <div className="flex-shrink-0 w-6 h-6 rounded-full bg-green-100 text-green-600 flex items-center justify-center text-xs font-bold">✓</div>
                    <div>
                      <div className="text-sm font-medium text-gray-900">Repeat until stable</div>
                      <div className="text-xs text-gray-500">Stop when no more merges are possible</div>
                    </div>
                  </div>
                </div>

                <h4 className="font-medium text-gray-900 mb-3">Bundling Constraints</h4>
                <div className="grid grid-cols-2 gap-2">
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <Store className="h-4 w-4 text-gray-400" />
                      <span className="text-sm font-medium text-gray-900">Same Store</span>
                    </div>
                    <p className="text-xs text-gray-500">Orders from the same location</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <Clock className="h-4 w-4 text-gray-400" />
                      <span className="text-sm font-medium text-gray-900">Time Overlap</span>
                    </div>
                    <p className="text-xs text-gray-500">Delivery windows intersect</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <Package className="h-4 w-4 text-gray-400" />
                      <span className="text-sm font-medium text-gray-900">Inventory</span>
                    </div>
                    <p className="text-xs text-gray-500">Stock available for combined qty</p>
                  </div>
                  <div className="bg-gray-50 rounded-lg p-3">
                    <div className="flex items-center gap-2 mb-1">
                      <Scale className="h-4 w-4 text-gray-400" />
                      <span className="text-sm font-medium text-gray-900">Capacity</span>
                    </div>
                    <p className="text-xs text-gray-500">Weight fits courier vehicle</p>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Active Bundles */}
      <div className="bg-white rounded-lg shadow">
        <div className="p-4 border-b">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Truck className="h-5 w-5 text-green-600" />
              <h3 className="font-semibold text-gray-900">Active Bundles</h3>
            </div>
            <div className="flex items-center gap-4 text-sm text-gray-500">
              <span className="flex items-center gap-1">
                <span className="inline-block w-3 h-3 rounded-full bg-green-500"></span>
                {multiBundles.length} bundles ({multiBundles.reduce((sum, b) => sum + (b.bundle_size || 0), 0)} orders)
              </span>
              <span className="flex items-center gap-1">
                <span className="inline-block w-3 h-3 rounded-full bg-gray-300"></span>
                {singletonBundles.length} unbundled
              </span>
            </div>
          </div>
        </div>

        <div className="p-4">
          {bundles.length === 0 ? (
            <div className="text-center py-8 text-gray-500">
              <ShoppingCart className="h-12 w-12 mx-auto mb-3 text-gray-300" />
              <p>No bundles yet. Create orders with overlapping delivery windows to see bundles form.</p>
            </div>
          ) : (
            <div className="space-y-4">
              {/* Multi-order bundles */}
              {Object.entries(bundlesByStore).map(([storeId, storeBundles]) => {
                const multiOrderBundles = storeBundles.filter((b) => (b.bundle_size || 0) > 1)
                if (multiOrderBundles.length === 0) return null

                const storeName = multiOrderBundles[0]?.store_name || storeId

                return (
                  <div key={storeId} className="border rounded-lg overflow-hidden">
                    <div className="bg-gray-50 px-4 py-2 border-b">
                      <div className="flex items-center gap-2">
                        <Store className="h-4 w-4 text-gray-500" />
                        <span className="font-medium text-gray-900">{storeName}</span>
                        <span className="text-xs text-gray-500">
                          ({multiOrderBundles.length} bundle{multiOrderBundles.length !== 1 ? 's' : ''})
                        </span>
                      </div>
                    </div>
                    <div className="divide-y">
                      {multiOrderBundles.map((bundle) => {
                        const isExpanded = expandedBundles.has(bundle.bundle_id)
                        const details = getBundleDetails(bundle.orders || [])

                        return (
                          <div key={bundle.bundle_id} className="p-4">
                            <button
                              onClick={() => toggleBundle(bundle.bundle_id)}
                              className="w-full flex items-center justify-between mb-2 hover:bg-gray-50 -mx-2 px-2 py-1 rounded transition-colors"
                            >
                              <div className="flex items-center gap-2">
                                {isExpanded ? (
                                  <ChevronDown className="h-4 w-4 text-gray-400" />
                                ) : (
                                  <ChevronRight className="h-4 w-4 text-gray-400" />
                                )}
                                <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-green-100 text-green-700 text-sm font-semibold">
                                  {bundle.bundle_size}
                                </span>
                                <span className="text-sm text-gray-600">orders bundled</span>
                              </div>
                              {/* Constraint badges */}
                              <div className="flex items-center gap-1">
                                <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-green-50 text-green-600 text-xs" title="Same Store">
                                  <Store className="h-3 w-3" />
                                  <Check className="h-3 w-3" />
                                </span>
                                <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-green-50 text-green-600 text-xs" title="Time Overlap">
                                  <Clock className="h-3 w-3" />
                                  <Check className="h-3 w-3" />
                                </span>
                                <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-green-50 text-green-600 text-xs" title="Inventory OK">
                                  <Package className="h-3 w-3" />
                                  <Check className="h-3 w-3" />
                                </span>
                                <span className="inline-flex items-center gap-0.5 px-1.5 py-0.5 rounded bg-green-50 text-green-600 text-xs" title="Courier Capacity">
                                  <Scale className="h-3 w-3" />
                                  <Check className="h-3 w-3" />
                                </span>
                              </div>
                            </button>

                            {/* Expanded details */}
                            {isExpanded && details && (
                              <div className="mb-3 ml-6 p-3 bg-green-50 rounded-lg border border-green-100">
                                <div className="text-xs font-medium text-green-800 mb-2">All constraints satisfied:</div>
                                <div className="grid grid-cols-2 gap-2 text-xs">
                                  <div className="flex items-center gap-2">
                                    <Check className="h-3 w-3 text-green-600" />
                                    <span className="text-gray-600">Same Store:</span>
                                    <span className="font-medium text-gray-900">{bundle.store_name}</span>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <Check className="h-3 w-3 text-green-600" />
                                    <span className="text-gray-600">Time Window:</span>
                                    <span className="font-medium text-gray-900">
                                      {formatTime(details.sharedStart)} – {formatTime(details.sharedEnd)}
                                    </span>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <Check className="h-3 w-3 text-green-600" />
                                    <span className="text-gray-600">Inventory:</span>
                                    <span className="font-medium text-gray-900">All products available</span>
                                  </div>
                                  <div className="flex items-center gap-2">
                                    <Check className="h-3 w-3 text-green-600" />
                                    <span className="text-gray-600">Total Weight:</span>
                                    <span className="font-medium text-gray-900">
                                      {formatWeight(details.totalWeight)}
                                      <span className="text-gray-500 ml-1">
                                        ({details.vehicles.bike ? 'BIKE' : details.vehicles.car ? 'CAR' : 'VAN'})
                                      </span>
                                    </span>
                                  </div>
                                </div>
                              </div>
                            )}

                            <div className="flex flex-wrap gap-2 ml-6">
                              {(bundle.orders || []).map((orderId) => (
                                <span
                                  key={orderId}
                                  className="inline-flex items-center px-2 py-1 rounded bg-green-50 text-green-700 text-xs font-mono"
                                >
                                  {orderId.replace('order:', '')}
                                </span>
                              ))}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                )
              })}

              {/* Singleton bundles (unbundled orders) with reasons */}
              {singletonBundles.length > 0 && (
                <div className="border rounded-lg overflow-hidden border-dashed border-amber-300">
                  <div className="bg-amber-50 px-4 py-2 border-b border-amber-200">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="h-4 w-4 text-amber-500" />
                      <span className="font-medium text-amber-800">Unbundled Orders</span>
                      <span className="text-xs text-amber-600">
                        ({singletonBundles.length} order{singletonBundles.length !== 1 ? 's' : ''})
                      </span>
                    </div>
                  </div>
                  <div className="p-4 space-y-2">
                    {singletonBundles.map((bundle) => {
                      const reason = getUnbundledReason(bundle.bundle_id, bundle.store_id)
                      return (
                        <div
                          key={bundle.bundle_id}
                          className="flex items-start gap-3 p-2 rounded bg-gray-50"
                        >
                          <span className="inline-flex items-center px-2 py-1 rounded bg-gray-200 text-gray-700 text-xs font-mono">
                            {bundle.bundle_id.replace('order:', '')}
                          </span>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-1.5 text-xs text-amber-700">
                              {reason.type === 'only_order' && <Store className="h-3 w-3" />}
                              {reason.type === 'no_overlap' && <Clock className="h-3 w-3" />}
                              {reason.type === 'transitive' && <AlertTriangle className="h-3 w-3" />}
                              <span>{reason.message}</span>
                            </div>
                            <div className="text-xs text-gray-500 mt-0.5">
                              {bundle.store_name || bundle.store_id}
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
