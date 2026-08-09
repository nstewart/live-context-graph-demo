import { useEffect, useMemo, useState } from "react";
import { useZero, useQuery } from "@rocicorp/zero/react";
import { VectorPipelineCard } from "../components/VectorPipelineCard";
import { ReferenceArchitectureCard } from "../components/ReferenceArchitectureCard";
import { WhatAreTriplesCard } from "../components/WhatAreTriplesCard";
import { searchApi, queryStatsApi, QueryStatsOrder } from "../api/client";
import { Schema } from "../schema";

// Must never match a real order_id — parks the Zero query until one is picked
const EMPTY_QUERY_SENTINEL = "$$EMPTY_QUERY$$";

export default function VectorSearchPage() {
  // Keep kNN recall healthy for the demo: each order change UPSERTs (and thus
  // tombstones) the search doc, and dead vectors swamp the HNSW graph until a
  // merge expunges them. Expunge deletes on load. Fire-and-forget + debounced
  // server-side, so a slow/failed merge never blocks the page.
  useEffect(() => {
    searchApi.forceMergeSearchIndex().catch(() => {});
  }, []);

  // Order selection drives the triples card below the architecture diagram
  const [orders, setOrders] = useState<QueryStatsOrder[]>([]);
  const [selectedOrderId, setSelectedOrderId] = useState<string>("");

  useEffect(() => {
    let cancelled = false;
    queryStatsApi
      .getOrders()
      .then((res) => {
        if (cancelled) return;
        setOrders(res.data);
        if (res.data.length > 0) setSelectedOrderId(res.data[0].order_id);
      })
      .catch((err) => console.error("Failed to load orders:", err));
    return () => {
      cancelled = true;
    };
  }, []);

  // Line items come from Zero so the triples card follows live edits
  const z = useZero<Schema>();
  const orderQuery = useMemo(
    () =>
      z.query.orders_with_lines_mv.where(
        "order_id",
        "=",
        selectedOrderId || EMPTY_QUERY_SENTINEL
      ),
    [z, selectedOrderId]
  );
  const [orderData] = useQuery(orderQuery);
  const order = orderData?.[0];

  const lineItemIds = useMemo(
    () => order?.line_items?.map((item) => item.line_id) ?? [],
    [order]
  );

  return (
    <div className="p-6">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Freshmart Agent Search Demo</h1>
        <p className="text-sm text-gray-500 mt-1">
          Semantic vector search with live data hydration from Materialize
        </p>
      </div>
      <WhatAreTriplesCard
        selectedOrderId={selectedOrderId}
        orderNumber={order?.order_number ?? null}
        lineItemIds={lineItemIds}
        onTripleClick={() => {}}
        orders={orders}
        onOrderChange={setSelectedOrderId}
        isPolling={false}
        refreshTrigger={0}
      />
      <ReferenceArchitectureCard defaultExpanded />
      <VectorPipelineCard defaultExpanded />
    </div>
  );
}
