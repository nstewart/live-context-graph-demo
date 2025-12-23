import { useState, useEffect, useRef, useCallback } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import {
  Activity,
  Play,
  Square,
  Wifi,
  WifiOff,
  BarChart3,
  Database,
  Zap,
  Clock,
  Edit3,
  ShoppingCart,
  User,
  Store,
  Package,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import {
  queryStatsApi,
  QueryStatsResponse,
  QueryStatsHistoryResponse,
  QueryStatsOrder,
  OrderDataResponse,
  OrderWithLinesData,
  OrderPredicate,
  OrderLineItem,
} from "../api/client";

interface ChartDataPoint {
  time: number;
  postgresql: number | null;
  batch: number | null;
  materialize: number | null;
}

// Status badge component
const StatusBadge = ({ status }: { status: string | null }) => {
  const getStatusColor = (s: string | null) => {
    switch (s?.toUpperCase()) {
      case "PLACED":
        return "bg-blue-100 text-blue-800";
      case "PICKING":
        return "bg-yellow-100 text-yellow-800";
      case "PICKED":
        return "bg-orange-100 text-orange-800";
      case "DELIVERING":
        return "bg-purple-100 text-purple-800";
      case "DELIVERED":
        return "bg-green-100 text-green-800";
      case "CANCELLED":
        return "bg-red-100 text-red-800";
      default:
        return "bg-gray-100 text-gray-800";
    }
  };

  return (
    <span className={`px-2 py-1 text-xs font-medium rounded ${getStatusColor(status)}`}>
      {status || "UNKNOWN"}
    </span>
  );
};

// Order Card component that displays order data from a single source
interface OrderCardProps {
  title: string;
  subtitle: string;
  icon: React.ReactNode;
  iconColor: string;
  bgColor: string;
  order: OrderWithLinesData | null;
  isLoading: boolean;
}

const OrderCard = ({ title, subtitle, icon, iconColor, bgColor, order, isLoading }: OrderCardProps) => {
  const [isExpanded, setIsExpanded] = useState(true);

  if (!order && !isLoading) {
    return (
      <div className={`bg-white rounded-lg shadow border-t-4 ${bgColor}`}>
        <div className="p-4">
          <div className="flex items-center gap-2 mb-2">
            <span className={iconColor}>{icon}</span>
            <div>
              <h4 className="font-semibold text-gray-900">{title}</h4>
              <p className="text-xs text-gray-500">{subtitle}</p>
            </div>
          </div>
          <div className="text-center py-8 text-gray-500">
            No data - start polling to load
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className={`bg-white rounded-lg shadow border-t-4 ${bgColor}`}>
      <div className="p-4">
        {/* Header */}
        <div className="flex items-center gap-2 mb-3">
          <span className={iconColor}>{icon}</span>
          <div>
            <h4 className="font-semibold text-gray-900">{title}</h4>
            <p className="text-xs text-gray-500">{subtitle}</p>
          </div>
        </div>

        {isLoading && !order ? (
          <div className="animate-pulse space-y-2">
            <div className="h-4 bg-gray-200 rounded w-3/4"></div>
            <div className="h-4 bg-gray-200 rounded w-1/2"></div>
            <div className="h-4 bg-gray-200 rounded w-2/3"></div>
          </div>
        ) : order ? (
          <>
            {/* Order Info */}
            <div className="space-y-2 text-sm">
              <div className="flex justify-between items-center">
                <span className="text-gray-600 flex items-center gap-1">
                  <ShoppingCart className="h-3 w-3" />
                  Order
                </span>
                <span className="font-mono font-medium">{order.order_number || order.order_id}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-600">Status</span>
                <StatusBadge status={order.order_status} />
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-600 flex items-center gap-1">
                  <User className="h-3 w-3" />
                  Customer
                </span>
                <span className="text-right truncate max-w-[150px]">{order.customer_name || "-"}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-600 flex items-center gap-1">
                  <Store className="h-3 w-3" />
                  Store
                </span>
                <span className="text-right truncate max-w-[150px]">{order.store_name || "-"}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-600">Total</span>
                <span className="font-semibold">
                  ${order.order_total_amount?.toFixed(2) || order.computed_total?.toFixed(2) || "0.00"}
                </span>
              </div>
            </div>

            {/* Line Items */}
            {order.line_items && order.line_items.length > 0 && (
              <div className="mt-3 pt-3 border-t">
                <button
                  onClick={() => setIsExpanded(!isExpanded)}
                  className="flex items-center gap-1 text-sm text-gray-600 hover:text-gray-900"
                >
                  {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                  <Package className="h-3 w-3" />
                  {order.line_item_count || order.line_items.length} items
                  {order.has_perishable_items && (
                    <span className="ml-1 text-xs text-amber-600">*perishable</span>
                  )}
                </button>
                {isExpanded && (
                  <div className="mt-2 space-y-1 max-h-[200px] overflow-y-auto">
                    {order.line_items.map((item: OrderLineItem) => (
                      <div
                        key={item.line_id}
                        className="flex justify-between text-xs py-1 px-2 bg-gray-50 rounded"
                      >
                        <span className="truncate max-w-[100px]">
                          {item.product_name || item.product_id}
                        </span>
                        <div className="flex items-center gap-2">
                          <span className="text-gray-600">
                            {item.quantity} x
                          </span>
                          {item.live_price != null ? (
                            <div className="flex flex-col items-end">
                              <span className="font-medium text-blue-600">
                                ${item.live_price.toFixed(2)}
                              </span>
                              {item.price_change != null && item.price_change !== 0 && (
                                <span className={`text-[10px] ${item.price_change > 0 ? 'text-green-600' : 'text-red-600'}`}>
                                  {item.price_change > 0 ? '+' : ''}${item.price_change.toFixed(2)}
                                </span>
                              )}
                            </div>
                          ) : (
                            <span className="text-gray-500">${item.unit_price?.toFixed(2)}</span>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {/* Timestamp */}
            <div className="mt-3 pt-2 border-t text-xs text-gray-400">
              Updated: {order.effective_updated_at ? new Date(order.effective_updated_at).toLocaleTimeString() : "-"}
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
};

export default function QueryStatisticsPage() {
  const [orders, setOrders] = useState<QueryStatsOrder[]>([]);
  const [predicates, setPredicates] = useState<OrderPredicate[]>([]);
  const [selectedOrderId, setSelectedOrderId] = useState<string>("");
  const [isPolling, setIsPolling] = useState(false);
  const [metrics, setMetrics] = useState<QueryStatsResponse | null>(null);
  const [orderData, setOrderData] = useState<OrderDataResponse | null>(null);
  const [chartData, setChartData] = useState<ChartDataPoint[]>([]);
  const [useLogScale, setUseLogScale] = useState(true);
  const [lastUpdateTime, setLastUpdateTime] = useState<number>(Date.now());
  const [error, setError] = useState<string | null>(null);

  // Triple writer state
  const [tripleSubject, setTripleSubject] = useState("");
  const [triplePredicate, setTriplePredicate] = useState("order_status");
  const [tripleValue, setTripleValue] = useState("");
  const [writeStatus, setWriteStatus] = useState<string | null>(null);

  const metricsIntervalRef = useRef<number | null>(null);
  const chartDataRef = useRef<ChartDataPoint[]>([]);

  // Load orders and predicates on mount
  useEffect(() => {
    const loadData = async () => {
      try {
        const [ordersRes, predicatesRes] = await Promise.all([
          queryStatsApi.getOrders(),
          queryStatsApi.getOrderPredicates(),
        ]);
        setOrders(ordersRes.data);
        setPredicates(predicatesRes.data);
        if (ordersRes.data.length > 0) {
          setSelectedOrderId(ordersRes.data[0].order_id);
          setTripleSubject(ordersRes.data[0].order_id);
        }
      } catch (err) {
        console.error("Failed to load data:", err);
        setError("Failed to load orders");
      }
    };
    loadData();
  }, []);

  // Fetch metrics periodically when polling
  const fetchMetrics = useCallback(async () => {
    try {
      const [metricsRes, historyRes, orderDataRes] = await Promise.all([
        queryStatsApi.getMetrics(),
        queryStatsApi.getMetricsHistory(),
        queryStatsApi.getOrderData(),
      ]);

      setMetrics(metricsRes.data);
      setOrderData(orderDataRes.data);
      setLastUpdateTime(Date.now());

      // Update chart data with the latest reaction times
      const history = historyRes.data as QueryStatsHistoryResponse;
      const now = Date.now();
      const maxSamples = 1800; // 3 minutes at 100ms intervals

      // Build chart data from history
      const pgTimes = history.postgresql_view?.reaction_times || [];
      const batchTimes = history.batch_cache?.reaction_times || [];
      const mzTimes = history.materialize?.reaction_times || [];

      const maxLen = Math.max(pgTimes.length, batchTimes.length, mzTimes.length);
      const newChartData: ChartDataPoint[] = [];

      for (let i = 0; i < maxLen; i++) {
        newChartData.push({
          time: now - (maxLen - i - 1) * 100, // Approximate timestamps (100ms intervals)
          postgresql: pgTimes[i] ?? null,
          batch: batchTimes[i] ?? null,
          materialize: mzTimes[i] ?? null,
        });
      }

      // Filter to only show last 3 minutes (180 seconds)
      const threeMinutesAgo = now - 180000;
      const filteredData = newChartData.filter((d) => d.time >= threeMinutesAgo);
      chartDataRef.current = filteredData.slice(-maxSamples);
      setChartData(chartDataRef.current);
      setError(null);
    } catch (err) {
      console.error("Failed to fetch metrics:", err);
    }
  }, []);

  // Start polling
  const handleStartPolling = async () => {
    if (!selectedOrderId) return;

    try {
      await queryStatsApi.startPolling(selectedOrderId);
      setIsPolling(true);
      setTripleSubject(selectedOrderId);
      chartDataRef.current = [];
      setChartData([]);
      setOrderData(null);

      // Start fetching metrics every second
      metricsIntervalRef.current = window.setInterval(fetchMetrics, 1000);
      // Fetch immediately
      fetchMetrics();
    } catch (err) {
      console.error("Failed to start polling:", err);
      setError("Failed to start polling");
    }
  };

  // Stop polling
  const handleStopPolling = async () => {
    try {
      await queryStatsApi.stopPolling();
      setIsPolling(false);

      if (metricsIntervalRef.current) {
        clearInterval(metricsIntervalRef.current);
        metricsIntervalRef.current = null;
      }
    } catch (err) {
      console.error("Failed to stop polling:", err);
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (metricsIntervalRef.current) {
        clearInterval(metricsIntervalRef.current);
      }
    };
  }, []);

  // Handle triple write
  const handleWriteTriple = async () => {
    if (!tripleSubject || !triplePredicate || !tripleValue) return;

    try {
      await queryStatsApi.writeTriple({
        subject_id: tripleSubject,
        predicate: triplePredicate,
        object_value: tripleValue,
      });
      setWriteStatus(`Written at ${new Date().toLocaleTimeString()}`);
      setTimeout(() => setWriteStatus(null), 3000);
    } catch (err) {
      console.error("Failed to write triple:", err);
      setWriteStatus("Write failed");
    }
  };

  // Format milliseconds for display
  const formatMs = (ms: number | undefined): string => {
    if (ms === undefined || ms === null) return "-";
    if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
    return `${ms.toFixed(1)}ms`;
  };

  return (
    <div className="p-6">
      {/* Header */}
      <div className="flex justify-between items-center mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">Query Statistics</h1>
            {isPolling ? (
              <span className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-green-700 bg-green-100 rounded-full">
                <Wifi className="h-3 w-3" />
                Polling
              </span>
            ) : (
              <span className="flex items-center gap-1 px-2 py-1 text-xs font-medium text-gray-500 bg-gray-100 rounded-full">
                <WifiOff className="h-3 w-3" />
                Stopped
              </span>
            )}
            {isPolling && (
              <span className="text-xs text-gray-500">
                Last update: {new Date(lastUpdateTime).toLocaleTimeString()}
              </span>
            )}
          </div>
          <p className="text-gray-600">
            Compare order view performance: PostgreSQL VIEW vs Batch MATERIALIZED VIEW vs Materialize
          </p>
        </div>
      </div>

      {error && (
        <div className="mb-4 p-4 bg-red-50 text-red-700 rounded-lg">{error}</div>
      )}

      {/* Order Selector */}
      <div className="bg-white rounded-lg shadow p-4 mb-4">
        <div className="flex items-center gap-4">
          <div className="flex-1">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <ShoppingCart className="h-4 w-4 inline mr-1" />
              Select Order
            </label>
            <select
              value={selectedOrderId}
              onChange={(e) => {
                setSelectedOrderId(e.target.value);
                setTripleSubject(e.target.value);
              }}
              disabled={isPolling}
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-100"
            >
              {orders.map((order) => (
                <option key={order.order_id} value={order.order_id}>
                  {order.order_number || order.order_id} - {order.order_status} - {order.customer_name || "Unknown"} @ {order.store_name || "Unknown"}
                </option>
              ))}
            </select>
          </div>
          <div className="flex gap-2 pt-6">
            {!isPolling ? (
              <button
                onClick={handleStartPolling}
                disabled={!selectedOrderId}
                className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed"
              >
                <Play className="h-4 w-4" />
                Start Polling
              </button>
            ) : (
              <button
                onClick={handleStopPolling}
                className="flex items-center gap-2 px-4 py-2 bg-red-600 text-white rounded-md hover:bg-red-700"
              >
                <Square className="h-4 w-4" />
                Stop
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Write Triple Form (directly under selector) */}
      <div className="bg-white rounded-lg shadow p-4 mb-6">
        <div className="flex items-center gap-2 mb-3">
          <Edit3 className="h-4 w-4 text-purple-600" />
          <span className="font-medium text-gray-900">Write a Triple</span>
          <span className="text-xs text-gray-500">
            - Update an order property and observe propagation
          </span>
        </div>

        <div className="flex items-end gap-3">
          <div className="flex-1">
            <label className="block text-xs font-medium text-gray-600 mb-1">Subject</label>
            <input
              type="text"
              value={tripleSubject}
              onChange={(e) => setTripleSubject(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm text-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500"
              placeholder="order:FM-1001"
            />
          </div>
          <div className="flex-1">
            <label className="block text-xs font-medium text-gray-600 mb-1">Predicate</label>
            <select
              value={triplePredicate}
              onChange={(e) => setTriplePredicate(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm text-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500"
            >
              {predicates.map((p) => (
                <option key={p.predicate} value={p.predicate}>
                  {p.predicate}
                </option>
              ))}
            </select>
          </div>
          <div className="flex-1">
            <label className="block text-xs font-medium text-gray-600 mb-1">Value</label>
            <input
              type="text"
              value={tripleValue}
              onChange={(e) => setTripleValue(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm text-sm focus:outline-none focus:ring-purple-500 focus:border-purple-500"
              placeholder="DELIVERED"
            />
          </div>
          <button
            onClick={handleWriteTriple}
            disabled={!tripleSubject || !triplePredicate || !tripleValue}
            className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm"
          >
            Write
          </button>
          {writeStatus && (
            <span className="text-sm text-green-600 flex items-center gap-1">
              <span className="inline-block w-2 h-2 rounded-full bg-green-500"></span>
              {writeStatus}
            </span>
          )}
        </div>
      </div>

      {/* Three Order Cards */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <OrderCard
          title="PostgreSQL VIEW"
          subtitle="Fresh but SLOW (computes every query)"
          icon={<Database className="h-5 w-5" />}
          iconColor="text-orange-500"
          bgColor="border-orange-500"
          order={orderData?.postgresql_view || null}
          isLoading={isPolling}
        />
        <OrderCard
          title="Batch MATERIALIZED VIEW"
          subtitle="Fast but STALE (refreshes every 60s)"
          icon={<Clock className="h-5 w-5" />}
          iconColor="text-green-500"
          bgColor="border-green-500"
          order={orderData?.batch_cache || null}
          isLoading={isPolling}
        />
        <OrderCard
          title="Materialize"
          subtitle="Fast AND Fresh (incremental via CDC)"
          icon={<Zap className="h-5 w-5" />}
          iconColor="text-blue-500"
          bgColor="border-blue-500"
          order={orderData?.materialize || null}
          isLoading={isPolling}
        />
      </div>

      {/* Statistics Table */}
      <div className="bg-white rounded-lg shadow mb-6">
        <div className="p-4 border-b">
          <h3 className="font-semibold text-gray-900 flex items-center gap-2">
            <BarChart3 className="h-5 w-5" />
            Query Statistics - Orders with Lines View
          </h3>
          <p className="text-xs text-gray-500 mt-1">
            Response Time = query latency | Reaction Time = freshness (NOW - effective_updated_at) | QPS = queries/second throughput
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase">
                  Source
                </th>
                <th
                  colSpan={3}
                  className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase border-l"
                >
                  <div className="flex items-center justify-center gap-1">
                    <Clock className="h-3 w-3" />
                    Response Time (ms)
                  </div>
                </th>
                <th
                  colSpan={3}
                  className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase border-l"
                >
                  <div className="flex items-center justify-center gap-1">
                    <Activity className="h-3 w-3" />
                    Reaction Time (ms)
                  </div>
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase border-l">
                  <div className="flex items-center justify-center gap-1">
                    <Zap className="h-3 w-3" />
                    QPS
                  </div>
                </th>
                <th className="px-4 py-3 text-center text-xs font-medium text-gray-500 uppercase border-l">
                  Samples
                </th>
              </tr>
              <tr className="bg-gray-50">
                <th></th>
                <th className="px-2 py-1 text-center text-xs text-gray-400 border-l">
                  Median
                </th>
                <th className="px-2 py-1 text-center text-xs text-gray-400">P99</th>
                <th className="px-2 py-1 text-center text-xs text-gray-400">Max</th>
                <th className="px-2 py-1 text-center text-xs text-gray-400 border-l">
                  Median
                </th>
                <th className="px-2 py-1 text-center text-xs text-gray-400">P99</th>
                <th className="px-2 py-1 text-center text-xs text-gray-400">Max</th>
                <th className="border-l"></th>
                <th className="border-l"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-200">
              {/* PostgreSQL View Row */}
              <tr className="hover:bg-gray-50">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Database className="h-4 w-4 text-orange-500" />
                    <div>
                      <div className="font-medium text-gray-900">PostgreSQL View</div>
                      <div className="text-xs text-gray-500">Fresh but SLOW (computes on every query)</div>
                    </div>
                  </div>
                </td>
                <td className="px-2 py-3 text-center border-l font-mono text-orange-600 font-semibold">
                  {formatMs(metrics?.postgresql_view?.response_time?.median)}
                </td>
                <td className="px-2 py-3 text-center font-mono text-orange-600">
                  {formatMs(metrics?.postgresql_view?.response_time?.p99)}
                </td>
                <td className="px-2 py-3 text-center font-mono text-orange-600">
                  {formatMs(metrics?.postgresql_view?.response_time?.max)}
                </td>
                <td className="px-2 py-3 text-center border-l font-mono">
                  {formatMs(metrics?.postgresql_view?.reaction_time?.median)}
                </td>
                <td className="px-2 py-3 text-center font-mono">
                  {formatMs(metrics?.postgresql_view?.reaction_time?.p99)}
                </td>
                <td className="px-2 py-3 text-center font-mono">
                  {formatMs(metrics?.postgresql_view?.reaction_time?.max)}
                </td>
                <td className="px-2 py-3 text-center border-l font-mono text-orange-600 font-semibold">
                  {metrics?.postgresql_view?.qps?.toFixed(1) || 0}
                </td>
                <td className="px-2 py-3 text-center border-l text-gray-500">
                  {metrics?.postgresql_view?.sample_count || 0}
                </td>
              </tr>

              {/* Batch Cache Row */}
              <tr className="hover:bg-gray-50">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Clock className="h-4 w-4 text-green-500" />
                    <div>
                      <div className="font-medium text-gray-900">Batch MATERIALIZED VIEW</div>
                      <div className="text-xs text-gray-500">Fast but STALE (refreshes every 60s)</div>
                    </div>
                  </div>
                </td>
                <td className="px-2 py-3 text-center border-l font-mono">
                  {formatMs(metrics?.batch_cache?.response_time?.median)}
                </td>
                <td className="px-2 py-3 text-center font-mono">
                  {formatMs(metrics?.batch_cache?.response_time?.p99)}
                </td>
                <td className="px-2 py-3 text-center font-mono">
                  {formatMs(metrics?.batch_cache?.response_time?.max)}
                </td>
                <td className="px-2 py-3 text-center border-l font-mono text-green-600 font-semibold">
                  {formatMs(metrics?.batch_cache?.reaction_time?.median)}
                </td>
                <td className="px-2 py-3 text-center font-mono text-green-600">
                  {formatMs(metrics?.batch_cache?.reaction_time?.p99)}
                </td>
                <td className="px-2 py-3 text-center font-mono text-green-600">
                  {formatMs(metrics?.batch_cache?.reaction_time?.max)}
                </td>
                <td className="px-2 py-3 text-center border-l font-mono text-green-600 font-semibold">
                  {metrics?.batch_cache?.qps?.toFixed(1) || 0}
                </td>
                <td className="px-2 py-3 text-center border-l text-gray-500">
                  {metrics?.batch_cache?.sample_count || 0}
                </td>
              </tr>

              {/* Materialize Row */}
              <tr className="hover:bg-gray-50 bg-blue-50">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <Zap className="h-4 w-4 text-blue-500" />
                    <div>
                      <div className="font-medium text-gray-900 flex items-center gap-1">
                        Materialize
                        <span className="text-xs text-blue-600 font-normal bg-blue-100 px-1 rounded">Best</span>
                      </div>
                      <div className="text-xs text-gray-500">Fast AND Fresh (incremental via CDC)</div>
                    </div>
                  </div>
                </td>
                <td className="px-2 py-3 text-center border-l font-mono">
                  {formatMs(metrics?.materialize?.response_time?.median)}
                </td>
                <td className="px-2 py-3 text-center font-mono">
                  {formatMs(metrics?.materialize?.response_time?.p99)}
                </td>
                <td className="px-2 py-3 text-center font-mono">
                  {formatMs(metrics?.materialize?.response_time?.max)}
                </td>
                <td className="px-2 py-3 text-center border-l font-mono text-blue-600 font-semibold">
                  {formatMs(metrics?.materialize?.reaction_time?.median)}
                </td>
                <td className="px-2 py-3 text-center font-mono text-blue-600 font-semibold">
                  {formatMs(metrics?.materialize?.reaction_time?.p99)}
                </td>
                <td className="px-2 py-3 text-center font-mono text-blue-600 font-semibold">
                  {formatMs(metrics?.materialize?.reaction_time?.max)}
                </td>
                <td className="px-2 py-3 text-center border-l font-mono text-blue-600 font-semibold">
                  {metrics?.materialize?.qps?.toFixed(1) || 0}
                </td>
                <td className="px-2 py-3 text-center border-l text-gray-500">
                  {metrics?.materialize?.sample_count || 0}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* Reaction Time Chart */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">Reaction Time Over Time</h3>
            <p className="text-xs text-gray-500">
              End-to-end latency: how fresh is the data when the query completes?
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setUseLogScale(false)}
              className={`px-3 py-1 text-sm rounded ${
                !useLogScale ? "bg-blue-600 text-white" : "bg-gray-200 text-gray-700"
              }`}
            >
              Linear
            </button>
            <button
              onClick={() => setUseLogScale(true)}
              className={`px-3 py-1 text-sm rounded ${
                useLogScale ? "bg-blue-600 text-white" : "bg-gray-200 text-gray-700"
              }`}
            >
              Logarithmic
            </button>
          </div>
        </div>

        <ResponsiveContainer width="100%" height={300}>
          <LineChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis
              dataKey="time"
              tickFormatter={(t) => {
                const date = new Date(t);
                return `${date.getMinutes().toString().padStart(2, '0')}:${date.getSeconds().toString().padStart(2, '0')}`;
              }}
              domain={[lastUpdateTime - 180000, lastUpdateTime]}
              type="number"
              fontSize={12}
              tick={{ fill: "#6b7280" }}
              interval="preserveStartEnd"
            />
            <YAxis
              scale={useLogScale ? "log" : "linear"}
              domain={useLogScale ? [1, "auto"] : [0, "auto"]}
              tickFormatter={(v) =>
                v >= 1000 ? `${(v / 1000).toFixed(0)}s` : `${v.toFixed(0)}ms`
              }
              fontSize={12}
              tick={{ fill: "#6b7280" }}
              allowDataOverflow={useLogScale}
            />
            <Tooltip
              formatter={(value: number | undefined) => [value !== undefined ? `${value.toFixed(1)}ms` : "-", ""]}
              labelFormatter={(t) => {
                const date = new Date(t as number);
                return date.toLocaleTimeString();
              }}
              contentStyle={{ backgroundColor: "#fff", border: "1px solid #e5e7eb" }}
            />
            <Legend />
            <Line
              type="monotone"
              dataKey="postgresql"
              name="PostgreSQL View"
              stroke="#f97316"
              strokeWidth={2}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="batch"
              name="Batch Cache"
              stroke="#22c55e"
              strokeWidth={2}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
            <Line
              type="monotone"
              dataKey="materialize"
              name="Materialize"
              stroke="#3b82f6"
              strokeWidth={2}
              dot={false}
              connectNulls
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
