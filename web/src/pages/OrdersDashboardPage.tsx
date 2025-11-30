import React, { useState, useEffect, useMemo } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  freshmartApi,
  triplesApi,
  OrderFlat,
  TripleCreate,
} from "../api/client";
import { useZero, useQuery } from "@rocicorp/zero/react";
import { Schema, OrderLineItem } from "../schema";
import { formatAmount } from "../test/utils";
import {
  Package,
  Clock,
  CheckCircle,
  XCircle,
  Truck,
  Plus,
  Edit2,
  Trash2,
  Wifi,
  WifiOff,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Snowflake,
  Filter,
  X,
} from "lucide-react";
import {
  OrderFormModal,
  OrderWithLines,
  OrderFormData,
} from "../components/OrderFormModal";
import { CartLineItem } from "../components/ShoppingCart";

const statusConfig: Record<string, { color: string; icon: typeof Package }> = {
  CREATED: { color: "bg-blue-100 text-blue-800", icon: Package },
  PICKING: { color: "bg-yellow-100 text-yellow-800", icon: Clock },
  OUT_FOR_DELIVERY: { color: "bg-purple-100 text-purple-800", icon: Truck },
  DELIVERED: { color: "bg-green-100 text-green-800", icon: CheckCircle },
  CANCELLED: { color: "bg-red-100 text-red-800", icon: XCircle },
};

const statusOrder = [
  "CREATED",
  "PICKING",
  "OUT_FOR_DELIVERY",
  "DELIVERED",
  "CANCELLED",
];

