import { useState, useCallback } from "react";
import {
  ChevronDown,
  ChevronRight,
  Search,
  Zap,
  Database,
  ArrowRight,
} from "lucide-react";
import { searchApi, VectorSearchResult } from "../api/client";

type StepColor = "purple" | "blue" | "green" | "orange";

interface Step {
  label: string;
  detail: string;
  icon: React.ComponentType<{ className?: string }>;
  color: StepColor;
}

const STEPS: Step[] = [
  {
    label: "Embed query",
    detail: "BAAI/bge-small-en-v1.5 (384-dim)",
    icon: Zap,
    color: "purple",
  },
  {
    label: "knn_search",
    detail: "OpenSearch finds similar order IDs",
    icon: Search,
    color: "blue",
  },
  {
    label: "Hydrate",
    detail: "Materialize: live status, price, ETA",
    icon: Database,
    color: "green",
  },
  {
    label: "Merge & return",
    detail: "Enriched result to agent",
    icon: ArrowRight,
    color: "orange",
  },
];

const STEP_COLOR_CLASSES: Record<
  StepColor,
  { bg: string; text: string; border: string; iconBg: string }
> = {
  purple: {
    bg: "bg-purple-50",
    text: "text-purple-700",
    border: "border-purple-200",
    iconBg: "bg-purple-100 text-purple-600",
  },
  blue: {
    bg: "bg-blue-50",
    text: "text-blue-700",
    border: "border-blue-200",
    iconBg: "bg-blue-100 text-blue-600",
  },
  green: {
    bg: "bg-green-50",
    text: "text-green-700",
    border: "border-green-200",
    iconBg: "bg-green-100 text-green-600",
  },
  orange: {
    bg: "bg-orange-50",
    text: "text-orange-700",
    border: "border-orange-200",
    iconBg: "bg-orange-100 text-orange-600",
  },
};

const STATUS_BADGE_CLASSES: Record<string, string> = {
  OUT_FOR_DELIVERY: "bg-blue-100 text-blue-800 border-blue-300",
  PICKING: "bg-yellow-100 text-yellow-800 border-yellow-300",
  CREATED: "bg-gray-100 text-gray-800 border-gray-300",
  DELIVERED: "bg-green-100 text-green-800 border-green-300",
};

const getStatusClasses = (status?: string): string => {
  if (!status) return "bg-gray-100 text-gray-800 border-gray-300";
  return (
    STATUS_BADGE_CLASSES[status] || "bg-gray-100 text-gray-800 border-gray-300"
  );
};

