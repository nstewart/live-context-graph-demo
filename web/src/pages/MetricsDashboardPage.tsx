import { useState, useEffect, useMemo } from "react";
import { useZero, useQuery } from "@rocicorp/zero/react";
import { Schema } from "../schema";
import { formatAmount } from "../test/utils";
import { useMetricsTimeseries } from "../hooks/useMetricsTimeseries";
import {
  AlertTriangle,
  Activity,
  Wifi,
  WifiOff,
  DollarSign,
  Package,
  Store,
  Users,
  Clock,
  TrendingUp,
  TrendingDown,
  Minus,
} from "lucide-react";

// Simple SVG sparkline component
function Sparkline({
  data,
  width = 80,
  height = 24,
  color = '#6366f1'
}: {
  data: number[],
  width?: number,
  height?: number,
  color?: string
}) {
  if (data.length < 2) return <div className="w-20 h-6 bg-gray-100 rounded animate-pulse" />

  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1

  const points = data.map((value, i) => {
    const x = (i / (data.length - 1)) * width
    const y = height - ((value - min) / range) * (height - 4) - 2
    return `${x},${y}`
  }).join(' ')

  return (
    <svg width={width} height={height} className="inline-block">
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        points={points}
      />
    </svg>
  )
}

// Stacked area chart for system-wide metrics (responsive)
function StackedAreaChart({
  data1,
  data2,
  label1,
  label2,
  color1 = '#6366f1',
  color2 = '#a5b4fc',
}: {
  data1: number[],
  data2: number[],
  label1: string,
  label2: string,
  color1?: string,
  color2?: string,
}) {
  if (data1.length < 2) {
    return <div className="w-full h-32 bg-gray-100 rounded animate-pulse" />
  }

  // Use fixed viewBox dimensions for consistent rendering
  const viewWidth = 400
  const viewHeight = 120
  const padding = { top: 10, right: 10, bottom: 20, left: 35 }
  const chartWidth = viewWidth - padding.left - padding.right
  const chartHeight = viewHeight - padding.top - padding.bottom

  // Stack the data
  const stacked = data1.map((v, i) => v + (data2[i] || 0))
  const maxVal = Math.max(...stacked, 1)
  const currentTotal = stacked[stacked.length - 1] || 0

  // Generate area paths
  const getY = (val: number) => chartHeight - (val / maxVal) * chartHeight

  // Bottom area (data1)
  const area1Points = data1.map((v, i) => {
    const x = (i / (data1.length - 1)) * chartWidth
    const y = getY(v)
    return `${x},${y}`
  })
  const area1Path = `M0,${chartHeight} L${area1Points.join(' L')} L${chartWidth},${chartHeight} Z`

  // Top area (stacked)
  const area2Points = stacked.map((v, i) => {
    const x = (i / (stacked.length - 1)) * chartWidth
    const y = getY(v)
    return `${x},${y}`
  })
  const area2BottomPoints = [...data1].reverse().map((v, i) => {
    const x = ((data1.length - 1 - i) / (data1.length - 1)) * chartWidth
    const y = getY(v)
    return `${x},${y}`
  })
  const area2Path = `M${area2Points.join(' L')} L${area2BottomPoints.join(' L')} Z`

  // Y-axis ticks
  const yTicks = [0, Math.round(maxVal / 2), Math.round(maxVal)]

  return (
    <div className="relative w-full">
      <svg
        viewBox={`0 0 ${viewWidth} ${viewHeight}`}
        className="w-full h-auto"
        preserveAspectRatio="xMidYMid meet"
      >
        <g transform={`translate(${padding.left}, ${padding.top})`}>
          {/* Y-axis */}
          {yTicks.map((tick, i) => (
            <g key={i}>
              <line
                x1={0}
                y1={getY(tick)}
                x2={chartWidth}
                y2={getY(tick)}
                stroke="#e5e7eb"
                strokeDasharray="2,2"
              />
              <text
                x={-5}
                y={getY(tick)}
                textAnchor="end"
                alignmentBaseline="middle"
                className="text-[10px] fill-gray-400"
              >
                {tick}
              </text>
            </g>
          ))}

          {/* Stacked areas */}
          <path d={area2Path} fill={color2} opacity={0.7} />
          <path d={area1Path} fill={color1} opacity={0.9} />
        </g>
      </svg>

      {/* Legend */}
      <div className="flex items-center justify-center gap-4 mt-1">
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded" style={{ backgroundColor: color1 }} />
          <span className="text-[10px] text-gray-500">{label1}</span>
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded" style={{ backgroundColor: color2 }} />
          <span className="text-[10px] text-gray-500">{label2}</span>
        </div>
      </div>

      {/* Current value badge */}
      <div className="absolute top-1 right-1 bg-gray-900 text-white text-xs px-2 py-0.5 rounded">
        {currentTotal}
      </div>
    </div>
  )
}

