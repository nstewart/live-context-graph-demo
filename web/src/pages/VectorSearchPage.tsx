import { useEffect } from "react";
import { VectorPipelineCard } from "../components/VectorPipelineCard";
import { searchApi } from "../api/client";

export default function VectorSearchPage() {
  // Keep kNN recall healthy for the demo: each order change UPSERTs (and thus
  // tombstones) the search doc, and dead vectors swamp the HNSW graph until a
  // merge expunges them. Expunge deletes on load. Fire-and-forget + debounced
  // server-side, so a slow/failed merge never blocks the page.
  useEffect(() => {
    searchApi.forceMergeSearchIndex().catch(() => {});
  }, []);

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Freshmart Agent Search Demo</h1>
        <p className="text-sm text-gray-500 mt-1">
          Semantic vector search with live data hydration from Materialize
        </p>
      </div>
      <VectorPipelineCard defaultExpanded />
    </div>
  );
}
