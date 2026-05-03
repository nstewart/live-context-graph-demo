import { useState, useEffect, useRef, useCallback, useMemo } from "react";
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
  BarChart3,
  Database,
  Zap,
  Clock,
  ShoppingCart,
  User,
  Store,
  Package,
  ChevronDown,
  ChevronRight,
  Code,
  X,
} from "lucide-react";
import { useZero, useQuery } from "@rocicorp/zero/react";
import { Schema } from "../schema";
import {
  queryStatsApi,
  QueryStatsResponse,
  QueryStatsHistoryResponse,
  QueryStatsOrder,
  OrderDataResponse,
  OrderWithLinesData,
  OrderLineItem,
  ViewDefinitionResponse,
} from "../api/client";
import { LineageGraph } from "../components/LineageGraph";
import { WhatAreTriplesCard } from "../components/WhatAreTriplesCard";
import { WhatIsKnowledgeGraphCard } from "../components/WhatIsKnowledgeGraphCard";
import { VectorPipelineCard } from "../components/VectorPipelineCard";
import { WriteTripleForm } from "../components/WriteTripleForm";
import { usePropagation } from "../contexts/PropagationContext";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

interface ChartDataPoint {
  time: number;
  postgresql: number | null;
  batch: number | null;
  materialize: number | null;
}

type ViewMode = 'query-offload' | 'batch' | 'materialize';

// Predicates available for each subject type
const predicatesBySubjectType: Record<string, string[]> = {
  order: ['order_status', 'order_number', 'delivery_window_start', 'delivery_window_end'],
  orderline: ['quantity', 'order_line_unit_price', 'line_sequence'],  // perishable_flag is derived from product
  customer: ['customer_name', 'customer_email', 'customer_address'],
  store: ['store_name', 'store_zone', 'store_address'],
  product: ['product_name', 'category', 'unit_price', 'perishable', 'unit_weight_grams'],
  inventory: ['stock_level', 'replenishment_eta'],
  courier: ['courier_name', 'courier_phone', 'courier_status'],
  task: ['task_status', 'assigned_to', 'eta'],
};


