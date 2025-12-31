import { useState, useCallback, useMemo } from "react";
import { ChevronDown, ChevronRight, Search, Database } from "lucide-react";
import { HighlightedJson } from "./HighlightedJson";
import { searchApi, OpenSearchResponse } from "../api/client";

export const AgentNativeReadsCard = () => {
  const [isExpanded, setIsExpanded] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [searchResult, setSearchResult] = useState<OpenSearchResponse | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  // Perform search on submit
  const performSearch = useCallback(async () => {
    const query = searchQuery.trim();
    if (!query) {
      setSearchResult(null);
      setSearchError(null);
      setSubmittedQuery("");
      return;
    }

    setIsSearching(true);
    setSearchError(null);
    setSubmittedQuery(query);

    try {
      const response = await searchApi.searchOrders(query, 3);
      setSearchResult(response.data);
    } catch (error) {
      console.error("Search failed:", error);
      setSearchError("Search unavailable. Ensure OpenSearch is running.");
      setSearchResult(null);
    } finally {
      setIsSearching(false);
    }
  }, [searchQuery]);

  // Handle Enter key
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      performSearch();
    }
  };

  // Handle example query click
  const handleExampleClick = (query: string) => {
    setSearchQuery(query);
    // Trigger search immediately
    setIsSearching(true);
    setSearchError(null);
    setSubmittedQuery(query);
    searchApi.searchOrders(query, 3)
      .then((response) => setSearchResult(response.data))
      .catch((error) => {
        console.error("Search failed:", error);
        setSearchError("Search unavailable. Ensure OpenSearch is running.");
        setSearchResult(null);
      })
      .finally(() => setIsSearching(false));
  };

  // Build the OpenSearch query for display
  const openSearchQuery = useMemo(() => {
    if (!submittedQuery) return null;
    return {
      query: {
        multi_match: {
          query: submittedQuery,
          fields: ["customer_name^2", "store_name^2", "store_zone", "order_number^3", "order_status"],
          fuzziness: "AUTO",
        },
      },
    };
  }, [submittedQuery]);

  // Get hit count for display
  const hitCount = searchResult?.hits?.total?.value ?? 0;

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
            <h3 className="text-lg font-semibold text-gray-900">Agent-native Reads</h3>
            <p className="text-xs text-gray-500">
              How agents discover information through always-fresh search indexes
            </p>
          </div>
        </div>
      </button>

      {isExpanded && (
        <div className="px-6 pb-6">
          {/* Explainer text */}
          <div className="mb-4 text-sm text-gray-600 leading-relaxed space-y-2">
            <p>
              Traditional databases require agents to know exact IDs. Search indexes let agents
              ask questions like "orders from the downtown store" and get answers instantly.
              Materialize keeps the index perfectly fresh&mdash;no stale data, no batch refresh lag.
            </p>
            <p className="text-xs text-gray-500">
              In production, some customers add a vector index for improved semantic search
              and natural language queries.
            </p>
          </div>

          {/* Ask the Search Index */}
          <div className="border rounded-lg overflow-hidden">
            <div className="bg-gray-50 px-4 py-2 border-b">
              <div className="flex items-center gap-2">
                <Search className="h-4 w-4 text-green-500" />
                <span className="text-sm font-medium text-gray-700">
                  Ask the Search Index
                </span>
              </div>
            </div>

            <div className="p-4 space-y-3">
              {/* Search input */}
              <div className="flex gap-2">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Search orders..."
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                />
                <button
                  onClick={performSearch}
                  disabled={isSearching || !searchQuery.trim()}
                  className="px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-md hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  <Search className="h-4 w-4" />
                  Search
                </button>
              </div>

              {/* Example queries */}
              <div className="text-xs text-gray-500">
                Try:{" "}
                <button onClick={() => handleExampleClick("downtown")} className="text-green-600 hover:underline">
                  downtown
                </button>
                ,{" "}
                <button onClick={() => handleExampleClick("john")} className="text-green-600 hover:underline">
                  john
                </button>
                ,{" "}
                <button onClick={() => handleExampleClick("PICKING")} className="text-green-600 hover:underline">
                  PICKING
                </button>
                ,{" "}
                <button onClick={() => handleExampleClick("BKN")} className="text-green-600 hover:underline">
                  BKN
                </button>
              </div>

              {/* Query and Response - side by side */}
              {(openSearchQuery || isSearching || searchError) && (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
                  {/* Query */}
                  {openSearchQuery && (
                    <div className="flex flex-col">
                      <div className="flex items-center gap-2 mb-2">
                        <Database className="h-4 w-4 text-blue-500" />
                        <span className="text-xs font-medium text-gray-600">
                          GET /orders/_search
                        </span>
                      </div>
                      <div className="bg-gray-900 rounded-lg p-3 flex-1 overflow-auto max-h-[350px]">
                        <HighlightedJson data={openSearchQuery} />
                      </div>
                    </div>
                  )}

                  {/* Response */}
                  <div className="flex flex-col">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-xs font-medium text-gray-600">
                        Response
                      </span>
                      <span className="text-xs text-gray-500">
                        {isSearching
                          ? "Searching..."
                          : searchError
                          ? "Error"
                          : `${hitCount} hit${hitCount !== 1 ? "s" : ""}`}
                      </span>
                    </div>
                    <div className="bg-gray-900 rounded-lg p-3 flex-1 overflow-auto max-h-[350px]">
                      {searchError ? (
                        <pre className="text-xs font-mono text-red-400">{searchError}</pre>
                      ) : isSearching ? (
                        <pre className="text-xs font-mono text-gray-500">Loading...</pre>
                      ) : searchResult ? (
                        <HighlightedJson data={searchResult} />
                      ) : (
                        <pre className="text-xs font-mono text-gray-500">
                          Enter a search query to see results...
                        </pre>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AgentNativeReadsCard;