// Line chart with optional secondary line (responsive)
function TimeSeriesLineChart({
  data,
  data2,
  label,
  label2,
  color = '#f59e0b',
  color2 = '#fcd34d',
  unit = '',
  decimals = 1,
}: {
  data: number[],
  data2?: number[],
  label: string,
  label2?: string,
  color?: string,
  color2?: string,
  unit?: string,
  decimals?: number,
}) {
  if (data.length < 2) {
    return <div className="w-full h-32 bg-gray-100 rounded animate-pulse" />
  }

  // Use fixed viewBox dimensions for consistent rendering
  const viewWidth = 400
  const viewHeight = 120
  const padding = { top: 10, right: 10, bottom: 20, left: 35 }
  const chartWidth = viewWidth - padding.left - padding.right
  const chartHeight = viewHeight - padding.top - padding.bottom

  const allData = data2 ? [...data, ...data2] : data
  const maxVal = Math.max(...allData, 0.1)
  const minVal = Math.min(...allData, 0)
  const range = maxVal - minVal || 1
  const currentVal = data[data.length - 1] || 0

  const getY = (val: number) => chartHeight - ((val - minVal) / range) * chartHeight

  // Primary line
  const linePoints = data.map((v, i) => {
    const x = (i / (data.length - 1)) * chartWidth
    const y = getY(v)
    return `${x},${y}`
  }).join(' ')

  // Secondary line (optional)
  const line2Points = data2?.map((v, i) => {
    const x = (i / (data2.length - 1)) * chartWidth
    const y = getY(v)
    return `${x},${y}`
  }).join(' ')

  // Y-axis ticks
  const yTicks = [minVal, (maxVal + minVal) / 2, maxVal]

  return (
    <div className="relative w-full">
      <svg
        viewBox={`0 0 ${viewWidth} ${viewHeight}`}
        className="w-full h-auto"
        preserveAspectRatio="xMidYMid meet"
      >
        <g transform={`translate(${padding.left}, ${padding.top})`}>
          {/* Y-axis */}
          {yTicks.map((tick, i) => (
            <g key={i}>
              <line
                x1={0}
                y1={getY(tick)}
                x2={chartWidth}
                y2={getY(tick)}
                stroke="#e5e7eb"
                strokeDasharray="2,2"
              />
              <text
                x={-5}
                y={getY(tick)}
                textAnchor="end"
                alignmentBaseline="middle"
                className="text-[10px] fill-gray-400"
              >
                {tick.toFixed(decimals)}
              </text>
            </g>
          ))}

          {/* Secondary line (drawn first, behind primary) */}
          {line2Points && (
            <polyline
              fill="none"
              stroke={color2}
              strokeWidth="1.5"
              strokeDasharray="4,2"
              points={line2Points}
              opacity={0.7}
            />
          )}

          {/* Primary line */}
          <polyline
            fill="none"
            stroke={color}
            strokeWidth="2"
            points={linePoints}
          />

          {/* Current value dot */}
          <circle
            cx={chartWidth}
            cy={getY(currentVal)}
            r={4}
            fill={color}
          />
        </g>
      </svg>

      {/* Legend */}
      <div className="flex items-center justify-center gap-4 mt-1">
        <div className="flex items-center gap-1">
          <div className="w-3 h-0.5 rounded" style={{ backgroundColor: color }} />
          <span className="text-[10px] text-gray-500">{label}</span>
        </div>
        {label2 && (
          <div className="flex items-center gap-1">
            <div className="w-3 h-0.5 rounded" style={{ backgroundColor: color2 }} />
            <span className="text-[10px] text-gray-500">{label2}</span>
          </div>
        )}
      </div>

      {/* Current value badge */}
      <div className="absolute top-1 right-1 bg-gray-900 text-white text-xs px-2 py-0.5 rounded">
        {currentVal.toFixed(decimals)}{unit}
      </div>
    </div>
  )
}