function StatusBadge({ status }: { status?: string | null }) {
  const config = statusConfig[status || ""] || {
    color: "bg-gray-100 text-gray-800",
    icon: Package,
  };
  const Icon = config.icon;
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${config.color}`}
    >
      <Icon className="h-3 w-3" />
      {status || "Unknown"}
    </span>
  );
}

function OrdersTable({
  orders,
  onEdit,
  onDelete,
}: {
  orders: OrderWithLines[];
  onEdit: (order: OrderWithLines) => void;
  onDelete: (order: OrderWithLines) => void;
}) {
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const toggleRow = (orderId: string) => {
    const newExpanded = new Set(expandedRows);
    if (newExpanded.has(orderId)) {
      newExpanded.delete(orderId);
    } else {
      newExpanded.add(orderId);
    }
    setExpandedRows(newExpanded);
  };

  return (
    <div className="bg-white rounded-lg shadow overflow-hidden">
      <div className="overflow-x-auto">
        <table className="min-w-full divide-y divide-gray-200">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-2 py-3 w-10"></th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Order
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Status
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Customer
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Store
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Delivery Window
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Amount
              </th>
              <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                Items
              </th>
              <th className="px-4 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                Actions
              </th>
            </tr>
          </thead>
          <tbody className="bg-white divide-y divide-gray-200">
            {orders.map((order) => (
              <React.Fragment key={order.order_id}>
                <tr className="hover:bg-gray-50">
                  <td className="px-2 py-3">
                    <button
                      onClick={() => toggleRow(order.order_id)}
                      className="p-1 hover:bg-gray-200 rounded transition-colors"
                      title="Toggle line items"
                    >
                      {expandedRows.has(order.order_id) ? (
                        <ChevronDown className="h-4 w-4 text-gray-600" />
                      ) : (
                        <ChevronRight className="h-4 w-4 text-gray-600" />
                      )}
                    </button>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900">
                      {order.order_number}
                    </div>
                    <div className="text-xs text-gray-400">
                      {order.order_id}
                    </div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <StatusBadge status={order.order_status} />
                  </td>
                  <td className="px-4 py-3">
                    <div className="text-sm text-gray-900">
                      {order.customer_name || "Unknown"}
                    </div>
                    <div className="text-xs text-gray-500 truncate max-w-xs">
                      {order.customer_address}
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <div className="text-sm text-gray-900">
                      {order.store_name || "Unknown"}
                    </div>
                    <div className="text-xs text-gray-500">
                      {order.store_zone}
                    </div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div className="text-sm text-gray-900">
                      {order.delivery_window_start?.slice(11, 16)} -{" "}
                      {order.delivery_window_end?.slice(11, 16)}
                    </div>
                    <div className="text-xs text-gray-500">
                      {order.delivery_window_start?.slice(0, 10)}
                    </div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div className="text-sm font-medium text-gray-900">
                      ${formatAmount(order.order_total_amount)}
                    </div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <div className="flex items-center gap-1">
                      <span className="text-sm text-gray-900">
                        {order.line_item_count || 0}
                      </span>
                      {order.has_perishable_items && (
                        <span title="Has perishable items">
                          <Snowflake className="h-4 w-4 text-blue-500" />
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap text-right text-sm font-medium">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        onClick={() => onEdit(order)}
                        className="text-blue-600 hover:text-blue-900"
                        title="Edit order"
                      >
                        <Edit2 className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => onDelete(order)}
                        className="text-red-600 hover:text-red-900"
                        title="Delete order"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    </div>
                  </td>
                </tr>

                {/* Expanded Row - Line Items */}
                {expandedRows.has(order.order_id) && (
                  <tr key={`${order.order_id}-expanded`}>
                    <td colSpan={9} className="px-0 py-0">
                      <div className="bg-gray-50 border-t border-b border-gray-200">
                        <LineItemsTable lineItems={order.line_items || []} />
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function LineItemsTable({ lineItems }: { lineItems: OrderLineItem[] }) {
  if (lineItems.length === 0) {
    return (
      <div className="px-8 py-6 text-center">
        <Package className="h-12 w-12 mx-auto mb-2 text-gray-300" />
        <p className="text-sm font-medium text-gray-700">No line items</p>
        <p className="text-xs text-gray-500 mt-1">
          This order has no products added yet
        </p>
      </div>
    );
  }

  return (
    <div className="px-8 py-4">
      <h4 className="text-sm font-semibold text-gray-700 mb-3 flex items-center gap-2">
        <Package className="h-4 w-4" />
        Order Line Items ({lineItems.length})
      </h4>
      <table className="min-w-full text-sm">
        <thead className="bg-gray-100">
          <tr>
            <th className="text-left px-3 py-2 text-xs font-medium text-gray-600">
              Product
            </th>
            <th className="text-center px-3 py-2 text-xs font-medium text-gray-600">
              Quantity
            </th>
            <th className="text-right px-3 py-2 text-xs font-medium text-gray-600">
              Order Price
            </th>
            <th className="text-right px-3 py-2 text-xs font-medium text-gray-600">
              Base Price
            </th>
            <th className="text-right px-3 py-2 text-xs font-medium text-gray-600">
              Live Price
            </th>
            <th className="text-right px-3 py-2 text-xs font-medium text-gray-600">
              Line Total
            </th>
            <th className="text-center px-3 py-2 text-xs font-medium text-gray-600 w-20">
              Status
            </th>
          </tr>
        </thead>
        <tbody className="bg-white divide-y divide-gray-100">
          {lineItems.map((item) => (
            <tr key={item.line_id} className="hover:bg-gray-50">
              <td className="px-3 py-2">
                <div className="flex items-center gap-2">
                  <span className="font-medium text-gray-900">
                    {item.product_name || item.product_id}
                  </span>
                  {item.perishable_flag && (
                    <span title="Perishable - requires cold chain">
                      <Snowflake className="h-4 w-4 text-blue-600" />
                    </span>
                  )}
                </div>
                {item.category && (
                  <div className="text-xs text-gray-500 mt-0.5">
                    {item.category}
                  </div>
                )}
              </td>
              <td className="px-3 py-2 text-center text-gray-900">
                {item.quantity}
              </td>
              <td className="px-3 py-2 text-right text-gray-900">
                ${formatAmount(item.unit_price)}
              </td>
              <td className="px-3 py-2 text-right text-gray-700">
                {item.base_price != null ? (
                  <span>${formatAmount(item.base_price)}</span>
                ) : (
                  <span className="text-gray-400">-</span>
                )}
              </td>
              <td className="px-3 py-2 text-right">
                {item.live_price != null ? (
                  <div className="flex flex-col items-end">
                    <span className="font-medium text-gray-900">
                      ${formatAmount(item.live_price)}
                    </span>
                    {item.price_change != null && item.price_change !== 0 && (
                      <span className={`text-xs ${item.price_change > 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {item.price_change > 0 ? '+' : ''}${formatAmount(item.price_change)}
                      </span>
                    )}
                  </div>
                ) : (
                  <span className="text-gray-400">-</span>
                )}
              </td>
              <td className="px-3 py-2 text-right font-medium text-gray-900">
                ${formatAmount(item.line_amount)}
              </td>
              <td className="px-3 py-2 text-center">
                {item.perishable_flag ? (
                  <Snowflake className="h-4 w-4 inline-block text-blue-600" />
                ) : (
                  <span className="text-gray-400">-</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr className="bg-gray-50 font-semibold">
            <td colSpan={5} className="px-3 py-2 text-right text-gray-700">
              Subtotal (
              {lineItems.reduce((sum, item) => sum + item.quantity, 0)} items):
            </td>
            <td className="px-3 py-2 text-right text-gray-900">
              $
              {formatAmount(
                lineItems.reduce((sum, item) => sum + item.line_amount, 0)
              )}
            </td>
            <td></td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}

export default function OrdersDashboardPage() {
  const queryClient = useQueryClient();
  const [showModal, setShowModal] = useState(false);
  const [editingOrder, setEditingOrder] = useState<
    OrderWithLines | undefined
  >();
  const [deleteConfirm, setDeleteConfirm] = useState<OrderWithLines | null>(
    null
  );
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 100;

  // Filter state
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [storeFilter, setStoreFilter] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState<string>("");

  // 🔥 ZERO - Real-time data using orders_with_lines_mv (includes embedded line items)
  const z = useZero<Schema>();

  // Get stores for filter dropdown
  const [storesData] = useQuery(z.query.stores_mv.orderBy("store_name", "asc"));

  // Build filtered query with related data (joins orders_with_lines_mv with orders_search_source_mv)
  let ordersQuery = z.query.orders_with_lines_mv.related("searchData");

  if (statusFilter) {
    ordersQuery = ordersQuery.where("order_status", "=", statusFilter);
  }
  if (storeFilter) {
    ordersQuery = ordersQuery.where("store_id", "=", storeFilter);
  }
  if (searchQuery.trim()) {
    const pattern = `%${searchQuery.trim()}%`;
    ordersQuery = ordersQuery.where("order_number", "ILIKE", pattern);
  }

  const [ordersData] = useQuery(ordersQuery.orderBy("order_number", "asc"));

  // Map to OrderWithLines type, pulling names from the related searchData
  const orders: OrderWithLines[] = useMemo(
    () =>
      ordersData.map((o) => ({
        order_id: o.order_id,
        order_number: o.order_number,
        order_status: o.order_status,
        store_id: o.store_id,
        customer_id: o.customer_id,
        delivery_window_start: o.delivery_window_start,
        delivery_window_end: o.delivery_window_end,
        order_total_amount: o.order_total_amount,
        // Names from related searchData
        customer_name: o.searchData?.customer_name,
        customer_email: o.searchData?.customer_email,
        customer_address: o.searchData?.customer_address,
        store_name: o.searchData?.store_name,
        store_zone: o.searchData?.store_zone,
        store_address: o.searchData?.store_address,
        assigned_courier_id: o.searchData?.assigned_courier_id,
        delivery_task_status: o.searchData?.delivery_task_status,
        delivery_eta: o.searchData?.delivery_eta,
        // Line items with defaults
        line_items: o.line_items ?? [],
        line_item_count: o.line_item_count ?? 0,
        has_perishable_items: o.has_perishable_items ?? false,
      })),
    [ordersData]
  );

  // Check if any filters are active
  const hasActiveFilters = statusFilter || storeFilter || searchQuery;

  const clearFilters = () => {
    setStatusFilter("");
    setStoreFilter("");
    setSearchQuery("");
  };

  // Track last update time when Zero data changes
  const [lastUpdateTime, setLastUpdateTime] = useState<number>(Date.now());

  useEffect(() => {
    if (ordersData.length > 0) {
      setLastUpdateTime(Date.now());
    }
  }, [ordersData]);

  const isLoading = ordersData.length === 0 && !hasActiveFilters;

  const createMutation = useMutation({
    mutationFn: async ({ data, lineItems }: { data: OrderFormData; lineItems: CartLineItem[] }) => {
      const orderId = `order:${data.order_number}`;
      const triples: TripleCreate[] = [
        {
          subject_id: orderId,
          predicate: "order_number",
          object_value: data.order_number,
          object_type: "string",
        },
        {
          subject_id: orderId,
          predicate: "order_status",
          object_value: data.order_status,
          object_type: "string",
        },
        {
          subject_id: orderId,
          predicate: "placed_by",
          object_value: data.customer_id,
          object_type: "entity_ref",
        },
        {
          subject_id: orderId,
          predicate: "order_store",
          object_value: data.store_id,
          object_type: "entity_ref",
        },
      ];
      if (data.order_total_amount) {
        triples.push({
          subject_id: orderId,
          predicate: "order_total_amount",
          object_value: data.order_total_amount,
          object_type: "float",
        });
      }
      if (data.delivery_window_start) {
        triples.push({
          subject_id: orderId,
          predicate: "delivery_window_start",
          object_value: new Date(data.delivery_window_start).toISOString(),
          object_type: "timestamp",
        });
      }
      if (data.delivery_window_end) {
        triples.push({
          subject_id: orderId,
          predicate: "delivery_window_end",
          object_value: new Date(data.delivery_window_end).toISOString(),
          object_type: "timestamp",
        });
      }

      // Add line items to the same batch (transactional with order creation)
      if (lineItems.length > 0) {
        lineItems.forEach((item, index) => {
          const lineItemId = `orderline:${data.order_number}-${String(index + 1).padStart(3, '0')}`;
          const lineAmount = item.quantity * item.unit_price;

          triples.push(
            {
              subject_id: lineItemId,
              predicate: "line_of_order",
              object_value: orderId,
              object_type: "entity_ref",
            },
            {
              subject_id: lineItemId,
              predicate: "line_product",
              object_value: item.product_id,
              object_type: "entity_ref",
            },
            {
              subject_id: lineItemId,
              predicate: "quantity",
              object_value: String(item.quantity),
              object_type: "int",
            },
            {
              subject_id: lineItemId,
              predicate: "order_line_unit_price",
              object_value: String(item.unit_price),
              object_type: "float",
            },
            {
              subject_id: lineItemId,
              predicate: "line_amount",
              object_value: String(lineAmount.toFixed(2)),
              object_type: "float",
            },
            {
              subject_id: lineItemId,
              predicate: "line_sequence",
              object_value: String(index + 1),
              object_type: "int",
            },
            {
              subject_id: lineItemId,
              predicate: "perishable_flag",
              object_value: String(item.perishable_flag).toLowerCase(),
              object_type: "bool",
            }
          );
        });
      }

      // Create order and all line items in a single transactional batch
      await triplesApi.createBatch(triples);

      return { orderId };
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      setShowModal(false);
      setEditingOrder(undefined);
    },
  });

  const updateMutation = useMutation({
    mutationFn: async ({
      order,
      data,
      lineItems,
    }: {
      order: OrderFlat;
      data: OrderFormData;
      lineItems: CartLineItem[];
    }) => {
      // Build triples for batch update
      const fieldsToUpdate: {
        predicate: string;
        value: string;
        type: TripleCreate["object_type"];
      }[] = [
        { predicate: "order_status", value: data.order_status, type: "string" },
        { predicate: "placed_by", value: data.customer_id, type: "entity_ref" },
        { predicate: "order_store", value: data.store_id, type: "entity_ref" },
      ];
      if (data.order_total_amount) {
        fieldsToUpdate.push({
          predicate: "order_total_amount",
          value: data.order_total_amount,
          type: "float",
        });
      }
      if (data.delivery_window_start) {
        fieldsToUpdate.push({
          predicate: "delivery_window_start",
          value: new Date(data.delivery_window_start).toISOString(),
          type: "timestamp",
        });
      }
      if (data.delivery_window_end) {
        fieldsToUpdate.push({
          predicate: "delivery_window_end",
          value: new Date(data.delivery_window_end).toISOString(),
          type: "timestamp",
        });
      }

      // Upsert triples in a single atomic transaction
      // The upsert endpoint deletes old values and inserts new ones - no duplicates
      const triplesToUpsert: TripleCreate[] = fieldsToUpdate.map(field => ({
        subject_id: order.order_id,
        predicate: field.predicate,
        object_value: field.value,
        object_type: field.type,
      }));

      // Single atomic transaction: deletes old predicates and inserts new values
      if (triplesToUpsert.length > 0) {
        await triplesApi.upsertBatch(triplesToUpsert);
      }

      // Handle line items: compare with existing line items
      const existingLineItems = await freshmartApi
        .listOrderLines(order.order_id)
        .then((r: { data: any }) => r.data)
        .catch(() => []);

      // Build maps for easier lookup
      const existingByProductId = new Map<string, any>(
        existingLineItems.map((item: any) => [item.product_id, item])
      );
      const cartByProductId = new Map<string, CartLineItem>(
        lineItems.map((item) => [item.product_id, item])
      );

      const lineItemOperations: Promise<any>[] = [];

      // 1. Update quantities of existing items that changed
      for (const existingItem of existingLineItems) {
        const cartItem = cartByProductId.get(existingItem.product_id);
        if (cartItem && cartItem.quantity !== existingItem.quantity) {
          lineItemOperations.push(
            freshmartApi.updateOrderLine(order.order_id, existingItem.line_id, {
              quantity: cartItem.quantity,
            })
          );
        }
      }

      // 2. Delete items removed from cart
      for (const existingItem of existingLineItems) {
        if (!cartByProductId.has(existingItem.product_id)) {
          lineItemOperations.push(
            freshmartApi.deleteOrderLine(order.order_id, existingItem.line_id)
          );
        }
      }

      // 3. Add new items in cart (not in existing line items)
      const newItems = lineItems.filter(
        (item) => !existingByProductId.has(item.product_id)
      );
      if (newItems.length > 0) {
        // Get next sequence number
        const maxSequence =
          existingLineItems.length > 0
            ? Math.max(
                ...existingLineItems.map((item: any) => item.line_sequence)
              )
            : 0;

        const lineItemsToCreate = newItems.map((item, index) => ({
          product_id: item.product_id,
          quantity: item.quantity,
          unit_price: item.unit_price,
          line_sequence: maxSequence + index + 1,
          perishable_flag: item.perishable_flag,
        }));

        lineItemOperations.push(
          freshmartApi.createOrderLinesBatch(order.order_id, lineItemsToCreate)
        );
      }

      // Execute all line item operations
      if (lineItemOperations.length > 0) {
        await Promise.all(lineItemOperations);
      }
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      setShowModal(false);
      setEditingOrder(undefined);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (orderId: string) => triplesApi.deleteSubject(orderId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      setDeleteConfirm(null);
    },
  });

  const handleSave = (data: OrderFormData, isEdit: boolean, lineItems: CartLineItem[]) => {
    if (isEdit && editingOrder) {
      updateMutation.mutate({ order: editingOrder, data, lineItems });
    } else {
      createMutation.mutate({ data, lineItems });
    }
  };

  const handleEdit = (order: OrderWithLines) => {
    setEditingOrder(order);
    setShowModal(true);
  };

  const handleDelete = (order: OrderWithLines) => {
    setDeleteConfirm(order);
  };

  // Calculate stats from ALL orders (not paginated)
  const ordersByStatus = useMemo(() => {
    return orders.reduce(
      (acc, order) => {
        const status = order.order_status || "Unknown";
        if (!acc[status]) acc[status] = [];
        acc[status].push(order);
        return acc;
      },
      {} as Record<string, typeof orders>
    );
  }, [orders]);

  // Pagination calculations (orders already sorted by Zero query)
  const totalOrders = orders.length;
  const totalPages = Math.ceil(totalOrders / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = startIndex + itemsPerPage;
  const paginatedOrders = orders.slice(startIndex, endIndex);

  return (
    <div className="p-6">
      <div className="flex justify-between items-center mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-gray-900">
              Orders Dashboard
            </h1>
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
          <p className="text-gray-600">
            Monitor and manage FreshMart orders via WebSocket
          </p>
        </div>
        <button
          onClick={() => {
            setEditingOrder(undefined);
            setShowModal(true);
          }}
          className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700"
        >
          <Plus className="h-4 w-4" />
          Create Order
        </button>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-lg shadow p-4 mb-6">
        <div className="flex items-center gap-4 flex-wrap">
          <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
            <Filter className="h-4 w-4" />
            Filters
          </div>

          {/* Search */}
          <div className="flex-1 min-w-[200px] max-w-xs">
            <input
              type="text"
              placeholder="Search order #..."
              value={searchQuery}
              onChange={(e) => {
                setSearchQuery(e.target.value);
                setCurrentPage(1);
              }}
              className="w-full px-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
            />
          </div>

          {/* Status Filter */}
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setCurrentPage(1);
            }}
            className="px-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
          >
            <option value="">All Statuses</option>
            {statusOrder.map((status) => (
              <option key={status} value={status}>
                {status.replace("_", " ")}
              </option>
            ))}
          </select>

          {/* Store Filter */}
          <select
            value={storeFilter}
            onChange={(e) => {
              setStoreFilter(e.target.value);
              setCurrentPage(1);
            }}
            className="px-3 py-2 text-sm border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
          >
            <option value="">All Stores</option>
            {storesData.map((store) => (
              <option key={store.store_id} value={store.store_id}>
                {store.store_name || store.store_id}
              </option>
            ))}
          </select>

          {/* Clear Filters */}
          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              className="flex items-center gap-1 px-3 py-2 text-sm text-gray-600 hover:text-gray-900 hover:bg-gray-100 rounded-lg transition-colors"
            >
              <X className="h-4 w-4" />
              Clear
            </button>
          )}

          {/* Active filter count */}
          {hasActiveFilters && (
            <span className="text-xs text-gray-500">
              Showing {orders.length} orders
            </span>
          )}
        </div>
      </div>

      {isLoading && (
        <div className="text-center py-8 text-gray-500">Loading orders...</div>
      )}

      {orders.length > 0 && (
        <>
          {/* Stats */}
          <div className="grid grid-cols-5 gap-4 mb-6">
            {statusOrder.map((status) => (
              <div key={status} className="bg-white rounded-lg shadow p-4">
                <div className="text-sm text-gray-500">
                  {status.replace("_", " ")}
                </div>
                <div className="text-2xl font-bold text-gray-900">
                  {ordersByStatus[status]?.length || 0}
                </div>
              </div>
            ))}
          </div>

          {/* Orders table */}
          <OrdersTable
            orders={paginatedOrders}
            onEdit={handleEdit}
            onDelete={handleDelete}
          />

          {/* Pagination Controls */}
          {totalPages > 1 && (
            <div className="mt-6 flex items-center justify-between">
              <div className="text-sm text-gray-600">
                Showing {startIndex + 1}-{Math.min(endIndex, totalOrders)} of{" "}
                {totalOrders} orders
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  disabled={currentPage === 1}
                  className="p-2 border rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  title="Previous page"
                >
                  <ChevronLeft className="h-4 w-4" />
                </button>
                <div className="flex items-center gap-1">
                  {/* Show first page */}
                  {currentPage > 3 && (
                    <>
                      <button
                        onClick={() => setCurrentPage(1)}
                        className="px-3 py-1 border rounded hover:bg-gray-50"
                      >
                        1
                      </button>
                      <span className="px-2">...</span>
                    </>
                  )}

                  {/* Show pages around current */}
                  {Array.from({ length: totalPages }, (_, i) => i + 1)
                    .filter(
                      (page) =>
                        page >= currentPage - 2 && page <= currentPage + 2
                    )
                    .map((page) => (
                      <button
                        key={page}
                        onClick={() => setCurrentPage(page)}
                        className={`px-3 py-1 border rounded ${page === currentPage ? "bg-green-600 text-white" : "hover:bg-gray-50"}`}
                      >
                        {page}
                      </button>
                    ))}

                  {/* Show last page */}
                  {currentPage < totalPages - 2 && (
                    <>
                      <span className="px-2">...</span>
                      <button
                        onClick={() => setCurrentPage(totalPages)}
                        className="px-3 py-1 border rounded hover:bg-gray-50"
                      >
                        {totalPages}
                      </button>
                    </>
                  )}
                </div>
                <button
                  onClick={() =>
                    setCurrentPage((p) => Math.min(totalPages, p + 1))
                  }
                  disabled={currentPage === totalPages}
                  className="p-2 border rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed"
                  title="Next page"
                >
                  <ChevronRight className="h-4 w-4" />
                </button>
              </div>
            </div>
          )}
        </>
      )}

      {/* Create/Edit Modal - queries its own stores/customers data */}
      <OrderFormModal
        isOpen={showModal}
        onClose={() => {
          setShowModal(false);
          setEditingOrder(undefined);
        }}
        order={editingOrder}
        onSave={handleSave}
        isLoading={createMutation.isPending || updateMutation.isPending}
      />

      {/* Delete Confirmation */}
      {deleteConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-sm mx-4">
            <h3 className="text-lg font-semibold mb-2">Delete Order</h3>
            <p className="text-gray-600 mb-4">
              Are you sure you want to delete order{" "}
              <strong>{deleteConfirm.order_number}</strong>? This action cannot
              be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={() => deleteMutation.mutate(deleteConfirm.order_id)}
                disabled={deleteMutation.isPending}
                className="px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 disabled:opacity-50"
              >
                {deleteMutation.isPending ? "Deleting..." : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
