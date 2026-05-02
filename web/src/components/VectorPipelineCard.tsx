import { useState, useCallback, useEffect, useRef } from "react";
import {
  ChevronDown,
  ChevronRight,
  Search,
  Zap,
  Database,
  ArrowRight,
  RefreshCw,
} from "lucide-react";
import { searchApi, VectorSearchResult, VectorLineItem } from "../api/client";

// ── Embedding strip ──────────────────────────────────────────────────────────
// Downsample a 384-dim vector to `bands` colour blocks and render them as an
// inline strip.  Each block maps a normalised float value to an HSL shade so
// the strip changes perceptibly when ANY product in the order changes.

const BANDS = 32;

function downsample(vector: number[], bands: number): number[] {
  const chunkSize = Math.floor(vector.length / bands);
  return Array.from({ length: bands }, (_, i) => {
    const slice = vector.slice(i * chunkSize, (i + 1) * chunkSize);
    return slice.reduce((a, b) => a + b, 0) / slice.length;
  });
}

const EmbeddingStrip = ({ vector }: { vector: number[] }) => {
  if (!vector || vector.length < BANDS) {
    return <span className="text-xs text-gray-400 italic">—</span>;
  }
  const samples = downsample(vector, BANDS);
  const min = Math.min(...samples);
  const max = Math.max(...samples);
  const range = max - min || 1;
  return (
    <div className="flex gap-px items-center" title={`384-dim embedding (${BANDS} bands shown)`}>
      {samples.map((v, i) => {
        const t = (v - min) / range; // 0 = min, 1 = max
        // hue: 240 (indigo/low) → 0 (red/high), lightness 70 → 30
        const hue = Math.round(240 - t * 240);
        const lightness = Math.round(70 - t * 40);
        return (
          <div
            key={i}
            style={{ width: 3, height: 14, backgroundColor: `hsl(${hue}, 65%, ${lightness}%)` }}
          />
        );
      })}
    </div>
  );
};

// ── Helpers ──────────────────────────────────────────────────────────────────

const STATUS_BADGE_CLASSES: Record<string, string> = {
  OUT_FOR_DELIVERY: "bg-blue-100 text-blue-800 border-blue-300",
  PICKING: "bg-yellow-100 text-yellow-800 border-yellow-300",
  CREATED: "bg-gray-100 text-gray-800 border-gray-300",
  DELIVERED: "bg-green-100 text-green-800 border-green-300",
};

const getStatusClasses = (status?: string) =>
  STATUS_BADGE_CLASSES[status ?? ""] ?? "bg-gray-100 text-gray-800 border-gray-300";

const fmtTime = (iso?: string | null): string => {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
};