// Delta indicator component showing change from previous value
function DeltaIndicator({
  current,
  previous,
  suffix = '',
  higherIsBetter = false
}: {
  current: number | null | undefined,
  previous: number | null | undefined,
  suffix?: string,
  higherIsBetter?: boolean
}) {
  if (current == null || previous == null) {
    return <span className="text-xs text-gray-400">--</span>
  }

  const delta = current - previous
  if (Math.abs(delta) < 0.01) {
    return (
      <span className="inline-flex items-center text-xs text-gray-400">
        <Minus className="h-3 w-3" />
      </span>
    )
  }

  const isPositive = delta > 0
  const isGood = higherIsBetter ? isPositive : !isPositive
  const color = isGood ? 'text-green-600' : 'text-red-600'
  const Icon = isPositive ? TrendingUp : TrendingDown

  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-medium ${color}`}>
      <Icon className="h-3 w-3" />
      {isPositive ? '+' : ''}{delta.toFixed(1)}{suffix}
    </span>
  )
}

type StoreMetrics = {
  store_id: string
  store_name: string
  store_zone: string
  total_couriers: number
  available_couriers: number
  busy_couriers: number
  off_shift_couriers: number
  orders_in_queue: number
  orders_picking: number
  orders_delivering: number
  utilization_pct: number
  health_status: 'HEALTHY' | 'WARNING' | 'CRITICAL'
  avg_wait_minutes: number | null
  orders_at_risk: number
}

const healthStatusColors = {
  HEALTHY: 'bg-green-500',
  WARNING: 'bg-yellow-500',
  CRITICAL: 'bg-red-500',
}

export default function MetricsDashboardPage() {
  const z = useZero<Schema>();
  const [lastUpdateTime, setLastUpdateTime] = useState<number>(Date.now());

  // Real-time metrics data via Zero
  const [pricingYieldData] = useQuery(z.query.pricing_yield_mv);
  const [inventoryRiskData] = useQuery(z.query.inventory_risk_mv);
  const [capacityHealthData] = useQuery(z.query.store_capacity_health_mv);

  // Additional data for Store Demand vs Capacity table
  const [storesData] = useQuery(z.query.stores_mv.orderBy('store_id', 'asc'));
  const [couriersData] = useQuery(z.query.courier_schedule_mv.orderBy('courier_id', 'asc'));
  const [ordersData] = useQuery(z.query.orders_with_lines_mv);

  // Time-series data for sparklines and rollup charts (via direct API polling, not Zero)
  // Zero doesn't support these views because Materialize lacks UNIQUE indexes
  const { storeTimeseries, systemTimeseries, isLoading: timeseriesLoading } = useMetricsTimeseries(1000, 10);

  // Extract system-wide time-series arrays for charts
  const systemChartData = useMemo(() => {
    if (systemTimeseries.length === 0) {
      return {
        queueDepth: [],
        inProgress: [],
        totalOrders: [],
        avgWait: [],
        maxWait: [],
        throughput: [],
      }
    }
    return {
      queueDepth: systemTimeseries.map(d => d.total_queue_depth),
      inProgress: systemTimeseries.map(d => d.total_in_progress),
      totalOrders: systemTimeseries.map(d => d.total_orders),
      avgWait: systemTimeseries.map(d => d.avg_wait_minutes ?? 0),
      maxWait: systemTimeseries.map(d => d.max_wait_minutes ?? 0),
      throughput: systemTimeseries.map(d => d.total_orders_picked_up),
    }
  }, [systemTimeseries]);

  useEffect(() => {
    if (pricingYieldData.length > 0 || inventoryRiskData.length > 0 || capacityHealthData.length > 0) {
      setLastUpdateTime(Date.now());
    }
  }, [pricingYieldData, inventoryRiskData, capacityHealthData]);

  // Calculate aggregate metrics
  const metrics = useMemo(() => {
    // 1. Pricing Yield
    const totalPremium = pricingYieldData.reduce((sum, r) => sum + (r.price_premium || 0), 0);
    const totalBase = pricingYieldData.reduce((sum, r) => sum + ((r.base_price || 0) * (r.quantity || 0)), 0);
    const yieldRate = totalBase > 0 ? (totalPremium / totalBase) * 100 : 0;

    // 2. Inventory Risk
    const criticalItems = inventoryRiskData.filter(i => i.risk_level === 'CRITICAL').length;
    const highRiskItems = inventoryRiskData.filter(i => i.risk_level === 'HIGH').length;
    const totalRevAtRisk = inventoryRiskData
      .filter(i => i.risk_level === 'CRITICAL' || i.risk_level === 'HIGH')
      .reduce((sum, i) => sum + (i.revenue_at_risk || 0), 0);

    // 3. Capacity Health
    const criticalStores = capacityHealthData.filter(s => s.health_status === 'CRITICAL').length;
    const strainedStores = capacityHealthData.filter(s => s.health_status === 'STRAINED').length;
    const avgUtilization = capacityHealthData.length > 0
      ? capacityHealthData.reduce((sum, s) => sum + (s.current_utilization_pct || 0), 0) / capacityHealthData.length
      : 0;

    return {
      pricingYield: { totalPremium, totalBase, yieldRate },
      inventoryRisk: { criticalItems, highRiskItems, totalRevAtRisk },
      capacityHealth: { criticalStores, strainedStores, avgUtilization },
    };
  }, [pricingYieldData, inventoryRiskData, capacityHealthData]);

  // Compute store demand vs capacity metrics
  const storeMetrics: StoreMetrics[] = useMemo(() => {
    if (storesData.length === 0) return []

    const now = Date.now()

    return storesData.map((store) => {
      // Count couriers by status for this store
      const storeCouriers = couriersData.filter(c => c.home_store_id === store.store_id)
      const total = storeCouriers.length
      const available = storeCouriers.filter(c => c.courier_status === 'AVAILABLE').length
      const busy = storeCouriers.filter(c => c.courier_status === 'PICKING' || c.courier_status === 'DELIVERING' || c.courier_status === 'ON_DELIVERY').length
      const offShift = storeCouriers.filter(c => c.courier_status === 'OFF_SHIFT').length

      // Count orders by status for this store
      const storeOrders = ordersData.filter(o => o.store_id === store.store_id)
      const inQueue = storeOrders.filter(o => o.order_status === 'CREATED').length
      const picking = storeOrders.filter(o => o.order_status === 'PICKING').length
      const delivering = storeOrders.filter(o => o.order_status === 'OUT_FOR_DELIVERY').length

      // Calculate utilization
      const utilization = total > 0 ? (busy / total) * 100 : 0

      // Determine health status
      let health: 'HEALTHY' | 'WARNING' | 'CRITICAL' = 'HEALTHY'
      if (available === 0 && inQueue > 0) {
        health = 'CRITICAL'
      } else if (utilization >= 80 || (inQueue > available * 5)) {
        health = 'WARNING'
      }

      // Calculate avg wait time from tasks with order_created_at and task_started_at
      const waitTimes: number[] = []
      storeCouriers.forEach(courier => {
        const tasks = (courier.tasks as any[]) || []
        tasks.forEach(task => {
          if (task.order_created_at && task.task_started_at) {
            const created = new Date(task.order_created_at).getTime()
            const started = new Date(task.task_started_at).getTime()
            if (started > created) {
              waitTimes.push((started - created) / 60000) // minutes
            }
          }
        })
      })
      const avgWait = waitTimes.length > 0
        ? waitTimes.reduce((a, b) => a + b, 0) / waitTimes.length
        : null

      // Calculate orders at risk (waiting more than 3 minutes for courier assignment)
      const atRisk = storeOrders.filter(o => {
        if (o.order_status === 'DELIVERED' || o.order_status === 'CANCELLED') return false
        if (o.order_status !== 'CREATED') return false // Only count orders still in queue
        if (!o.order_created_at) return false
        // order_created_at is epoch milliseconds from Zero
        const createdAt = typeof o.order_created_at === 'number' ? o.order_created_at : new Date(o.order_created_at).getTime()
        const waitTime = now - createdAt
        return waitTime > 3 * 60 * 1000 // waiting more than 3 minutes
      }).length

      return {
        store_id: store.store_id,
        store_name: store.store_name || store.store_id,
        store_zone: store.store_zone || '',
        total_couriers: total,
        available_couriers: available,
        busy_couriers: busy,
        off_shift_couriers: offShift,
        orders_in_queue: inQueue,
        orders_picking: picking,
        orders_delivering: delivering,
        utilization_pct: utilization,
        health_status: health,
        avg_wait_minutes: avgWait,
        orders_at_risk: atRisk,
      }
    }).sort((a, b) => a.store_name.localeCompare(b.store_name))
  }, [storesData, couriersData, ordersData]);

  // Helper to get sparkline data for a store
  const getStoreSparklineData = (storeId: string, field: 'queue_depth' | 'avg_wait_minutes'): number[] => {
    const data = storeTimeseries[storeId]
    if (!data || data.length === 0) return []
    return data.map(d => field === 'queue_depth' ? d.queue_depth : (d.avg_wait_minutes ?? 0))
  }

  // Helper to get delta values (current vs previous window)
  const getStoreDelta = (storeId: string, field: 'queue_depth' | 'avg_wait_minutes'): { current: number | null, previous: number | null } => {
    const data = storeTimeseries[storeId]
    if (!data || data.length < 2) return { current: null, previous: null }
    const current = field === 'queue_depth' ? data[data.length - 1].queue_depth : data[data.length - 1].avg_wait_minutes
    const previous = field === 'queue_depth' ? data[data.length - 2].queue_depth : data[data.length - 2].avg_wait_minutes
    return { current, previous }
  }

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">Live Metrics Dashboard</h1>
            {z.online ? (
              <span className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-green-700 bg-green-100 rounded-full">
                <Wifi className="h-3 w-3" />
                Real-time
              </span>
            ) : (
              <span className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-amber-700 bg-amber-100 rounded-full">
                <WifiOff className="h-3 w-3" />
                Connecting...
              </span>
            )}
            <span className="text-xs text-gray-500">
              Last update: {new Date(lastUpdateTime).toLocaleTimeString()}
            </span>
          </div>
          <p className="text-gray-600">Real-time business health indicators</p>
        </div>
      </div>

      {/* Top-line KPIs */}
      <div className="grid grid-cols-3 gap-6 mb-6">
        {/* Pricing Yield */}
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-500">Dynamic Pricing Yield</h3>
            <DollarSign className="h-5 w-5 text-green-600" />
          </div>
          <p className="text-xs text-gray-500 mb-4">
            Revenue premium captured above base catalog prices through dynamic pricing
          </p>
          <div className="text-3xl font-bold text-gray-900 mb-2">
            {metrics.pricingYield.yieldRate.toFixed(1)}%
          </div>
          <div className="text-sm text-gray-600">
            ${formatAmount(metrics.pricingYield.totalPremium)} premium captured
          </div>
          <div className="text-xs text-gray-400 mt-1">
            from ${formatAmount(metrics.pricingYield.totalBase)} base revenue
          </div>
        </div>

        {/* Inventory Risk */}
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-500">Revenue at Risk</h3>
            <AlertTriangle className="h-5 w-5 text-red-600" />
          </div>
          <p className="text-xs text-gray-500 mb-4">
            Order value at risk due to low inventory levels with pending customer orders
          </p>
          <div className="text-3xl font-bold text-gray-900 mb-2">
            ${formatAmount(metrics.inventoryRisk.totalRevAtRisk)}
          </div>
          <div className="text-sm text-gray-600">
            {metrics.inventoryRisk.criticalItems} critical, {metrics.inventoryRisk.highRiskItems} high risk items
          </div>
        </div>

        {/* Capacity Health */}
        <div className="bg-white rounded-lg shadow p-6">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-medium text-gray-500">Avg Store Utilization</h3>
            <Activity className="h-5 w-5 text-blue-600" />
          </div>
          <p className="text-xs text-gray-500 mb-4">
            Current order volume as percentage of maximum store capacity per hour
          </p>
          <div className="text-3xl font-bold text-gray-900 mb-2">
            {metrics.capacityHealth.avgUtilization.toFixed(1)}%
          </div>
          <div className="text-sm text-gray-600">
            {metrics.capacityHealth.criticalStores} critical, {metrics.capacityHealth.strainedStores} strained stores
          </div>
        </div>
      </div>

      {/* System Throughput Panel - Rolled up time-series from all stores */}
      <div className="mb-6">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-semibold text-gray-900">System Throughput</h2>
          <span className="text-xs text-gray-500">
            Rolled up from {Object.keys(storeTimeseries).length} stores
          </span>
        </div>
        <div className="grid grid-cols-3 gap-6">
          {/* Orders In Flight */}
          <div className="bg-white rounded-lg shadow p-4">
            <h3 className="text-sm font-medium text-gray-700 mb-2">Orders In Flight</h3>
            <p className="text-xs text-gray-500 mb-3">
              Orders currently in queue or being processed
            </p>
            <StackedAreaChart
              data1={systemChartData.queueDepth}
              data2={systemChartData.inProgress}
              label1="In Queue"
              label2="In Progress"
              color1="#6366f1"
              color2="#a5b4fc"
            />
          </div>

          {/* Wait Times */}
          <div className="bg-white rounded-lg shadow p-4">
            <h3 className="text-sm font-medium text-gray-700 mb-2">Wait Times</h3>
            <p className="text-xs text-gray-500 mb-3">
              Time from order creation to courier pickup (minutes)
            </p>
            <TimeSeriesLineChart
              data={systemChartData.avgWait}
              data2={systemChartData.maxWait}
              label="Avg"
              label2="Max"
              color="#f59e0b"
              color2="#fcd34d"
              unit="m"
              decimals={2}
            />
          </div>

          {/* Throughput */}
          <div className="bg-white rounded-lg shadow p-4">
            <h3 className="text-sm font-medium text-gray-700 mb-2">Throughput</h3>
            <p className="text-xs text-gray-500 mb-3">
              Orders picked up per minute window
            </p>
            <TimeSeriesLineChart
              data={systemChartData.throughput}
              label="Picked Up"
              color="#10b981"
              unit=""
              decimals={0}
            />
          </div>
        </div>
      </div>

      {/* Store Demand vs Capacity Table */}
      {storeMetrics.length > 0 && (
        <div className="mb-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-3">Store Demand vs Capacity</h2>
          <div className="bg-white rounded-lg shadow overflow-hidden">
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Store
                    </th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Health
                    </th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      <span className="flex items-center gap-1">
                        <Users className="h-3.5 w-3.5" />
                        Couriers
                      </span>
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      <span className="flex items-center justify-end gap-1">
                        <Package className="h-3.5 w-3.5" />
                        Queue
                      </span>
                    </th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Queue Trend
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      <span className="flex items-center justify-end gap-1">
                        <Clock className="h-3.5 w-3.5" />
                        Avg Wait
                      </span>
                    </th>
                    <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Wait Trend
                    </th>
                    <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                      At Risk
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {storeMetrics.map((metrics) => {
                    const queueData = getStoreSparklineData(metrics.store_id, 'queue_depth')
                    const waitData = getStoreSparklineData(metrics.store_id, 'avg_wait_minutes')
                    const queueDelta = getStoreDelta(metrics.store_id, 'queue_depth')
                    const waitDelta = getStoreDelta(metrics.store_id, 'avg_wait_minutes')

                    return (
                      <tr key={metrics.store_id} className="hover:bg-gray-50">
                        <td className="px-4 py-3 whitespace-nowrap">
                          <div className="text-sm font-medium text-gray-900">{metrics.store_name}</div>
                          <div className="text-xs text-gray-500">{metrics.store_zone}</div>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-center">
                          <span
                            className={`inline-block w-3 h-3 rounded-full ${healthStatusColors[metrics.health_status]}`}
                            title={metrics.health_status}
                          />
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap">
                          <span className="text-sm text-gray-900">
                            {metrics.available_couriers}/{metrics.total_couriers}
                          </span>
                          <span className="text-xs text-gray-500 ml-1">avail</span>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-right">
                          <span className={`text-sm font-medium ${metrics.orders_in_queue > 0 ? 'text-gray-900' : 'text-gray-400'}`}>
                            {metrics.orders_in_queue}
                          </span>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-center">
                          <div className="flex items-center justify-center gap-2">
                            {timeseriesLoading ? (
                              <div className="w-20 h-6 bg-gray-100 rounded animate-pulse" />
                            ) : queueData.length >= 2 ? (
                              <>
                                <Sparkline data={queueData} color="#6366f1" />
                                <DeltaIndicator
                                  current={queueDelta.current}
                                  previous={queueDelta.previous}
                                  higherIsBetter={false}
                                />
                              </>
                            ) : (
                              <span className="text-xs text-gray-400">--</span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-right">
                          <span className={`text-sm ${metrics.avg_wait_minutes !== null ? 'text-gray-900' : 'text-gray-400'}`}>
                            {metrics.avg_wait_minutes !== null ? `${metrics.avg_wait_minutes.toFixed(1)}m` : '-'}
                          </span>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-center">
                          <div className="flex items-center justify-center gap-2">
                            {timeseriesLoading ? (
                              <div className="w-20 h-6 bg-gray-100 rounded animate-pulse" />
                            ) : waitData.length >= 2 ? (
                              <>
                                <Sparkline data={waitData} color="#f59e0b" />
                                <DeltaIndicator
                                  current={waitDelta.current}
                                  previous={waitDelta.previous}
                                  suffix="m"
                                  higherIsBetter={false}
                                />
                              </>
                            ) : (
                              <span className="text-xs text-gray-400">--</span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-3 whitespace-nowrap text-right">
                          <span className={`text-sm font-medium ${
                            metrics.orders_at_risk > 0 ? 'text-red-600' : 'text-gray-400'
                          }`}>
                            {metrics.orders_at_risk}
                          </span>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Detailed Tables */}
      <div className="grid grid-cols-2 gap-6">
        {/* Inventory Risk Detail */}
        <div className="bg-white rounded-lg shadow">
          <div className="p-4 border-b">
            <h3 className="font-semibold text-gray-900 flex items-center gap-2">
              <Package className="h-5 w-5" />
              High-Risk Inventory
            </h3>
            <p className="text-xs text-gray-500 mt-1">
              Products with low stock levels that have pending customer orders (may cause stockouts)
            </p>
          </div>
          <div className="overflow-x-auto max-h-96">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Product</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Store</th>
                  <th className="px-4 py-2 text-center text-xs font-medium text-gray-500">Stock</th>
                  <th className="px-4 py-2 text-center text-xs font-medium text-gray-500">Pending</th>
                  <th className="px-4 py-2 text-center text-xs font-medium text-gray-500">Risk</th>
                  <th className="px-4 py-2 text-right text-xs font-medium text-gray-500">$ at Risk</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {inventoryRiskData
                  .filter(i => i.risk_level === 'CRITICAL' || i.risk_level === 'HIGH')
                  .sort((a, b) => (b.revenue_at_risk || 0) - (a.revenue_at_risk || 0))
                  .slice(0, 20)
                  .map((item) => (
                    <tr key={item.inventory_id} className="hover:bg-gray-50">
                      <td className="px-4 py-2">
                        <div className="font-medium text-gray-900">{item.product_name}</div>
                        <div className="text-xs text-gray-400">{item.inventory_id}</div>
                      </td>
                      <td className="px-4 py-2 text-gray-600">{item.store_name}</td>
                      <td className="px-4 py-2 text-center">{item.stock_level}</td>
                      <td className="px-4 py-2 text-center">
                        <span className="text-amber-600 font-medium">{item.pending_reservations || 0}</span>
                      </td>
                      <td className="px-4 py-2 text-center">
                        <span className={`px-2 py-1 text-xs rounded-full ${
                          item.risk_level === 'CRITICAL' ? 'bg-red-100 text-red-800' : 'bg-orange-100 text-orange-800'
                        }`}>
                          {item.risk_level}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-right font-medium">
                        ${formatAmount(item.revenue_at_risk || 0)}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Store Capacity Detail */}
        <div className="bg-white rounded-lg shadow">
          <div className="p-4 border-b">
            <h3 className="font-semibold text-gray-900 flex items-center gap-2">
              <Store className="h-5 w-5" />
              Store Capacity Status
            </h3>
            <p className="text-xs text-gray-500 mt-1">
              Real-time store workload with automated recommendations for demand management
            </p>
          </div>
          <div className="overflow-x-auto max-h-96">
            <table className="min-w-full text-sm">
              <thead className="bg-gray-50 sticky top-0">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Store</th>
                  <th className="px-4 py-2 text-center text-xs font-medium text-gray-500">Utilization</th>
                  <th className="px-4 py-2 text-center text-xs font-medium text-gray-500">Status</th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {capacityHealthData
                  .sort((a, b) => (b.current_utilization_pct || 0) - (a.current_utilization_pct || 0))
                  .map((store) => (
                    <tr key={store.store_id} className="hover:bg-gray-50">
                      <td className="px-4 py-2">
                        <div>{store.store_name}</div>
                        <div className="text-xs text-gray-500">{store.store_zone}</div>
                      </td>
                      <td className="px-4 py-2 text-center font-medium">
                        {store.current_utilization_pct?.toFixed(1)}%
                      </td>
                      <td className="px-4 py-2 text-center">
                        <span className={`px-2 py-1 text-xs rounded-full ${
                          store.health_status === 'CRITICAL' ? 'bg-red-100 text-red-800' :
                          store.health_status === 'STRAINED' ? 'bg-yellow-100 text-yellow-800' :
                          store.health_status === 'HEALTHY' ? 'bg-green-100 text-green-800' :
                          'bg-blue-100 text-blue-800'
                        }`}>
                          {store.health_status}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-sm text-gray-600">
                        {store.recommended_action?.replace('_', ' ')}
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