// Highlighted JSON component that glows when values change
const HighlightedJson = ({ data, trackingKey }: { data: object; trackingKey?: string }) => {
  const prevDataRef = useRef<string>('');
  const prevTrackingKeyRef = useRef<string | undefined>(undefined);
  const changedPathsRef = useRef<Map<string, number>>(new Map());
  const [, forceUpdate] = useState(0);

  const HIGHLIGHT_DURATION = 1500; // ms

  // Find changed paths by comparing JSON
  useEffect(() => {
    // Reset when tracking key changes (e.g., different order selected)
    if (trackingKey !== prevTrackingKeyRef.current) {
      prevTrackingKeyRef.current = trackingKey;
      prevDataRef.current = JSON.stringify(data);
      changedPathsRef.current = new Map();
      return;
    }

    const currentJson = JSON.stringify(data);
    if (prevDataRef.current && prevDataRef.current !== currentJson) {
      // Find which paths changed
      const prevData = JSON.parse(prevDataRef.current);
      const now = Date.now();

      const findChanges = (current: unknown, previous: unknown, path: string) => {
        if (typeof current !== typeof previous) {
          changedPathsRef.current.set(path, now);
          return;
        }
        if (current === null || previous === null) {
          if (current !== previous) changedPathsRef.current.set(path, now);
          return;
        }
        if (typeof current !== 'object') {
          if (current !== previous) changedPathsRef.current.set(path, now);
          return;
        }
        if (Array.isArray(current) && Array.isArray(previous)) {
          if (current.length !== previous.length) {
            changedPathsRef.current.set(path, now);
          }
          current.forEach((item, i) => {
            findChanges(item, previous[i], `${path}[${i}]`);
          });
          return;
        }
        const currentObj = current as Record<string, unknown>;
        const previousObj = previous as Record<string, unknown>;
        const allKeys = new Set([...Object.keys(currentObj), ...Object.keys(previousObj)]);
        allKeys.forEach(key => {
          findChanges(currentObj[key], previousObj[key], path ? `${path}.${key}` : key);
        });
      };

      findChanges(data, prevData, '');
      forceUpdate(n => n + 1);

      // Schedule cleanup of expired highlights
      const timer = setTimeout(() => {
        const now = Date.now();
        for (const [path, timestamp] of changedPathsRef.current) {
          if (now - timestamp >= HIGHLIGHT_DURATION) {
            changedPathsRef.current.delete(path);
          }
        }
        forceUpdate(n => n + 1);
      }, HIGHLIGHT_DURATION);

      prevDataRef.current = currentJson;
      return () => clearTimeout(timer);
    }
    prevDataRef.current = currentJson;
  }, [data, trackingKey]);

  // Check if a path is currently highlighted
  const isHighlighted = (path: string): boolean => {
    const timestamp = changedPathsRef.current.get(path);
    if (!timestamp) return false;
    return Date.now() - timestamp < HIGHLIGHT_DURATION;
  };

  // Render JSON with highlights
  const renderValue = (value: unknown, path: string, indent: number): React.ReactNode => {
    const isChanged = isHighlighted(path);
    const glowClass = isChanged ? 'animate-pulse bg-yellow-500/30 rounded px-1 -mx-1' : '';
    const spaces = '  '.repeat(indent);

    if (value === null) {
      return <span className={`text-gray-500 ${glowClass}`}>null</span>;
    }
    if (typeof value === 'boolean') {
      return <span className={`text-purple-400 ${glowClass}`}>{value ? 'true' : 'false'}</span>;
    }
    if (typeof value === 'number') {
      return <span className={`text-blue-400 ${glowClass}`}>{value}</span>;
    }
    if (typeof value === 'string') {
      return <span className={`text-green-400 ${glowClass}`}>"{value}"</span>;
    }
    if (Array.isArray(value)) {
      if (value.length === 0) return <span className={glowClass}>[]</span>;
      return (
        <>
          {'[\n'}
          {value.map((item, i) => (
            <span key={i}>
              {spaces}  {renderValue(item, `${path}[${i}]`, indent + 1)}
              {i < value.length - 1 ? ',' : ''}{'\n'}
            </span>
          ))}
          {spaces}{']'}
        </>
      );
    }
    if (typeof value === 'object') {
      const entries = Object.entries(value as Record<string, unknown>);
      if (entries.length === 0) return <span className={glowClass}>{'{}'}</span>;
      return (
        <>
          {'{\n'}
          {entries.map(([key, val], i) => {
            const keyPath = path ? `${path}.${key}` : key;
            const isKeyChanged = isHighlighted(keyPath);
            const keyGlowClass = isKeyChanged ? 'animate-pulse bg-yellow-500/30 rounded px-1 -mx-1' : '';
            return (
              <span key={key}>
                {spaces}  <span className={`text-gray-400 ${keyGlowClass}`}>"{key}"</span>: {renderValue(val, keyPath, indent + 1)}
                {i < entries.length - 1 ? ',' : ''}{'\n'}
              </span>
            );
          })}
          {spaces}{'}'}
        </>
      );
    }
    return String(value);
  };

  return (
    <pre className="text-xs font-mono text-gray-300 whitespace-pre">
      {renderValue(data, '', 0)}
    </pre>
  );
};

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
  const prevOrderRef = useRef<OrderWithLinesData | null>(null);
  const [changedFields, setChangedFields] = useState<Set<string>>(new Set());
  const timeoutRef = useRef<NodeJS.Timeout | null>(null);

  // Detect changes and highlight them
  useEffect(() => {
    if (!order) {
      prevOrderRef.current = null;
      return;
    }

    if (!prevOrderRef.current) {
      prevOrderRef.current = order;
      return;
    }

    const prev = prevOrderRef.current;
    const changes = new Set<string>();

    // Check top-level fields
    if (prev.order_status !== order.order_status) changes.add('status');
    if (prev.order_total_amount !== order.order_total_amount) changes.add('total');
    if (prev.customer_name !== order.customer_name) changes.add('customer');
    if (prev.store_name !== order.store_name) changes.add('store');

    // Check line items
    const prevLines = new Map(prev.line_items?.map(l => [l.line_id, l]) || []);
    order.line_items?.forEach(line => {
      const prevLine = prevLines.get(line.line_id);
      if (!prevLine) {
        changes.add(`line-${line.line_id}`);
      } else {
        if (prevLine.quantity !== line.quantity) changes.add(`line-${line.line_id}-qty`);
        if (prevLine.unit_price !== line.unit_price) changes.add(`line-${line.line_id}-price`);
        if (prevLine.line_amount !== line.line_amount) changes.add(`line-${line.line_id}-subtotal`);
        if (prevLine.live_price !== line.live_price) changes.add(`line-${line.line_id}-live`);
      }
    });

    // Update ref for next comparison
    prevOrderRef.current = order;

    if (changes.size > 0) {
      // Clear any existing timeout
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
      setChangedFields(changes);
      // Clear highlights after 2 seconds
      timeoutRef.current = setTimeout(() => {
        setChangedFields(new Set());
      }, 2000);
    }
  }, [order]);

  // Cleanup timeout on unmount
  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        clearTimeout(timeoutRef.current);
      }
    };
  }, []);

  const highlightClass = (field: string) =>
    changedFields.has(field)
      ? 'bg-yellow-200 rounded px-1 -mx-1 transition-all duration-1000'
      : 'transition-all duration-1000';

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
              <div className="flex justify-between items-start">
                <span className="text-gray-600 flex items-center gap-1">
                  <ShoppingCart className="h-3 w-3" />
                  Order
                </span>
                <div className="text-right">
                  <div className="font-mono font-medium">{order.order_number || order.order_id}</div>
                  <div className="text-[10px] text-gray-400 font-mono">{order.order_id}</div>
                </div>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-600">Status</span>
                <span className={highlightClass('status')}>
                  <StatusBadge status={order.order_status} />
                </span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-600 flex items-center gap-1">
                  <User className="h-3 w-3" />
                  Customer
                </span>
                <span className={`text-right truncate max-w-[150px] ${highlightClass('customer')}`}>{order.customer_name || "-"}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-600 flex items-center gap-1">
                  <Store className="h-3 w-3" />
                  Store
                </span>
                <span className={`text-right truncate max-w-[150px] ${highlightClass('store')}`}>{order.store_name || "-"}</span>
              </div>
              <div className="flex justify-between items-center">
                <span className="text-gray-600">Total</span>
                <span className={`font-semibold ${highlightClass('total')}`}>
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
                  <div className="mt-2 space-y-1 max-h-[250px] overflow-y-auto">
                    {/* Header row */}
                    <div className="text-[10px] text-gray-500 px-2 py-1 border-b grid grid-cols-[1fr_40px_40px_40px_55px] gap-1">
                      <span>Product</span>
                      <span className="text-right" title="Price when order was placed">Order</span>
                      <span className="text-right" title="Product catalog price">Base</span>
                      <span className="text-right" title="Current dynamic price">Live</span>
                      <span className="text-right" title="Quantity × Order Price">Subtotal</span>
                    </div>
                    {order.line_items.map((item: OrderLineItem) => {
                      const lineHighlight = (field: string) => highlightClass(`line-${item.line_id}-${field}`);
                      const isNewLine = changedFields.has(`line-${item.line_id}`);
                      return (
                        <div
                          key={item.line_id}
                          className={`text-xs py-1.5 px-2 rounded transition-all duration-1000 ${isNewLine ? 'bg-yellow-200' : 'bg-gray-50'}`}
                        >
                          <div className="grid grid-cols-[1fr_40px_40px_40px_55px] gap-1 items-center">
                            <div className="min-w-0">
                              <span className="truncate block font-medium">
                                {item.product_name || item.product_id}
                              </span>
                              <span className={`text-gray-500 ${lineHighlight('qty')}`}>
                                Qty: {item.quantity}
                              </span>
                            </div>
                            <span className={`text-right font-mono ${lineHighlight('price')}`}>
                              ${item.unit_price?.toFixed(2) ?? '-'}
                            </span>
                            <span className="text-right font-mono text-gray-400">
                              ${item.base_price?.toFixed(2) ?? '-'}
                            </span>
                            <span className={`text-right font-mono text-blue-600 ${lineHighlight('live')}`}>
                              ${item.live_price?.toFixed(2) ?? '-'}
                            </span>
                            <span className={`text-right font-mono font-medium ${lineHighlight('subtotal')}`}>
                              ${item.line_amount?.toFixed(2) ?? '-'}
                            </span>
                          </div>
                          <div className="text-[10px] text-gray-400 font-mono mt-0.5">
                            {item.line_id}
                          </div>
                        </div>
                      );
                    })}
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
  const { clearWrites } = usePropagation();
  const [orders, setOrders] = useState<QueryStatsOrder[]>([]);
  const [selectedOrderId, setSelectedOrderId] = useState<string>("");
  const [isPolling, setIsPolling] = useState(false);
  const [metrics, setMetrics] = useState<QueryStatsResponse | null>(null);
  const [orderData, setOrderData] = useState<OrderDataResponse | null>(null);
  const [chartData, setChartData] = useState<ChartDataPoint[]>([]);
  const [responseTimeChartData, setResponseTimeChartData] = useState<ChartDataPoint[]>([]);
  const [useLogScale, setUseLogScale] = useState(false);
  const [useLogScaleResponseTime, setUseLogScaleResponseTime] = useState(false);
  const [lineageGraphOpen, setLineageGraphOpen] = useState(true);
  const [contextReactiveOpen, setContextReactiveOpen] = useState(false);
  const [freshmartUIOpen, setFreshmartUIOpen] = useState(false);
  const [trustedActionOpen, setTrustedActionOpen] = useState(true);
  const [responseChartOpen, setResponseChartOpen] = useState(true);
  const [reactionChartOpen, setReactionChartOpen] = useState(false);
  const [queryStatsOpen, setQueryStatsOpen] = useState(false);
  const [lastUpdateTime, setLastUpdateTime] = useState<number>(Date.now());
  const [error, setError] = useState<string | null>(null);

  // View definition state for SQL viewer
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [viewDefinition, setViewDefinition] = useState<ViewDefinitionResponse | null>(null);
  const [viewDefLoading, setViewDefLoading] = useState(false);

  // Zero for real-time Materialize data
  const z = useZero<Schema>();

  // Sentinel value for empty queries (must be a value that will never match real data)
  const EMPTY_QUERY_SENTINEL = "$$EMPTY_QUERY$$";

  // Query the selected order from Zero (real-time sync from Materialize)
  const orderQuery = useMemo(() => {
    const baseQuery = z.query.orders_with_lines_mv.related("searchData");
    if (!selectedOrderId) return baseQuery.where("order_id", "=", EMPTY_QUERY_SENTINEL);
    return baseQuery.where("order_id", "=", selectedOrderId);
  }, [z, selectedOrderId]);

  const [zeroOrderData] = useQuery(orderQuery);
  const zeroOrder = zeroOrderData?.[0];

  // Query inventory pricing for the store (real-time from Materialize)
  const storeId = zeroOrder?.searchData?.store_id || zeroOrder?.store_id;
  const pricingQuery = useMemo(() => {
    if (!storeId) return z.query.inventory_items_with_dynamic_pricing_mv.where("store_id", "=", EMPTY_QUERY_SENTINEL);
    return z.query.inventory_items_with_dynamic_pricing_mv.where("store_id", "=", storeId);
  }, [z, storeId]);

  const [zeroPricingData] = useQuery(pricingQuery);

  // Transform Zero data to match OrderWithLinesData format for the Materialize card
  const zeroMaterializeOrder: OrderWithLinesData | null = useMemo(() => {
    if (!zeroOrder) return null;

    // Build pricing lookup by product_id
    const pricingByProduct = new Map<string, { live_price: number | null; base_price: number | null; price_change: number | null; stock_level: number | null }>();

    for (const p of zeroPricingData || []) {
      if (p.product_id) {
        pricingByProduct.set(p.product_id, {
          live_price: p.live_price ?? null,
          base_price: p.base_price ?? null,
          price_change: p.price_change ?? null,
          stock_level: p.stock_level ?? null,
        });
      }
    }

    // Enrich line items with live pricing
    const lineItems = (zeroOrder.line_items || []).map((item) => ({
      ...item,
      live_price: pricingByProduct.get(item.product_id)?.live_price ?? null,
      base_price: pricingByProduct.get(item.product_id)?.base_price ?? null,
      price_change: pricingByProduct.get(item.product_id)?.price_change ?? null,
      current_stock: pricingByProduct.get(item.product_id)?.stock_level ?? null,
    }));

    const searchData = zeroOrder.searchData;

    return {
      order_id: zeroOrder.order_id,
      order_number: zeroOrder.order_number ?? null,
      order_status: zeroOrder.order_status ?? null,
      store_id: zeroOrder.store_id ?? null,
      customer_id: zeroOrder.customer_id ?? null,
      delivery_window_start: zeroOrder.delivery_window_start ?? null,
      delivery_window_end: zeroOrder.delivery_window_end ?? null,
      order_total_amount: zeroOrder.order_total_amount ?? null,
      customer_name: searchData?.customer_name ?? null,
      customer_email: searchData?.customer_email ?? null,
      customer_address: searchData?.customer_address ?? null,
      store_name: searchData?.store_name ?? null,
      store_zone: searchData?.store_zone ?? null,
      store_address: searchData?.store_address ?? null,
      delivery_task_id: null,
      assigned_courier_id: searchData?.assigned_courier_id ?? null,
      delivery_task_status: searchData?.delivery_task_status ?? null,
      delivery_eta: searchData?.delivery_eta ?? null,
      line_items: lineItems,
      line_item_count: zeroOrder.line_item_count ?? lineItems.length,
      computed_total: zeroOrder.computed_total ?? null,
      has_perishable_items: zeroOrder.has_perishable_items ?? false,
      effective_updated_at: zeroOrder.effective_updated_at
        ? new Date(zeroOrder.effective_updated_at).toISOString()
        : new Date().toISOString(),
    };
  }, [zeroOrder, zeroPricingData]);

  // Triple writer state
  const [tripleSubject, setTripleSubject] = useState("");
  const [triplePredicate, setTriplePredicate] = useState("quantity");
  const userSetSubjectRef = useRef(false);
  const [triplesRefreshTrigger, setTriplesRefreshTrigger] = useState(0);

  // View mode state
  const [viewMode, setViewMode] = useState<ViewMode>('query-offload');

  // Derive subject type from tripleSubject prefix and get available predicates
  const availablePredicates = useMemo(() => {
    let basePredicates: string[];

    if (!tripleSubject) {
      basePredicates = predicatesBySubjectType.orderline;
    } else {
      // Extract prefix before the colon (e.g., "orderline:123" -> "orderline")
      const colonIndex = tripleSubject.indexOf(':');
      if (colonIndex === -1) {
        // No colon found, try to detect type from ID format
        if (tripleSubject.startsWith('order_')) basePredicates = predicatesBySubjectType.order;
        else if (tripleSubject.startsWith('orderline_')) basePredicates = predicatesBySubjectType.orderline;
        else if (tripleSubject.startsWith('customer_')) basePredicates = predicatesBySubjectType.customer;
        else if (tripleSubject.startsWith('store_')) basePredicates = predicatesBySubjectType.store;
        else if (tripleSubject.startsWith('product_')) basePredicates = predicatesBySubjectType.product;
        else if (tripleSubject.startsWith('inventory_')) basePredicates = predicatesBySubjectType.inventory;
        else if (tripleSubject.startsWith('courier_')) basePredicates = predicatesBySubjectType.courier;
        else if (tripleSubject.startsWith('task_')) basePredicates = predicatesBySubjectType.task;
        else {
          // Unknown subject type - warn and default to orderline
          console.warn(`Unknown subject type for ID: "${tripleSubject}", defaulting to orderline predicates`);
          basePredicates = predicatesBySubjectType.orderline;
        }
      } else {
        const prefix = tripleSubject.slice(0, colonIndex).toLowerCase();
        if (!predicatesBySubjectType[prefix]) {
          console.warn(`Unknown subject type prefix: "${prefix}", defaulting to orderline predicates`);
        }
        basePredicates = predicatesBySubjectType[prefix] || predicatesBySubjectType.orderline;
      }
    }

    // Include current predicate if it's not in the base list (allows clicking any triple)
    if (triplePredicate && !basePredicates.includes(triplePredicate)) {
      return [triplePredicate, ...basePredicates];
    }
    return basePredicates;
  }, [tripleSubject, triplePredicate]);

  // Update predicate when available predicates change (if current predicate is not in new list)
  useEffect(() => {
    if (availablePredicates.length > 0 && !availablePredicates.includes(triplePredicate)) {
      setTriplePredicate(availablePredicates[0]);
    }
  }, [availablePredicates, triplePredicate]);

  // Default tripleSubject to first orderline when Zero data becomes available
  useEffect(() => {
    if (zeroOrder?.line_items && zeroOrder.line_items.length > 0 && selectedOrderId && !userSetSubjectRef.current) {
      // Only update if tripleSubject is still set to the order ID (not already an orderline)
      if (tripleSubject === selectedOrderId || !tripleSubject.startsWith('orderline_')) {
        setTripleSubject(zeroOrder.line_items[0].line_id);
      }
    }
  }, [zeroOrder, selectedOrderId, tripleSubject]);

  const metricsIntervalRef = useRef<number | null>(null);
  const chartDataRef = useRef<ChartDataPoint[]>([]);
  const responseTimeChartDataRef = useRef<ChartDataPoint[]>([]);

  // Load orders on mount
  useEffect(() => {
    const loadData = async () => {
      try {
        const ordersRes = await queryStatsApi.getOrders();
        setOrders(ordersRes.data);
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

      // Update chart data with the latest reaction times using actual timestamps
      const history = historyRes.data as QueryStatsHistoryResponse;
      const now = Date.now();
      const ninetySecondsAgo = now - 90000; // 90 seconds in ms

      // Build chart data from history using actual timestamps
      // Each source may have different sample rates, so we combine them all
      const pgData = history.postgresql_view || { reaction_times: [], response_times: [], timestamps: [] };
      const batchData = history.batch_cache || { reaction_times: [], response_times: [], timestamps: [] };
      const mzData = history.materialize || { reaction_times: [], response_times: [], timestamps: [] };

      // Type for collecting all values per bucket before computing p99
      type BucketData = {
        time: number;
        postgresql: number[];
        batch: number[];
        materialize: number[];
      };

      // Create maps of time -> collected values, using 1-second buckets
      const reactionBuckets = new Map<number, BucketData>();
      const responseBuckets = new Map<number, BucketData>();

      // Helper to add data point to the appropriate second bucket
      const addToBucket = (
        dataMap: Map<number, BucketData>,
        timestamp: number,
        value: number,
        source: 'postgresql' | 'batch' | 'materialize'
      ) => {
        if (timestamp < ninetySecondsAgo) return; // Skip old data
        const bucket = Math.floor(timestamp / 1000) * 1000; // Round to nearest second
        if (!dataMap.has(bucket)) {
          dataMap.set(bucket, { time: bucket, postgresql: [], batch: [], materialize: [] });
        }
        dataMap.get(bucket)![source].push(value);
      };

      // Helper to calculate p99 from an array of values
      const calcP99 = (values: number[]): number | null => {
        if (values.length === 0) return null;
        const sorted = [...values].sort((a, b) => a - b);
        const p99Idx = Math.min(Math.floor(sorted.length * 0.99), sorted.length - 1);
        return sorted[p99Idx];
      };

      // Convert bucket data to chart data points with p99 values
      const bucketsToChartData = (buckets: Map<number, BucketData>): ChartDataPoint[] => {
        return Array.from(buckets.values())
          .map(bucket => ({
            time: bucket.time,
            postgresql: calcP99(bucket.postgresql),
            batch: calcP99(bucket.batch),
            materialize: calcP99(bucket.materialize),
          }))
          .sort((a, b) => a.time - b.time);
      };

      // Add all reaction time data points from each source
      for (let i = 0; i < pgData.reaction_times.length; i++) {
        const ts = pgData.timestamps[i];
        if (ts) addToBucket(reactionBuckets, ts, pgData.reaction_times[i], 'postgresql');
      }
      for (let i = 0; i < batchData.reaction_times.length; i++) {
        const ts = batchData.timestamps[i];
        if (ts) addToBucket(reactionBuckets, ts, batchData.reaction_times[i], 'batch');
      }
      for (let i = 0; i < mzData.reaction_times.length; i++) {
        const ts = mzData.timestamps[i];
        if (ts) addToBucket(reactionBuckets, ts, mzData.reaction_times[i], 'materialize');
      }

      // Add all response time data points from each source
      for (let i = 0; i < pgData.response_times.length; i++) {
        const ts = pgData.timestamps[i];
        if (ts) addToBucket(responseBuckets, ts, pgData.response_times[i], 'postgresql');
      }
      for (let i = 0; i < batchData.response_times.length; i++) {
        const ts = batchData.timestamps[i];
        if (ts) addToBucket(responseBuckets, ts, batchData.response_times[i], 'batch');
      }
      for (let i = 0; i < mzData.response_times.length; i++) {
        const ts = mzData.timestamps[i];
        if (ts) addToBucket(responseBuckets, ts, mzData.response_times[i], 'materialize');
      }

      // Convert buckets to chart data with p99 per second
      const newChartData = bucketsToChartData(reactionBuckets);
      chartDataRef.current = newChartData;
      setChartData(chartDataRef.current);

      const newResponseTimeChartData = bucketsToChartData(responseBuckets);
      responseTimeChartDataRef.current = newResponseTimeChartData;
      setResponseTimeChartData(responseTimeChartDataRef.current);

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
      responseTimeChartDataRef.current = [];
      setResponseTimeChartData([]);
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
      clearWrites(); // Clear the write propagation state

      if (metricsIntervalRef.current) {
        clearInterval(metricsIntervalRef.current);
        metricsIntervalRef.current = null;
      }
    } catch (err) {
      console.error("Failed to stop polling:", err);
    }
  };

  // Cleanup on unmount - stop both local interval and backend polling
  useEffect(() => {
    return () => {
      if (metricsIntervalRef.current) {
        clearInterval(metricsIntervalRef.current);
        metricsIntervalRef.current = null;
      }
      // Stop backend polling when navigating away
      queryStatsApi.stopPolling().catch(() => {
        // Ignore errors on unmount
      });
      // Clear propagation state
      clearWrites();
    };
  }, [clearWrites]);

  // Handle triple row click - pre-populate the form
  const handleTripleClick = useCallback((subject: string, predicate: string, _value: string) => {
    userSetSubjectRef.current = true;
    setTripleSubject(subject);
    setTriplePredicate(predicate);
  }, []);

  // Handle triple write
  // Handle lineage graph node click
  const handleNodeClick = useCallback(async (nodeId: string) => {
    // Toggle selection if clicking the same node
    if (nodeId === selectedNodeId) {
      setSelectedNodeId(null);
      setViewDefinition(null);
      return;
    }

    setSelectedNodeId(nodeId);
    setViewDefLoading(true);
    setViewDefinition(null);

    try {
      const response = await queryStatsApi.getViewDefinition(nodeId);
      setViewDefinition(response.data);
    } catch (err) {
      console.error("Failed to fetch view definition:", err);
      setViewDefinition(null);
    } finally {
      setViewDefLoading(false);
    }
  }, [selectedNodeId]);

  // Format milliseconds for display
  const formatMs = (ms: number | undefined): string => {
    if (ms === undefined || ms === null) return "-";
    if (ms >= 1000) return `${(ms / 1000).toFixed(1)}s`;
    return `${ms.toFixed(1)}ms`;
  };

  return (
    <div className="p-6">
      {/* Header - Sticky */}
      <div className="mb-6 sticky top-0 z-10 bg-gray-50 -mx-6 px-6 py-4 -mt-6">
        {/* Top row: Title and Controls */}
        <div className="flex justify-between items-start">
          <h1 className="text-2xl font-bold text-gray-900">Agent Reference Architecture</h1>

          {/* Controls group */}
          <div className="flex items-center gap-3 bg-white rounded-lg border border-gray-200 px-3 py-2 shadow-sm">
            {/* Polling control */}
            <div className="flex items-center gap-2">
              {!isPolling ? (
                <button
                  onClick={handleStartPolling}
                  disabled={!selectedOrderId}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-green-600 text-white rounded-md hover:bg-green-700 disabled:bg-gray-400 disabled:cursor-not-allowed text-sm font-medium"
                >
                  <Play className="h-3.5 w-3.5" />
                  Start
                </button>
              ) : (
                <>
                  <button
                    onClick={handleStopPolling}
                    className="flex items-center gap-1.5 px-3 py-1.5 bg-red-600 text-white rounded-md hover:bg-red-700 text-sm font-medium"
                  >
                    <Square className="h-3.5 w-3.5" />
                    Stop
                  </button>
                  <span className="flex items-center gap-1 text-xs text-green-600">
                    <Wifi className="h-3 w-3" />
                    Live
                  </span>
                </>
              )}
            </div>

            {/* Divider */}
            <div className="w-px h-6 bg-gray-200" />

            {/* View mode */}
            <div className="flex items-center gap-2">
              <label className="text-xs font-medium text-gray-500 uppercase tracking-wide">View</label>
              <select
                value={viewMode}
                onChange={(e) => setViewMode(e.target.value as ViewMode)}
                className="px-2 py-1.5 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 bg-white"
              >
                <option value="query-offload">Query Offload</option>
                <option value="batch">Batch Computation</option>
                <option value="materialize">Materialize</option>
              </select>
            </div>
          </div>
        </div>

        {/* Description row */}
        <p className="text-gray-600 text-sm max-w-3xl">
          Materialize creates a foundational data layer for AI agents by creating a live semantic representation of a business that can handle agent-scale writes and reads from siloed operational databases.
        </p>

        {/* Polling status indicator */}
        {isPolling && (
          <p className="text-xs text-gray-400 mt-1">
            Last update: {new Date(lastUpdateTime).toLocaleTimeString()}
          </p>
        )}
      </div>

      {error && (
        <div className="mb-4 p-4 bg-red-50 text-red-700 rounded-lg">{error}</div>
      )}

      {/* What are Triples? Card */}
      <WhatAreTriplesCard
        selectedOrderId={selectedOrderId}
        orderNumber={zeroOrder?.order_number ?? null}
        lineItemIds={zeroOrder?.line_items?.map((item) => item.line_id) ?? []}
        onTripleClick={handleTripleClick}
        orders={orders}
        onOrderChange={(orderId) => {
          setSelectedOrderId(orderId);
          setTripleSubject(orderId);
          userSetSubjectRef.current = false;
        }}
        isPolling={isPolling}
        refreshTrigger={triplesRefreshTrigger}
      />

      {/* Live Data Products (Collapsible) */}
      <div className="bg-white rounded-lg shadow mb-6">
        <button
          onClick={() => setLineageGraphOpen(!lineageGraphOpen)}
          className="w-full p-4 flex items-center justify-between hover:bg-gray-50 transition-colors"
        >
          <div className="flex items-center gap-2">
            {lineageGraphOpen ? (
              <ChevronDown className="h-5 w-5 text-gray-500" />
            ) : (
              <ChevronRight className="h-5 w-5 text-gray-500" />
            )}
            <div className="text-left">
              <h3 className="text-lg font-semibold text-gray-900">{viewMode === 'materialize' ? 'Real-time data products for agents and apps' : viewMode === 'batch' ? 'Batch data products for agents and apps' : 'Data product APIs for agents and apps'}</h3>
              <p className="text-xs text-gray-500">
                A data product is a named dataset or view that is maintained and exposed for consumption by agents or applications. Unlike a one-off query, it is designed to be discoverable, reusable, and composable across teams and services.
              </p>
            </div>
          </div>
        </button>
        {lineageGraphOpen && (
          <div className="p-6 pt-0 space-y-6">
            {/* Row 1: Lineage Graph — full width */}
            <div>
              <h4 className="text-sm font-semibold text-gray-700 mb-2">
                {viewMode === 'materialize'
                  ? 'Context maintained proactively via live medallion architecture'
                  : viewMode === 'batch'
                  ? 'Context is processed in periodic batches'
                  : 'Context is calculated reactively'}
              </h4>
              <LineageGraph
                selectedNodeId={selectedNodeId}
                onNodeClick={handleNodeClick}
                scenario={viewMode === 'materialize' ? 'materialize' : viewMode === 'batch' ? 'batch' : 'postgres'}
              />
            </div>

            {/* Row 2: JSON API Response — two columns, collapsible */}
            <div className="bg-gray-50 rounded-lg">
              <div
                role="button"
                tabIndex={0}
                onClick={() => setContextReactiveOpen(!contextReactiveOpen)}
                onKeyDown={(e) => e.key === 'Enter' && setContextReactiveOpen(!contextReactiveOpen)}
                className="px-4 py-3 flex items-center gap-2 hover:bg-gray-100 transition-colors rounded-lg cursor-pointer"
              >
                {contextReactiveOpen ? (
                  <ChevronDown className="h-4 w-4 text-gray-500" />
                ) : (
                  <ChevronRight className="h-4 w-4 text-gray-500" />
                )}
                <h4 className="text-sm font-semibold text-gray-700">Context obtained reactively</h4>
              </div>
              {contextReactiveOpen && (
              <div className="px-4 pb-4">
              <div className="flex gap-4 h-[300px]">
                {/* Left: label + SQL */}
                <div className="flex-1 bg-gray-900 rounded-lg overflow-hidden flex flex-col">
                  <div className="px-4 py-3 bg-gray-800 border-b border-gray-700 flex-shrink-0">
                    <div className="flex items-center gap-2">
                      <Database className="h-4 w-4 text-blue-400" />
                      <span className="text-sm font-medium text-gray-200">API Response</span>
                    </div>
                  </div>
                  <div className="flex-1 overflow-auto px-4 py-3 font-mono text-xs text-gray-400 leading-relaxed">
                    <div><span className="text-purple-400">SELECT</span></div>
                    <div className="pl-4">o.order_id, o.order_number, o.order_status,</div>
                    <div className="pl-4">o.store_id, o.customer_id,</div>
                    <div className="pl-4">o.delivery_window_start, o.delivery_window_end,</div>
                    <div className="pl-4">o.order_total_amount,</div>
                    <div className="pl-4">o.customer_name, o.customer_email, o.customer_address,</div>
                    <div className="pl-4">o.store_name, o.store_zone, o.store_address,</div>
                    <div className="pl-4">o.assigned_courier_id, o.delivery_task_status,</div>
                    <div className="pl-4">o.delivery_eta, o.effective_updated_at,</div>
                    <div className="pl-4">p.base_price, p.live_price, p.price_change,</div>
                    <div className="pl-4">p.zone_adjustment, p.perishable_adjustment,</div>
                    <div className="pl-4">p.local_stock_adjustment, p.popularity_adjustment,</div>
                    <div className="pl-4">p.scarcity_adjustment, p.demand_multiplier,</div>
                    <div className="pl-4">p.demand_premium, p.stock_level</div>
                    <div className="mt-1"><span className="text-purple-400">FROM</span> orders_with_lines_mv o</div>
                    <div><span className="text-purple-400">LEFT JOIN</span> inventory_items_with_dynamic_pricing_mv p</div>
                    <div className="pl-4"><span className="text-purple-400">ON</span> p.product_id = o.product_id</div>
                    <div className="pl-4"><span className="text-purple-400">AND</span> p.store_id = o.store_id</div>
                    <div className="mt-1"><span className="text-purple-400">WHERE</span> o.order_id = <span className="text-green-400">:order_id</span></div>
                  </div>
                </div>
                {/* Right: JSON response */}
                <div className="flex-[2] bg-gray-900 rounded-lg overflow-hidden flex flex-col">
                  <div className="flex-1 overflow-auto p-4">
                    {zeroMaterializeOrder ? (
                      <HighlightedJson data={zeroMaterializeOrder} trackingKey={selectedOrderId} />
                    ) : (
                      <pre className="text-xs font-mono text-gray-500">Select an order to see live data...</pre>
                    )}
                  </div>
                </div>
              </div>
              </div>
              )}
            </div>

          </div>
        )}
      </div>

      {/* Time to Trusted Action (Collapsible) */}
      <div className="bg-white rounded-lg shadow mb-6">
        <button
          onClick={() => setTrustedActionOpen(!trustedActionOpen)}
          className="w-full p-4 flex items-center justify-between hover:bg-gray-50 transition-colors"
        >
          <div className="flex items-center gap-2">
            {trustedActionOpen ? (
              <ChevronDown className="h-5 w-5 text-gray-500" />
            ) : (
              <ChevronRight className="h-5 w-5 text-gray-500" />
            )}
            <div className="text-left">
              <h3 className="text-lg font-semibold text-gray-900">Time to trusted action</h3>
              <p className="text-xs text-gray-500">
                Compare how quickly agents can act on fresh, trusted data across storage strategies
              </p>
            </div>
          </div>
        </button>
        {trustedActionOpen && (
          <div className="p-6 pt-0">
            {/* Response Time and Reaction Time Charts - Stacked, each collapsible */}
            <div className="space-y-4 mb-6">
              {/* Response Time Chart */}
              <div className="bg-gray-50 rounded-lg">
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => setResponseChartOpen(!responseChartOpen)}
                  onKeyDown={(e) => e.key === 'Enter' && setResponseChartOpen(!responseChartOpen)}
                  className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-100 transition-colors rounded-lg cursor-pointer"
                >
                  <div className="flex items-center gap-2">
                    {responseChartOpen ? (
                      <ChevronDown className="h-4 w-4 text-gray-500" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-gray-500" />
                    )}
                    <div className="text-left">
                      <h4 className="font-semibold text-gray-900">Response Time Over Time (p99/sec)</h4>
                      <p className="text-xs text-gray-500">Query latency: how long does each query take to execute?</p>
                    </div>
                  </div>
                  {responseChartOpen && (
                    <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => setUseLogScaleResponseTime(false)}
                        className={`px-2 py-1 text-xs rounded ${!useLogScaleResponseTime ? "bg-blue-600 text-white" : "bg-gray-200 text-gray-700"}`}
                      >
                        Linear
                      </button>
                      <button
                        onClick={() => setUseLogScaleResponseTime(true)}
                        className={`px-2 py-1 text-xs rounded ${useLogScaleResponseTime ? "bg-blue-600 text-white" : "bg-gray-200 text-gray-700"}`}
                      >
                        Log
                      </button>
                    </div>
                  )}
                </div>
                {responseChartOpen && (
                <div className="px-4 pb-4">
                  <ResponsiveContainer width="100%" height={250}>
                  <LineChart data={responseTimeChartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="time"
                      tickFormatter={(t) => {
                        const date = new Date(t);
                        return `${date.getUTCHours().toString().padStart(2, '0')}:${date.getUTCMinutes().toString().padStart(2, '0')}:${date.getUTCSeconds().toString().padStart(2, '0')}`;
                      }}
                      domain={[lastUpdateTime - 90000, lastUpdateTime]}
                      type="number"
                      fontSize={15}
                      tick={{ fill: "#6b7280" }}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      scale={useLogScaleResponseTime ? "log" : "linear"}
                      domain={useLogScaleResponseTime ? [1, "auto"] : [0, "auto"]}
                      tickFormatter={(v) =>
                        v >= 1000 ? `${(v / 1000).toFixed(0)}s` : `${v.toFixed(0)}ms`
                      }
                      fontSize={15}
                      tick={{ fill: "#6b7280" }}
                      allowDataOverflow={useLogScaleResponseTime}
                    />
                    <Tooltip
                      formatter={(value: number | undefined) => [value !== undefined ? `${value.toFixed(1)}ms` : "-", ""]}
                      labelFormatter={(t) => {
                        const date = new Date(t as number);
                        return `${date.getUTCHours().toString().padStart(2, '0')}:${date.getUTCMinutes().toString().padStart(2, '0')}:${date.getUTCSeconds().toString().padStart(2, '0')} UTC`;
                      }}
                      contentStyle={{ backgroundColor: "#fff", border: "1px solid #e5e7eb" }}
                    />
                    <Legend wrapperStyle={{ fontSize: '10px' }} />
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
                    {(viewMode === 'batch' || viewMode === 'materialize') && (
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
                    )}
                    {viewMode === 'materialize' && (
                      <Line
                        type="monotone"
                        dataKey="materialize"
                        name="Materialize"
                        stroke="#a855f7"
                        strokeWidth={2}
                        dot={false}
                        connectNulls
                        isAnimationActive={false}
                      />
                    )}
                  </LineChart>
                  </ResponsiveContainer>
                </div>
                )}
              </div>

              {/* Reaction Time Chart */}
              <div className="bg-gray-50 rounded-lg">
                <div
                  role="button"
                  tabIndex={0}
                  onClick={() => setReactionChartOpen(!reactionChartOpen)}
                  onKeyDown={(e) => e.key === 'Enter' && setReactionChartOpen(!reactionChartOpen)}
                  className="w-full px-4 py-3 flex items-center justify-between hover:bg-gray-100 transition-colors rounded-lg cursor-pointer"
                >
                  <div className="flex items-center gap-2">
                    {reactionChartOpen ? (
                      <ChevronDown className="h-4 w-4 text-gray-500" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-gray-500" />
                    )}
                    <div className="text-left">
                      <h4 className="font-semibold text-gray-900">Reaction Time Over Time (p99/sec)</h4>
                      <p className="text-xs text-gray-500">Data freshness: how stale is the data when the query completes?</p>
                    </div>
                  </div>
                  {reactionChartOpen && (
                    <div className="flex gap-2" onClick={(e) => e.stopPropagation()}>
                      <button
                        onClick={() => setUseLogScale(false)}
                        className={`px-2 py-1 text-xs rounded ${!useLogScale ? "bg-blue-600 text-white" : "bg-gray-200 text-gray-700"}`}
                      >
                        Linear
                      </button>
                      <button
                        onClick={() => setUseLogScale(true)}
                        className={`px-2 py-1 text-xs rounded ${useLogScale ? "bg-blue-600 text-white" : "bg-gray-200 text-gray-700"}`}
                      >
                        Log
                      </button>
                    </div>
                  )}
                </div>
                {reactionChartOpen && (
                <div className="px-4 pb-4">
                  <ResponsiveContainer width="100%" height={250}>
                  <LineChart data={chartData}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis
                      dataKey="time"
                      tickFormatter={(t) => {
                        const date = new Date(t);
                        return `${date.getUTCHours().toString().padStart(2, '0')}:${date.getUTCMinutes().toString().padStart(2, '0')}:${date.getUTCSeconds().toString().padStart(2, '0')}`;
                      }}
                      domain={[lastUpdateTime - 90000, lastUpdateTime]}
                      type="number"
                      fontSize={15}
                      tick={{ fill: "#6b7280" }}
                      interval="preserveStartEnd"
                    />
                    <YAxis
                      scale={useLogScale ? "log" : "linear"}
                      domain={useLogScale ? [1, "auto"] : [0, "auto"]}
                      tickFormatter={(v) =>
                        v >= 1000 ? `${(v / 1000).toFixed(0)}s` : `${v.toFixed(0)}ms`
                      }
                      fontSize={15}
                      tick={{ fill: "#6b7280" }}
                      allowDataOverflow={useLogScale}
                    />
                    <Tooltip
                      formatter={(value: number | undefined) => [value !== undefined ? `${value.toFixed(1)}ms` : "-", ""]}
                      labelFormatter={(t) => {
                        const date = new Date(t as number);
                        return `${date.getUTCHours().toString().padStart(2, '0')}:${date.getUTCMinutes().toString().padStart(2, '0')}:${date.getUTCSeconds().toString().padStart(2, '0')} UTC`;
                      }}
                      contentStyle={{ backgroundColor: "#fff", border: "1px solid #e5e7eb" }}
                    />
                    <Legend wrapperStyle={{ fontSize: '10px' }} />
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
                    {(viewMode === 'batch' || viewMode === 'materialize') && (
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
                    )}
                    {viewMode === 'materialize' && (
                      <Line
                        type="monotone"
                        dataKey="materialize"
                        name="Materialize"
                        stroke="#a855f7"
                        strokeWidth={2}
                        dot={false}
                        connectNulls
                        isAnimationActive={false}
                      />
                    )}
                  </LineChart>
                  </ResponsiveContainer>
                </div>
                )}
              </div>
            </div>

            {/* Statistics Table */}
            <div className="bg-gray-50 rounded-lg mb-6">
              <button
                onClick={() => setQueryStatsOpen(!queryStatsOpen)}
                className="w-full p-4 flex items-center justify-between hover:bg-gray-100 transition-colors rounded-lg"
              >
                <div className="flex items-center gap-2">
                  {queryStatsOpen ? (
                    <ChevronDown className="h-4 w-4 text-gray-500" />
                  ) : (
                    <ChevronRight className="h-4 w-4 text-gray-500" />
                  )}
                  <div className="text-left">
                    <h3 className="font-semibold text-gray-900 flex items-center gap-2">
                      <BarChart3 className="h-5 w-5" />
                      Query Statistics - Orders with Lines View
                    </h3>
                    <p className="text-xs text-gray-500 mt-1">
                      Response Time = query latency | Reaction Time = freshness (NOW - effective_updated_at) | QPS = queries/second throughput
                    </p>
                  </div>
                </div>
              </button>
              {queryStatsOpen && <div className="overflow-x-auto">
                <table className="min-w-full text-sm">
                  <thead className="bg-gray-100">
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
                    </tr>
                    <tr className="bg-gray-100">
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
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-200 bg-white">
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
                    </tr>

                    {/* Batch Cache Row - shown in batch and materialize modes */}
                    {(viewMode === 'batch' || viewMode === 'materialize') && (
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
                      </tr>
                    )}

                    {/* Materialize Row - shown only in materialize mode */}
                    {viewMode === 'materialize' && (
                      <tr className="hover:bg-gray-50 bg-blue-50">
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <Zap className="h-4 w-4 text-blue-500" />
                            <div>
                              <div className="font-medium text-gray-900">
                                Materialize
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
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>}
            </div>

          </div>
        )}
      </div>

      {/* View Definition Modal */}
      {selectedNodeId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
                {/* Backdrop */}
                <div
                  className="absolute inset-0 bg-black/50"
                  onClick={() => {
                    setSelectedNodeId(null);
                    setViewDefinition(null);
                  }}
                />
                {/* Modal */}
                <div className="relative bg-gray-900 rounded-lg overflow-hidden w-full max-w-4xl max-h-[80vh] flex flex-col shadow-2xl">
                  {/* Header */}
                  <div className="px-4 py-3 bg-gray-800 border-b border-gray-700 flex-shrink-0">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Code className="h-4 w-4 text-yellow-400" />
                        <span className="text-sm font-medium text-gray-200">View Definition</span>
                      </div>
                      <button
                        onClick={() => {
                          setSelectedNodeId(null);
                          setViewDefinition(null);
                        }}
                        className="text-gray-400 hover:text-gray-200 transition-colors"
                        title="Close"
                      >
                        <X className="h-5 w-5" />
                      </button>
                    </div>
                    <div className="mt-2 font-mono text-xs text-gray-400">
                      <span className="text-purple-400">SHOW CREATE</span>{' '}
                      <span className="text-blue-400">
                        {viewDefinition?.object_type === 'materialized_view' ? 'MATERIALIZED VIEW' :
                         viewDefinition?.object_type === 'source' ? 'SOURCE' :
                         viewDefinition?.object_type === 'table' ? 'TABLE' : 'VIEW'}
                      </span>{' '}
                      <span className="text-green-400">{selectedNodeId}</span>
                    </div>
                  </div>
                  {/* SQL Content */}
                  <div className="flex-1 overflow-auto p-4">
                    {viewDefLoading ? (
                      <div className="flex items-center justify-center py-8">
                        <div className="animate-spin rounded-full h-6 w-6 border-2 border-gray-600 border-t-yellow-400"></div>
                      </div>
                    ) : viewDefinition ? (
                      <SyntaxHighlighter
                        language="sql"
                        style={vscDarkPlus}
                        customStyle={{
                          margin: 0,
                          padding: 0,
                          background: 'transparent',
                          fontSize: '0.875rem',
                        }}
                        wrapLongLines={true}
                      >
                        {viewDefinition.sql}
                      </SyntaxHighlighter>
                    ) : (
                      <pre className="text-xs font-mono text-gray-500">Failed to load view definition</pre>
                    )}
                  </div>
                </div>
              </div>
            )}

      {/* Freshmart UI Components (Collapsible) */}
      <div className="bg-white rounded-lg shadow mb-6">
        <button
          onClick={() => setFreshmartUIOpen(!freshmartUIOpen)}
          className="w-full p-4 flex items-center justify-between hover:bg-gray-50 transition-colors"
        >
          <div className="flex items-center gap-2">
            {freshmartUIOpen ? (
              <ChevronDown className="h-5 w-5 text-gray-500" />
            ) : (
              <ChevronRight className="h-5 w-5 text-gray-500" />
            )}
            <h3 className="text-lg font-semibold text-gray-900">UI components</h3>
          </div>
        </button>
        {freshmartUIOpen && (
          <div className="p-6 pt-0">
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
              {(viewMode === 'batch' || viewMode === 'materialize') && (
                <OrderCard
                  title="Batch MATERIALIZED VIEW"
                  subtitle="Fast but STALE (refreshes every 60s)"
                  icon={<Clock className="h-5 w-5" />}
                  iconColor="text-green-500"
                  bgColor="border-green-500"
                  order={orderData?.batch_cache || null}
                  isLoading={isPolling}
                />
              )}
              {viewMode === 'materialize' && (
                <OrderCard
                  title="Materialize"
                  subtitle="Real-time sync - updates instantly"
                  icon={<Zap className="h-5 w-5" />}
                  iconColor="text-blue-500"
                  bgColor="border-blue-500"
                  order={zeroMaterializeOrder}
                  isLoading={false}
                />
              )}
            </div>
            <WriteTripleForm
              initialSubject={tripleSubject}
              onWritten={() => setTriplesRefreshTrigger(prev => prev + 1)}
            />
          </div>
        )}
      </div>

      {/* Vector Pipeline Card */}
      <VectorPipelineCard />

      {/* What is a Knowledge Graph? Card */}
      <WhatIsKnowledgeGraphCard />
    </div>
  );
}