const formatTimeAgo = (timestamp?: string): string => {
  if (!timestamp) return "just now";
  const then = new Date(timestamp).getTime();
  if (Number.isNaN(then)) return "just now";
  const diffSec = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (diffSec < 2) return "just now";
  if (diffSec < 60) return `${diffSec}s ago`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}m ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr}h ago`;
  return `${Math.floor(diffHr / 24)}d ago`;
};

export const VectorPipelineCard = () => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [topResult, setTopResult] = useState<VectorSearchResult | null>(null);
  const [hasSearched, setHasSearched] = useState(false);

  const executeSearch = useCallback(async (query: string) => {
    if (!query) {
      setTopResult(null);
      setSearchError(null);
      setSubmittedQuery("");
      setHasSearched(false);
      return;
    }

    setIsSearching(true);
    setSearchError(null);
    setSubmittedQuery(query);
    setHasSearched(true);

    try {
      const response = await searchApi.vectorSearchOrders(query, 3);
      const first = response.data.results[0] ?? null;
      setTopResult(first);
    } catch (error) {
      console.error("Vector search failed:", error);
      setSearchError(
        "Vector search unavailable. Ensure OpenSearch and the embedding service are running."
      );
      setTopResult(null);
    } finally {
      setIsSearching(false);
    }
  }, []);

  const performSearch = useCallback(async () => {
    const query = searchQuery.trim();
    await executeSearch(query);
  }, [searchQuery, executeSearch]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      performSearch();
    }
  };

  const handleExampleClick = (query: string) => {
    setSearchQuery(query);
    executeSearch(query);
  };

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
            <h3 className="text-lg font-semibold text-gray-900">
              Vector Pipeline
            </h3>
            <p className="text-xs text-gray-500">
              Semantic search + live data hydration from Materialize
            </p>
          </div>
        </div>
      </button>

      {isExpanded && (
        <div className="px-6 pb-6">
          <div className="mb-4 text-sm text-gray-600 leading-relaxed">
            <p>
              The vector store finds <em>which</em> documents match the
              question semantically. Materialize provides <em>live data</em>{" "}
              for those documents&mdash;always fresh, never stale.
            </p>
          </div>

          {/* Search input */}
          <div className="border rounded-lg overflow-hidden mb-4">
            <div className="bg-gray-50 px-4 py-2 border-b">
              <div className="flex items-center gap-2">
                <Search className="h-4 w-4 text-purple-500" />
                <span className="text-sm font-medium text-gray-700">
                  Ask a semantic question
                </span>
              </div>
            </div>
            <div className="p-4 space-y-3">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Search by meaning (e.g., dairy products)..."
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                />
                <button
                  onClick={performSearch}
                  disabled={isSearching || !searchQuery.trim()}
                  className="px-4 py-2 bg-purple-600 text-white text-sm font-medium rounded-md hover:bg-purple-700 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  <Search className="h-4 w-4" />
                  Search
                </button>
              </div>

              <div className="text-xs text-gray-500">
                Try:{" "}
                <button
                  onClick={() => handleExampleClick("organic produce")}
                  className="text-purple-600 hover:underline"
                >
                  organic produce
                </button>
                ,{" "}
                <button
                  onClick={() => handleExampleClick("dairy products")}
                  className="text-purple-600 hover:underline"
                >
                  dairy products
                </button>
                ,{" "}
                <button
                  onClick={() => handleExampleClick("perishable delivery")}
                  className="text-purple-600 hover:underline"
                >
                  perishable delivery
                </button>
              </div>
            </div>
          </div>

          {/* Two-column layout */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Left: How it works */}
            <div className="border rounded-lg overflow-hidden">
              <div className="bg-gray-50 px-4 py-2 border-b">
                <span className="text-sm font-medium text-gray-700">
                  How it works
                </span>
              </div>
              <div className="p-4">
                <ol className="space-y-2">
                  {STEPS.map((step, idx) => {
                    const Icon = step.icon;
                    const colors = STEP_COLOR_CLASSES[step.color];
                    return (
                      <li key={step.label}>
                        <div
                          className={`flex items-start gap-3 p-3 rounded-md border ${colors.bg} ${colors.border}`}
                        >
                          <div
                            className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${colors.iconBg}`}
                          >
                            <Icon className="h-4 w-4" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-mono text-gray-400">
                                {idx + 1}.
                              </span>
                              <span
                                className={`text-sm font-semibold ${colors.text}`}
                              >
                                {step.label}
                              </span>
                            </div>
                            <p className="text-xs text-gray-600 mt-1">
                              {step.detail}
                            </p>
                          </div>
                        </div>
                        {idx < STEPS.length - 1 && (
                          <div className="flex justify-center py-1">
                            <ArrowRight className="h-4 w-4 text-gray-400 rotate-90" />
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ol>
              </div>
            </div>

            {/* Right: Live order result */}
            <div className="border rounded-lg overflow-hidden">
              <div className="bg-gray-50 px-4 py-2 border-b flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700">
                  Live order result
                </span>
                {submittedQuery && !isSearching && !searchError && (
                  <span className="text-xs text-gray-500 font-mono truncate max-w-[60%]">
                    "{submittedQuery}"
                  </span>
                )}
              </div>
              <div className="p-4">
                {isSearching ? (
                  <div className="text-sm text-gray-500 py-8 text-center">
                    Searching...
                  </div>
                ) : searchError ? (
                  <div className="text-sm text-red-600 py-8 text-center">
                    {searchError}
                  </div>
                ) : !hasSearched ? (
                  <div className="text-sm text-gray-400 py-8 text-center italic">
                    Enter a query to see a live result...
                  </div>
                ) : !topResult ? (
                  <div className="text-sm text-gray-500 py-8 text-center">
                    No results found.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {/* Order header */}
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-base font-bold text-gray-900">
                          {topResult.order_number
                            ? `#${topResult.order_number}`
                            : topResult.order_id}
                        </span>
                        {topResult.order_status && (
                          <span
                            className={`px-2 py-0.5 text-xs font-medium rounded border ${getStatusClasses(
                              topResult.order_status
                            )}`}
                          >
                            {topResult.order_status}
                          </span>
                        )}
                      </div>
                      <span className="text-xs text-purple-700 font-semibold">
                        {(topResult.score * 100).toFixed(1)}% match
                      </span>
                    </div>

                    {/* Customer */}
                    {topResult.customer_name && (
                      <div className="text-sm">
                        <span className="text-gray-500">Customer: </span>
                        <span className="font-medium text-gray-900">
                          {topResult.customer_name}
                        </span>
                      </div>
                    )}

                    {/* Store + zone */}
                    {(topResult.store_name || topResult.store_zone) && (
                      <div className="text-sm">
                        <span className="text-gray-500">Store: </span>
                        <span className="font-medium text-gray-900">
                          {topResult.store_name}
                          {topResult.store_zone &&
                            ` (${topResult.store_zone})`}
                        </span>
                      </div>
                    )}

                    {/* Total */}
                    {typeof topResult.order_total_amount === "number" && (
                      <div className="text-sm">
                        <span className="text-gray-500">Total: </span>
                        <span className="font-medium text-gray-900">
                          ${topResult.order_total_amount.toFixed(2)}
                        </span>
                      </div>
                    )}

                    {/* Embedding text */}
                    <div className="pt-2 border-t border-gray-200">
                      <div className="text-xs text-gray-500 mb-1">
                        Embedded text
                      </div>
                      <code className="block bg-gray-100 text-xs font-mono text-gray-800 px-2 py-1.5 rounded break-words">
                        {topResult.embedding_text}
                      </code>
                    </div>

                    {/* Hydrated label */}
                    <div className="flex items-center gap-2 pt-2 border-t border-gray-200">
                      <Database className="h-3.5 w-3.5 text-green-600" />
                      <span className="text-xs font-medium text-green-700">
                        Hydrated from Materialize
                      </span>
                      <span className="text-xs text-gray-500 ml-auto">
                        {formatTimeAgo(topResult.effective_updated_at)}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default VectorPipelineCard;
