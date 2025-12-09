import React, { useState, useEffect, useCallback, useMemo } from "react";
import { useZero, useQuery } from "@rocicorp/zero/react";
import { Schema, OrderLineItem } from "../schema";
import { X, AlertTriangle } from "lucide-react";
import { ProductSelector, ProductWithStock } from "./ProductSelector";
import { ShoppingCart, CartLineItem } from "./ShoppingCart";
import { OrderFlat } from "../api/client";

const statusOrder = [
  "CREATED",
  "PICKING",
  "OUT_FOR_DELIVERY",
  "DELIVERED",
  "CANCELLED",
];

export interface OrderFormData {
  order_number: string;
  customer_id: string;
  store_id: string;
  order_status: string;
  order_total_amount: string;
  delivery_window_start: string;
  delivery_window_end: string;
}

// Extended order type with line items from Zero
export interface OrderWithLines extends OrderFlat {
  line_items?: OrderLineItem[] | null;
  line_item_count?: number | null;
  has_perishable_items?: boolean | null;
}

interface OrderFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  order?: OrderWithLines;
  onSave: (data: OrderFormData, isEdit: boolean, lineItems: CartLineItem[]) => void;
  isLoading: boolean;
}

export function OrderFormModal({
  isOpen,
  onClose,
  order,
  onSave,
  isLoading,
}: OrderFormModalProps) {
  // Memoize initialFormData to fix useEffect dependency warning
  const initialFormData: OrderFormData = useMemo(() => ({
    order_number: "",
    customer_id: "",
    store_id: "",
    order_status: "CREATED",
    order_total_amount: "",
    delivery_window_start: "",
    delivery_window_end: "",
  }), []);

  const [formData, setFormData] = useState<OrderFormData>(initialFormData);
  const [lineItems, setLineItems] = useState<CartLineItem[]>([]);
  const [showStoreChangeConfirm, setShowStoreChangeConfirm] = useState(false);
  const [pendingStoreId, setPendingStoreId] = useState<string>("");
  const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);
  const [showCloseConfirm, setShowCloseConfirm] = useState(false);

  // Zero queries for stores and customers
  const z = useZero<Schema>();
  const [storesData] = useQuery(z.query.stores_mv.orderBy("store_id", "asc"));
  const [customersData] = useQuery(
    z.query.customers_mv.orderBy("customer_id", "asc")
  );

  // Calculate total from line items
  const getTotal = useCallback(() => {
    return lineItems.reduce((sum, item) => sum + item.line_amount, 0);
  }, [lineItems]);

  // Load existing data when editing
  useEffect(() => {
    if (order && order.order_id) {
      setFormData({
        order_number: order.order_number || "",
        customer_id: order.customer_id || "",
        store_id: order.store_id || "",
        order_status: order.order_status || "CREATED",
        order_total_amount: order.order_total_amount?.toString() || "",
        delivery_window_start: order.delivery_window_start?.slice(0, 16) || "",
        delivery_window_end: order.delivery_window_end?.slice(0, 16) || "",
      });

      // Load line items from order
      const items = order.line_items || [];
      const cartItems: CartLineItem[] = items.map((item) => {
        const lineAmount = item.line_amount || 0;
        const quantity = item.quantity || 0;
        const unitPrice =
          Number(item.unit_price) || (quantity > 0 ? lineAmount / quantity : 0);
        return {
          product_id: item.product_id,
          product_name: item.product_name || "Unknown Product",
          quantity: quantity,
          unit_price: unitPrice,
          perishable_flag: item.perishable_flag || false,
          available_stock: item.current_stock_level ?? 999, // Use actual stock level or fallback
          category: item.category || undefined,
          line_amount: lineAmount,
        };
      });
      setLineItems(cartItems);
    } else {
      setFormData(initialFormData);
      setLineItems([]);
    }
  }, [order]);

  // Clear state when modal closes
  useEffect(() => {
    if (!isOpen) {
      setLineItems([]);
      setFormData(initialFormData);
      setHasUnsavedChanges(false);
    }
  }, [isOpen, initialFormData]);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (!order && lineItems.length === 0) {
      alert("Please add at least one product to the order");
      return;
    }

    const total = getTotal();
    const dataWithTotal = {
      ...formData,
      order_total_amount: total > 0 ? total.toFixed(2) : formData.order_total_amount,
    };

    // Reset unsaved changes flag before saving
    // This is the ONLY place where data is saved to the database
    setHasUnsavedChanges(false);
    onSave(dataWithTotal, !!order, lineItems);
  };

  const handleStoreChange = (newStoreId: string) => {
    if (formData.store_id && formData.store_id !== newStoreId && lineItems.length > 0) {
      // Store change requires confirmation when cart has items
      setPendingStoreId(newStoreId);
      setShowStoreChangeConfirm(true);
    } else {
      setFormData({ ...formData, store_id: newStoreId });
      setLineItems([]); // Clear cart when store changes
      setHasUnsavedChanges(false); // Reset unsaved changes flag when cart is cleared
    }
  };

  const confirmStoreChange = () => {
    setFormData({ ...formData, store_id: pendingStoreId });
    setLineItems([]);
    setHasUnsavedChanges(false); // Reset unsaved changes flag when cart is cleared
    setShowStoreChangeConfirm(false);
    setPendingStoreId("");
  };

  const cancelStoreChange = () => {
    setShowStoreChangeConfirm(false);
    setPendingStoreId("");
  };

  const handleClose = () => {
    if (hasUnsavedChanges && order) {
      setShowCloseConfirm(true);
    } else {
      onClose();
    }
  };

  const confirmClose = () => {
    setShowCloseConfirm(false);
    setHasUnsavedChanges(false);
    onClose();
  };

  const cancelClose = () => {
    setShowCloseConfirm(false);
  };

  const handleProductSelect = (product: ProductWithStock) => {
    // Mark that there are unsaved changes (only updates local state, doesn't save to DB)
    setHasUnsavedChanges(true);

    setLineItems((prev) => {
      const existingIndex = prev.findIndex(
        (item) => item.product_id === product.product_id
      );

      if (existingIndex !== -1) {
        // Update existing item
        const existing = prev[existingIndex];
        const newQuantity = existing.quantity + 1;

        if (newQuantity > product.stock_level) {
          alert(
            `Cannot add more. Only ${product.stock_level - existing.quantity} remaining in stock.`
          );
          return prev;
        }

        const updated = [...prev];
        updated[existingIndex] = {
          ...existing,
          quantity: newQuantity,
          unit_price: product.unit_price || existing.unit_price,
          live_price: product.live_price || existing.live_price,
          base_price: product.base_price || existing.base_price,
          line_amount: newQuantity * (product.unit_price || existing.unit_price),
          available_stock: product.stock_level,
        };
        return updated;
      } else {
        // Add new item
        if (product.stock_level < 1) {
          alert("Product is out of stock");
          return prev;
        }

        return [
          ...prev,
          {
            product_id: product.product_id,
            product_name: product.product_name || "Unknown Product",
            quantity: 1,
            unit_price: product.unit_price || 0,
            live_price: product.live_price || undefined,
            base_price: product.base_price || undefined,
            perishable_flag: product.perishable || false,
            available_stock: product.stock_level,
            category: product.category || undefined,
            line_amount: product.unit_price || 0,
          },
        ];
      }
    });
  };

  const handleUpdateQuantity = (productId: string, quantity: number) => {
    if (quantity <= 0) {
      handleRemoveItem(productId);
      return;
    }

    // Mark that there are unsaved changes (only updates local state, doesn't save to DB)
    setHasUnsavedChanges(true);

    setLineItems((prev) => {
      const item = prev.find((i) => i.product_id === productId);
      if (!item) return prev;

      if (quantity > item.available_stock) {
        throw new Error(
          `Cannot set quantity to ${quantity}. Only ${item.available_stock} available.`
        );
      }

      return prev.map((i) =>
        i.product_id === productId
          ? { ...i, quantity, line_amount: quantity * i.unit_price }
          : i
      );
    });
  };

  const handleRemoveItem = (productId: string) => {
    // Mark that there are unsaved changes (only updates local state, doesn't save to DB)
    setHasUnsavedChanges(true);
    setLineItems((prev) => prev.filter((item) => item.product_id !== productId));
  };

  const total = getTotal();

  return (
    <>
      <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
        <div className="bg-white rounded-lg shadow-xl w-full max-w-4xl mx-4 max-h-[90vh] overflow-y-auto">
          <div className="flex justify-between items-center p-4 border-b">
            <h2 className="text-lg font-semibold">
              {order ? "Edit Order" : "Create Order"}
            </h2>
            <button
              onClick={handleClose}
              className="text-gray-500 hover:text-gray-700"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
          <form onSubmit={handleSubmit} className="p-4 space-y-4">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Order Number *
                </label>
                <input
                  type="text"
                  required
                  disabled={!!order}
                  value={formData.order_number}
                  onChange={(e) => {
                    setFormData({ ...formData, order_number: e.target.value });
                    if (order) setHasUnsavedChanges(true);
                  }}
                  placeholder="FM-1001"
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 disabled:bg-gray-100"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Status *
                </label>
                <select
                  required
                  value={formData.order_status}
                  onChange={(e) => {
                    setFormData({ ...formData, order_status: e.target.value });
                    if (order) setHasUnsavedChanges(true);
                  }}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
                >
                  {statusOrder.map((status) => (
                    <option key={status} value={status}>
                      {status.replace("_", " ")}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Customer *
                </label>
                <select
                  required
                  value={formData.customer_id}
                  onChange={(e) => {
                    setFormData({ ...formData, customer_id: e.target.value });
                    if (order) setHasUnsavedChanges(true);
                  }}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
                >
                  <option value="">Select a customer...</option>
                  {customersData.map((customer) => (
                    <option
                      key={customer.customer_id}
                      value={customer.customer_id}
                    >
                      {customer.customer_name || "Unknown"} (
                      {customer.customer_id})
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Store *
                </label>
                <select
                  required
                  value={formData.store_id}
                  onChange={(e) => handleStoreChange(e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
                >
                  <option value="">Select a store...</option>
                  {storesData.map((store) => (
                    <option key={store.store_id} value={store.store_id}>
                      {store.store_name || "Unknown"} ({store.store_id})
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Product Selector */}
            <div>
              <ProductSelector
                storeId={formData.store_id || null}
                onProductSelect={handleProductSelect}
                disabled={!formData.store_id}
              />
            </div>

            {/* Shopping Cart */}
            <div>
              <ShoppingCart
                lineItems={lineItems}
                onUpdateQuantity={handleUpdateQuantity}
                onRemoveItem={handleRemoveItem}
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Total Amount
                <span className="ml-2 text-xs text-gray-500">
                  (Auto-calculated from cart)
                </span>
              </label>
              <input
                type="number"
                step="0.01"
                value={total > 0 ? total.toFixed(2) : formData.order_total_amount}
                readOnly
                placeholder="0.00"
                className="w-full px-3 py-2 border rounded-lg bg-gray-50 text-gray-700"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Delivery Window Start
                </label>
                <input
                  type="datetime-local"
                  value={formData.delivery_window_start}
                  onChange={(e) => {
                    setFormData({
                      ...formData,
                      delivery_window_start: e.target.value,
                    });
                    if (order) setHasUnsavedChanges(true);
                  }}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Delivery Window End
                </label>
                <input
                  type="datetime-local"
                  value={formData.delivery_window_end}
                  onChange={(e) => {
                    setFormData({
                      ...formData,
                      delivery_window_end: e.target.value,
                    });
                    if (order) setHasUnsavedChanges(true);
                  }}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500"
                />
              </div>
            </div>
            {hasUnsavedChanges && order && (
              <div
                className="flex items-center gap-2 px-4 py-3 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-800"
                role="alert"
                aria-live="polite"
              >
                <AlertTriangle className="h-4 w-4 flex-shrink-0" aria-label="Warning" />
                <span>You have unsaved changes. Click "Update" to save them to the database.</span>
              </div>
            )}
            <div className="flex justify-end gap-2 pt-4">
              <button
                type="button"
                onClick={handleClose}
                className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isLoading}
                className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50"
              >
                {isLoading ? "Saving..." : order ? "Update" : "Create"}
              </button>
            </div>
          </form>
        </div>
      </div>

      {/* Store Change Confirmation Dialog */}
      {showStoreChangeConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-60">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-sm mx-4">
            <div className="flex items-start gap-3 mb-4">
              <div className="p-2 bg-orange-100 rounded-lg">
                <AlertTriangle className="h-5 w-5 text-orange-600" />
              </div>
              <div>
                <h3 className="text-lg font-semibold mb-1">Change Store?</h3>
                <p className="text-gray-600 text-sm">
                  Changing the store will clear all items from your cart. Are
                  you sure?
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={cancelStoreChange}
                className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={confirmStoreChange}
                className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700"
              >
                Change Store
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Close Confirmation Dialog */}
      {showCloseConfirm && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-60">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-sm mx-4">
            <div className="flex items-start gap-3 mb-4">
              <div className="p-2 bg-orange-100 rounded-lg">
                <AlertTriangle className="h-5 w-5 text-orange-600" />
              </div>
              <div>
                <h3 className="text-lg font-semibold mb-1">Discard Changes?</h3>
                <p className="text-gray-600 text-sm">
                  You have unsaved changes. Are you sure you want to close
                  without saving?
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <button
                onClick={cancelClose}
                className="px-4 py-2 text-gray-700 border rounded-lg hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={confirmClose}
                className="px-4 py-2 bg-orange-600 text-white rounded-lg hover:bg-orange-700"
              >
                Discard Changes
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
