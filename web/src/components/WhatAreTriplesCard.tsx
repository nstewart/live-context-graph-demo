import { useState, useEffect, useCallback } from "react";
import { ChevronDown, ChevronRight, ArrowRight, ShoppingCart } from "lucide-react";
import { triplesApi, Triple } from "../api/client";

interface Order {
  order_id: string;
  order_number?: string | null;
  order_status: string | null;
  customer_name?: string | null;
  store_name?: string | null;
}

interface WhatAreTriplesCardProps {
  selectedOrderId: string;
  orderNumber: string | null;
  lineItemIds: string[];
  onTripleClick: (subject: string, predicate: string, value: string) => void;
  refreshTrigger: number; // Increment to trigger refresh
  // Order selector props
  orders: Order[];
  onOrderChange: (orderId: string) => void;
  isPolling: boolean;
}

export const WhatAreTriplesCard = ({
  selectedOrderId,
  orderNumber,
  lineItemIds,
  onTripleClick,
  refreshTrigger,
  orders,
  onOrderChange,
  isPolling,
}: WhatAreTriplesCardProps) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [triples, setTriples] = useState<Triple[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchTriples = useCallback(async () => {
    if (!selectedOrderId) {
      setTriples([]);
      setError(null);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      // Fetch triples for the order
      const orderTriples = await triplesApi.list({ subject_id: selectedOrderId });

      // Fetch triples for each order line
      const lineTriplePromises = lineItemIds.map((lineId) =>
        triplesApi.list({ subject_id: lineId })
      );
      const lineTripleResults = await Promise.all(lineTriplePromises);

      // Combine all triples: order first, then orderlines
      const allTriples = [
        ...orderTriples.data,
        ...lineTripleResults.flatMap((result) => result.data),
      ];

      setTriples(allTriples);
    } catch (error) {
      console.error("Failed to fetch triples:", error);
      setTriples([]);
      setError("Failed to load triples. Please try again.");
    } finally {
      setIsLoading(false);
    }
  }, [selectedOrderId, lineItemIds]);

  // Fetch triples when order changes or refresh is triggered
  useEffect(() => {
    fetchTriples();
  }, [fetchTriples, refreshTrigger]);

  const isEntityRef = (objectType: string) => objectType === "entity_ref";

  return (
    <div className="bg-white rounded-lg shadow mb-6">
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full p-4 flex items-center justify-between hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          {isExpanded ? (
            <ChevronDown className="h-5 w-5 text-gray-500" />
          ) : (
            <ChevronRight className="h-5 w-5 text-gray-500" />
          )}
          <div className="text-left">
            <h3 className="text-lg font-semibold text-gray-900">Agent-Scale Writes</h3>
            <p className="text-xs text-gray-500">
              Using "triples" as the atomic unit of knowledge recorded by agents
            </p>
          </div>
        </div>
        {triples.length > 0 && (
          <span className="text-sm text-gray-500">{triples.length} triples</span>
        )}
      </button>

      {isExpanded && (
        <div className="px-6 pb-6">
          {/* Explainer text */}
          <div className="mb-4 text-sm text-gray-600 leading-relaxed">
            <p>
              Triples are the atomic unit of knowledge&mdash;each captures a single fact as{" "}
              <span className="font-mono text-purple-600">Subject</span>{" "}
              <ArrowRight className="inline h-3 w-3 text-gray-400" />{" "}
              <span className="font-mono text-purple-600">Predicate</span>{" "}
              <ArrowRight className="inline h-3 w-3 text-gray-400" />{" "}
              <span className="font-mono text-purple-600">Value</span>. This structure lets AI
              agents update individual facts without needing complex schemas or full object
              structures.
            </p>
          </div>

          {/* Order Selector */}
          <div className="mb-4">
            <label className="block text-sm font-medium text-gray-700 mb-1">
              <ShoppingCart className="h-4 w-4 inline mr-1" />
              Select Order
            </label>
            <select
              value={selectedOrderId}
              onChange={(e) => onOrderChange(e.target.value)}
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

          {/* Triples table */}
          <div className="border rounded-lg overflow-hidden">
            <div className="bg-gray-50 px-4 py-2 border-b flex justify-between items-center">
              <span className="text-sm font-medium text-gray-700">
                Triples for Order {orderNumber || selectedOrderId}
              </span>
              <span className="text-xs text-gray-500">
                {isLoading ? "Loading..." : `${triples.length} triples`}
              </span>
            </div>

            {error ? (
              <div className="p-4 text-center text-red-600 text-sm">
                {error}
              </div>
            ) : triples.length === 0 && !isLoading ? (
              <div className="p-4 text-center text-gray-500 text-sm">
                No triples found for this order
              </div>
            ) : (
              <div className="max-h-[300px] overflow-y-auto">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 sticky top-0">
                    <tr>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Subject
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Predicate
                      </th>
                      <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                        Value
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {triples.map((triple) => (
                      <tr
                        key={triple.id}
                        onClick={() =>
                          onTripleClick(
                            triple.subject_id,
                            triple.predicate,
                            triple.object_value
                          )
                        }
                        className="hover:bg-purple-50 cursor-pointer transition-colors"
                        title="Click to edit this triple"
                      >
                        <td className="px-4 py-2 font-mono text-xs text-gray-700">
                          {triple.subject_id}
                        </td>
                        <td className="px-4 py-2 font-mono text-xs text-gray-700">
                          {triple.predicate}
                        </td>
                        <td className="px-4 py-2 font-mono text-xs">
                          {isEntityRef(triple.object_type) ? (
                            <span className="text-blue-600">
                              <ArrowRight className="inline h-3 w-3 mr-1" />
                              {triple.object_value}
                            </span>
                          ) : (
                            <span className="text-gray-700">{triple.object_value}</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <p className="mt-3 text-xs text-gray-500">
            Click any row to pre-populate the Write Triple form below. This view shows only
            triples for the selected order and its line items&mdash;the full graph includes
            customers, stores, products, inventory, couriers, and delivery tasks.
          </p>
        </div>
      )}
    </div>
  );
};