const fmtAgo = (iso?: string | null): string => {
  if (!iso) return "just now";
  const sec = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  if (sec < 2) return "just now";
  if (sec < 60) return `${sec}s ago`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m ago`;
  return `${Math.floor(sec / 3600)}h ago`;
};

// ── Architecture steps ───────────────────────────────────────────────────────

type StepColor = "purple" | "blue" | "green" | "orange";

const STEPS = [
  { label: "Embed query",    detail: "BAAI/bge-small-en-v1.5 (384-dim)",    color: "purple" as StepColor, icon: Zap },
  { label: "knn_search",     detail: "OpenSearch returns top-N order IDs",   color: "blue"   as StepColor, icon: Search },
  { label: "Hydrate",        detail: "Materialize: live status, price, ETA", color: "green"  as StepColor, icon: Database },
  { label: "Merge & return", detail: "Enriched result to agent",             color: "orange" as StepColor, icon: ArrowRight },
];

const STEP_COLORS: Record<StepColor, { bg: string; text: string; border: string; icon: string }> = {
  purple: { bg: "bg-purple-50", text: "text-purple-700", border: "border-purple-200", icon: "bg-purple-100 text-purple-600" },
  blue:   { bg: "bg-blue-50",   text: "text-blue-700",   border: "border-blue-200",   icon: "bg-blue-100 text-blue-600" },
  green:  { bg: "bg-green-50",  text: "text-green-700",  border: "border-green-200",  icon: "bg-green-100 text-green-600" },
  orange: { bg: "bg-orange-50", text: "text-orange-700", border: "border-orange-200", icon: "bg-orange-100 text-orange-600" },
};

// ── Main component ────────────────────────────────────────────────────────────

export const VectorPipelineCard = () => {
  const [isExpanded, setIsExpanded]     = useState(false);
  const [searchQuery, setSearchQuery]   = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [isSearching, setIsSearching]   = useState(false);
  const [searchError, setSearchError]   = useState<string | null>(null);
  const [topResult, setTopResult]       = useState<VectorSearchResult | null>(null);
  const [hasSearched, setHasSearched]   = useState(false);
  // Per-line-item flash: set of line_ids (or indices) that changed on last refresh
  const [flashedRows, setFlashedRows]   = useState<Set<number>>(new Set());
  const [lastRefresh, setLastRefresh]   = useState<Date | null>(null);
  const prevPricesRef = useRef<Record<number, number>>({});
  const refreshTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const applyResult = useCallback((result: VectorSearchResult | null) => {
    if (!result) { setTopResult(null); return; }

    // Detect which rows changed price since last refresh
    const newFlashed = new Set<number>();
    (result.line_items ?? []).forEach((item, idx) => {
      const prev = prevPricesRef.current[idx];
      const curr = item.live_price ?? item.unit_price ?? 0;
      if (prev !== undefined && prev !== curr) newFlashed.add(idx);
      prevPricesRef.current[idx] = curr;
    });

    setTopResult(result);
    setLastRefresh(new Date());
    if (newFlashed.size > 0) {
      setFlashedRows(newFlashed);
      setTimeout(() => setFlashedRows(new Set()), 1200);
    }
  }, []);

  const executeSearch = useCallback(async (query: string, silent = false) => {
    if (!query) {
      setTopResult(null); setSearchError(null); setSubmittedQuery(""); setHasSearched(false);
      return;
    }
    if (!silent) { setIsSearching(true); setSearchError(null); setSubmittedQuery(query); setHasSearched(true); }
    try {
      const response = await searchApi.vectorSearchOrders(query, 3);
      applyResult(response.data.results[0] ?? null);
    } catch (err) {
      if (!silent) {
        console.error("Vector search failed:", err);
        setSearchError("Vector search unavailable. Ensure OpenSearch and the embedding service are running.");
        setTopResult(null);
      }
    } finally {
      if (!silent) setIsSearching(false);
    }
  }, [applyResult]);

  // Auto-refresh every 5s after a successful search
  useEffect(() => {
    if (refreshTimerRef.current) clearInterval(refreshTimerRef.current);
    if (!submittedQuery) return;
    refreshTimerRef.current = setInterval(() => {
      executeSearch(submittedQuery, true);
    }, 5000);
    return () => { if (refreshTimerRef.current) clearInterval(refreshTimerRef.current); };
  }, [submittedQuery, executeSearch]);

  const performSearch = useCallback(() => executeSearch(searchQuery.trim()), [searchQuery, executeSearch]);
  const handleKeyDown = (e: React.KeyboardEvent) => { if (e.key === "Enter") performSearch(); };
  const handleExampleClick = (q: string) => { setSearchQuery(q); executeSearch(q); };

  return (
    <div className="bg-white rounded-lg shadow mb-6">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full p-4 flex items-center justify-between hover:bg-gray-50 transition-colors"
      >
        <div className="flex items-center gap-2">
          {isExpanded ? <ChevronDown className="h-5 w-5 text-gray-500" /> : <ChevronRight className="h-5 w-5 text-gray-500" />}
          <div className="text-left">
            <h3 className="text-lg font-semibold text-gray-900">Vector Pipeline</h3>
            <p className="text-xs text-gray-500">Semantic search + live data hydration from Materialize</p>
          </div>
        </div>
      </button>

      {isExpanded && (
        <div className="px-6 pb-6">
          <div className="mb-4 text-sm text-gray-600 leading-relaxed">
            <p>
              The vector store finds <em>which</em> documents match semantically.
              Materialize provides <em>live data</em> for those documents — always fresh, never stale.
            </p>
          </div>

          {/* Search box */}
          <div className="border rounded-lg overflow-hidden mb-4">
            <div className="bg-gray-50 px-4 py-2 border-b flex items-center gap-2">
              <Search className="h-4 w-4 text-purple-500" />
              <span className="text-sm font-medium text-gray-700">Ask a semantic question</span>
            </div>
            <div className="p-4 space-y-3">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
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
                {["organic produce", "dairy products", "perishable delivery"].map((q, i) => (
                  <span key={q}>
                    {i > 0 && ", "}
                    <button onClick={() => handleExampleClick(q)} className="text-purple-600 hover:underline">{q}</button>
                  </span>
                ))}
              </div>
            </div>
          </div>

          {/* Two-column layout */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {/* Left: How it works */}
            <div className="border rounded-lg overflow-hidden">
              <div className="bg-gray-50 px-4 py-2 border-b">
                <span className="text-sm font-medium text-gray-700">How it works</span>
              </div>
              <div className="p-4">
                <ol className="space-y-2">
                  {STEPS.map((step, idx) => {
                    const c = STEP_COLORS[step.color];
                    const Icon = step.icon;
                    return (
                      <li key={step.label}>
                        <div className={`flex items-start gap-3 p-3 rounded-md border ${c.bg} ${c.border}`}>
                          <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${c.icon}`}>
                            <Icon className="h-4 w-4" />
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="text-xs font-mono text-gray-400">{idx + 1}.</span>
                              <span className={`text-sm font-semibold ${c.text}`}>{step.label}</span>
                            </div>
                            <p className="text-xs text-gray-600 mt-1">{step.detail}</p>
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
                <span className="text-sm font-medium text-gray-700">Live order result</span>
                <div className="flex items-center gap-2">
                  {lastRefresh && (
                    <span className="text-xs text-gray-400 flex items-center gap-1">
                      <RefreshCw className="h-3 w-3" />
                      {fmtAgo(lastRefresh.toISOString())}
                    </span>
                  )}
                  {submittedQuery && !isSearching && !searchError && (
                    <span className="text-xs text-gray-500 font-mono truncate max-w-[120px]">"{submittedQuery}"</span>
                  )}
                </div>
              </div>

              <div className="p-4">
                {isSearching ? (
                  <div className="text-sm text-gray-500 py-8 text-center">Searching...</div>
                ) : searchError ? (
                  <div className="text-sm text-red-600 py-8 text-center">{searchError}</div>
                ) : !hasSearched ? (
                  <div className="text-sm text-gray-400 py-8 text-center italic">Enter a query to see a live result...</div>
                ) : !topResult ? (
                  <div className="text-sm text-gray-500 py-8 text-center">No results found.</div>
                ) : (
                  <div className="space-y-3">
                    {/* Order header */}
                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <div className="flex items-center gap-2">
                        <span className="text-base font-bold text-gray-900">
                          #{topResult.order_number ?? topResult.order_id}
                        </span>
                        {topResult.order_status && (
                          <span className={`px-2 py-0.5 text-xs font-medium rounded border ${getStatusClasses(topResult.order_status)}`}>
                            {topResult.order_status}
                          </span>
                        )}
                      </div>
                      <span className="text-xs text-purple-700 font-semibold">
                        {(topResult.score * 100).toFixed(1)}% match
                      </span>
                    </div>

                    {/* Customer + store */}
                    <div className="grid grid-cols-2 gap-x-4 text-sm">
                      {topResult.customer_name && (
                        <div>
                          <span className="text-gray-400 text-xs block">Customer</span>
                          <span className="font-medium text-gray-900">{topResult.customer_name}</span>
                        </div>
                      )}
                      {topResult.store_name && (
                        <div>
                          <span className="text-gray-400 text-xs block">Store</span>
                          <span className="font-medium text-gray-900">
                            {topResult.store_name}
                            {topResult.store_zone && <span className="ml-1 text-xs text-gray-400">({topResult.store_zone})</span>}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Line items table */}
                    {topResult.line_items && topResult.line_items.length > 0 && (
                      <div className="pt-2 border-t border-gray-200">
                        <div className="text-xs text-gray-500 mb-2 flex items-center justify-between">
                          <span>Line items — live from Materialize</span>
                          {topResult.order_total_amount != null && (
                            <span className="font-medium text-gray-700">
                              Total: ${parseFloat(String(topResult.order_total_amount)).toFixed(2)}
                            </span>
                          )}
                        </div>
                        <div className="overflow-x-auto">
                          <table className="w-full text-xs border-collapse">
                            <thead>
                              <tr className="text-left text-gray-400 border-b border-gray-200">
                                <th className="pb-1 pr-2 font-medium">Product</th>
                                <th className="pb-1 pr-2 font-medium">Cat</th>
                                <th className="pb-1 pr-2 font-medium text-right">Qty</th>
                                <th className="pb-1 pr-2 font-medium text-right">Live $</th>
                                <th className="pb-1 pr-2 font-medium">▓▒░ Embedding</th>
                                <th className="pb-1 pr-2 font-medium whitespace-nowrap">Embedded at</th>
                                <th className="pb-1 font-medium whitespace-nowrap">Row updated</th>
                              </tr>
                            </thead>
                            <tbody>
                              {topResult.line_items.map((item: VectorLineItem, idx: number) => {
                                const priceUp   = item.live_price != null && item.base_price != null && Number(item.live_price) > Number(item.base_price);
                                const priceDown = item.live_price != null && item.base_price != null && Number(item.live_price) < Number(item.base_price);
                                const isFlashed = flashedRows.has(idx);
                                return (
                                  <tr
                                    key={idx}
                                    className="border-b border-gray-100 last:border-0 transition-colors duration-300"
                                    style={isFlashed ? { backgroundColor: "#fef9c3" } : undefined}
                                  >
                                    <td className="py-1 pr-2 font-medium text-gray-800 max-w-[90px] truncate">
                                      {item.perishable_flag && <span className="text-orange-400 mr-1" title="Perishable">⚡</span>}
                                      {item.product_name ?? "—"}
                                    </td>
                                    <td className="py-1 pr-2 text-gray-500 whitespace-nowrap">{item.category ?? "—"}</td>
                                    <td className="py-1 pr-2 text-right text-gray-700">{item.quantity ?? "—"}</td>
                                    <td className="py-1 pr-2 text-right font-medium whitespace-nowrap">
                                      {item.base_price != null && item.live_price != null && Number(item.live_price) !== Number(item.base_price) && (
                                        <span className="line-through text-gray-400 mr-1">${Number(item.base_price).toFixed(2)}</span>
                                      )}
                                      <span className={priceUp ? "text-red-600" : priceDown ? "text-green-600" : "text-gray-800"}>
                                        ${Number(item.live_price ?? item.unit_price ?? 0).toFixed(2)}
                                      </span>
                                    </td>
                                    <td className="py-1 pr-2">
                                      <EmbeddingStrip vector={topResult.embedding} />
                                    </td>
                                    <td className="py-1 pr-2 text-gray-500 whitespace-nowrap font-mono">{fmtTime(topResult.embedded_at)}</td>
                                    <td className="py-1 text-gray-500 whitespace-nowrap font-mono">{fmtTime(topResult.effective_updated_at)}</td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    )}

                    {/* Embedding text */}
                    <div className="pt-2 border-t border-gray-200">
                      <div className="text-xs text-gray-500 mb-1">
                        Embedded text <span className="text-gray-400">(384-dim vector)</span>
                      </div>
                      <code className="block bg-gray-100 text-xs font-mono text-gray-700 px-2 py-1.5 rounded break-words leading-relaxed">
                        {topResult.embedding_text}
                      </code>
                    </div>

                    {/* Hydrated label */}
                    <div className="flex items-center gap-2 pt-2 border-t border-gray-200">
                      <Database className="h-3.5 w-3.5 text-green-600" />
                      <span className="text-xs font-medium text-green-700">Hydrated from Materialize</span>
                      <span className="text-xs text-gray-500 ml-auto">{fmtAgo(topResult.effective_updated_at)}</span>
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
