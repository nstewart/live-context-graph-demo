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
import { WriteTripleForm } from "./WriteTripleForm";

// ── Embedding strip ──────────────────────────────────────────────────────────

const BANDS = 32;

function downsample(vector: number[], bands: number): number[] {
  const chunkSize = Math.floor(vector.length / bands);
  return Array.from({ length: bands }, (_, i) => {
    const slice = vector.slice(i * chunkSize, (i + 1) * chunkSize);
    return slice.reduce((a, b) => a + b, 0) / slice.length;
  });
}

const EmbeddingStrip = ({ vector, flashing, height = 16 }: { vector: number[]; flashing?: boolean; height?: number }) => {
  if (!vector || vector.length < BANDS) {
    return <span className="text-xs text-gray-400 italic">—</span>;
  }
  const samples = downsample(vector, BANDS);
  const min = Math.min(...samples);
  const max = Math.max(...samples);
  const range = max - min || 1;
  return (
    <div
      className={`w-full rounded overflow-hidden transition-all duration-300 ${flashing ? "ring-2 ring-yellow-400 shadow-[0_0_12px_3px_rgba(250,204,21,0.5)]" : ""}`}
      title={`384-dim embedding (${BANDS} bands shown)`}
    >
      <div className="flex w-full">
        {samples.map((v, i) => {
          const t = (v - min) / range;
          const hue = Math.round(240 - t * 240);
          const lightness = Math.round(70 - t * 40);
          return (
            <div
              key={i}
              style={{ flex: 1, height, backgroundColor: `hsl(${hue}, 65%, ${lightness}%)` }}
            />
          );
        })}
      </div>
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

// ── Compact result card ───────────────────────────────────────────────────────

interface ResultCardProps {
  result: VectorSearchResult;
  rank: number;
  flashedRows: Set<number>;
  embeddingFlashing: boolean;
}

const ResultCard = ({ result, rank: _rank, flashedRows, embeddingFlashing }: ResultCardProps) => (
  <div className="space-y-1.5">
    {/* Header row */}
    <div className="flex items-center gap-2 flex-wrap">
      <span className="font-semibold text-gray-900 text-sm">#{result.order_number ?? result.order_id}</span>
      {result.order_status && (
        <span className={`px-1.5 py-0.5 text-xs font-medium rounded border ${getStatusClasses(result.order_status)}`}>
          {result.order_status}
        </span>
      )}
      <span className="text-xs text-gray-500 truncate">
        {[result.customer_name, result.store_name && `${result.store_name}${result.store_zone ? ` (${result.store_zone})` : ""}`]
          .filter(Boolean).join(" · ")}
      </span>
      <span className="ml-auto text-xs text-purple-700 font-semibold whitespace-nowrap">
        {(result.score * 100).toFixed(1)}% match
      </span>
    </div>

    {/* Embedding strip + text */}
    <div className="flex items-center gap-2">
      <div className="flex-1">
        <EmbeddingStrip vector={result.embedding} flashing={embeddingFlashing} height={12} />
      </div>
      <span className="text-xs text-gray-400 font-mono whitespace-nowrap flex-shrink-0">
        {embeddingFlashing
          ? <span className="text-yellow-600 font-semibold animate-pulse">↻ re-embedded</span>
          : `emb ${fmtTime(result.embedded_at)}`}
      </span>
    </div>
    {result.embedding_text && (
      <code className="block bg-gray-100 text-xs font-mono text-gray-600 px-2 py-1 rounded break-words leading-relaxed">
        {result.embedding_text}
      </code>
    )}

    {/* Line items */}
    {result.line_items && result.line_items.length > 0 && (
      <div className="overflow-x-auto">
        <table className="w-full border-collapse" style={{ fontSize: "11px" }}>
          <thead>
            <tr className="text-left text-gray-400 border-b border-gray-100">
              <th className="pb-0.5 pr-2 font-medium">Product</th>
              <th className="pb-0.5 pr-2 font-medium">Cat</th>
              <th className="pb-0.5 pr-2 font-medium text-right">Qty</th>
              <th className="pb-0.5 pr-2 font-medium text-right">Live $</th>
              <th className="pb-0.5 font-medium whitespace-nowrap">Updated</th>
            </tr>
          </thead>
          <tbody>
            {result.line_items.map((item: VectorLineItem, idx: number) => {
              const priceUp   = item.live_price != null && item.base_price != null && Number(item.live_price) > Number(item.base_price);
              const priceDown = item.live_price != null && item.base_price != null && Number(item.live_price) < Number(item.base_price);
              return (
                <tr
                  key={idx}
                  className="border-b border-gray-100 last:border-0 transition-colors duration-300"
                  style={flashedRows.has(idx) ? { backgroundColor: "#fef9c3" } : undefined}
                >
                  <td className="py-0.5 pr-2 max-w-[120px]">
                    <div className="font-medium text-gray-800 truncate">
                      {item.perishable_flag && <span className="text-orange-400 mr-0.5" title="Perishable">⚡</span>}
                      {item.product_name ?? "—"}
                      {item.product_id && <span className="ml-1 text-gray-400 font-normal">({item.product_id})</span>}
                    </div>
                    {item.line_id && (
                      <div className="text-gray-400 font-mono truncate" style={{ fontSize: "9px" }}>{item.line_id}</div>
                    )}
                  </td>
                  <td className="py-0.5 pr-2 text-gray-500 whitespace-nowrap">{item.category ?? "—"}</td>
                  <td className="py-0.5 pr-2 text-right text-gray-700">{item.quantity ?? "—"}</td>
                  <td className="py-0.5 pr-2 text-right font-medium whitespace-nowrap">
                    {item.base_price != null && item.live_price != null && Number(item.live_price) !== Number(item.base_price) && (
                      <span className="line-through text-gray-400 mr-1">${Number(item.base_price).toFixed(2)}</span>
                    )}
                    <span className={priceUp ? "text-red-600" : priceDown ? "text-green-600" : "text-gray-800"}>
                      ${Number(item.live_price ?? item.unit_price ?? 0).toFixed(2)}
                    </span>
                  </td>
                  <td className="py-0.5 text-gray-400 whitespace-nowrap font-mono">{fmtTime(result.effective_updated_at)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    )}

    {/* Footer */}
    <div className="flex items-center gap-1.5">
      {result.order_total_amount != null && (
        <span className="text-xs text-gray-500">Total: ${parseFloat(String(result.order_total_amount)).toFixed(2)}</span>
      )}
      <span className="text-xs text-gray-400 ml-auto">{fmtAgo(result.effective_updated_at)}</span>
    </div>
  </div>
);

// ── Main component ────────────────────────────────────────────────────────────

export const VectorPipelineCard = () => {
  const [isExpanded, setIsExpanded]         = useState(false);
  const [searchQuery, setSearchQuery]       = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [isSearching, setIsSearching]       = useState(false);
  const [searchError, setSearchError]       = useState<string | null>(null);
  const [results, setResults]               = useState<VectorSearchResult[]>([]);
  const [hasSearched, setHasSearched]       = useState(false);
  const [flashedRowsByResult, setFlashedRowsByResult] = useState<Record<number, Set<number>>>({});
  const [flashedEmbeddings, setFlashedEmbeddings]     = useState<Set<number>>(new Set());
  const [lastRefresh, setLastRefresh]       = useState<Date | null>(null);

  // Keyed by order_id so they survive result reordering
  const prevPricesRef     = useRef<Record<string, Record<number, number>>>({});
  const prevEmbeddedAtRef = useRef<Record<string, string | null | undefined>>({});
  const refreshTimerRef   = useRef<ReturnType<typeof setInterval> | null>(null);

  const applyResults = useCallback((newResults: VectorSearchResult[]) => {
    const newFlashedRows: Record<number, Set<number>> = {};
    const newFlashedEmbeddings = new Set<number>();

    newResults.forEach((result, resultIdx) => {
      const id = result.order_id;
      const prevPrices = prevPricesRef.current[id] ?? {};
      const rowFlash = new Set<number>();

      (result.line_items ?? []).forEach((item, lineIdx) => {
        const prev = prevPrices[lineIdx];
        const curr = item.live_price ?? item.unit_price ?? 0;
        if (prev !== undefined && prev !== curr) rowFlash.add(lineIdx);
        prevPrices[lineIdx] = curr;
      });
      prevPricesRef.current[id] = prevPrices;
      if (rowFlash.size > 0) newFlashedRows[resultIdx] = rowFlash;

      const prevEmb = prevEmbeddedAtRef.current[id];
      if (prevEmb !== undefined && prevEmb !== result.embedded_at) newFlashedEmbeddings.add(resultIdx);
      prevEmbeddedAtRef.current[id] = result.embedded_at;
    });

    setResults(newResults);
    setLastRefresh(new Date());

    if (Object.keys(newFlashedRows).length > 0) {
      setFlashedRowsByResult(newFlashedRows);
      setTimeout(() => setFlashedRowsByResult({}), 1200);
    }
    if (newFlashedEmbeddings.size > 0) {
      setFlashedEmbeddings(newFlashedEmbeddings);
      setTimeout(() => setFlashedEmbeddings(new Set()), 2000);
    }
  }, []);

  const executeSearch = useCallback(async (query: string, silent = false) => {
    if (!query) {
      setResults([]); setSearchError(null); setSubmittedQuery(""); setHasSearched(false);
      return;
    }
    if (!silent) { setIsSearching(true); setSearchError(null); setSubmittedQuery(query); setHasSearched(true); }
    try {
      const response = await searchApi.vectorSearchOrders(query, 3);
      applyResults(response.data.results ?? []);
    } catch (err) {
      if (!silent) {
        console.error("Vector search failed:", err);
        setSearchError("Vector search unavailable. Ensure OpenSearch and the embedding service are running.");
        setResults([]);
      }
    } finally {
      if (!silent) setIsSearching(false);
    }
  }, [applyResults]);

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
              <span className="text-sm font-medium text-gray-700">Semantic Search</span>
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

          {/* Write a Triple */}
          <div className="mb-4">
            <WriteTripleForm />
          </div>

          {/* Two-column layout */}
          <div className="grid grid-cols-1 lg:grid-cols-[280px_1fr] gap-4">
            {/* Left: How it works */}
            <div className="border rounded-lg overflow-hidden">
              <div className="bg-gray-50 px-4 py-2 border-b">
                <span className="text-sm font-medium text-gray-700">How it works</span>
              </div>
              <div className="p-3">
                <ol className="flex flex-col gap-0">
                  {STEPS.map((step, idx) => {
                    const c = STEP_COLORS[step.color];
                    const Icon = step.icon;
                    return (
                      <li key={step.label} className="flex flex-col">
                        <div className={`flex items-center gap-2 px-2 py-1.5 rounded border ${c.bg} ${c.border}`}>
                          <div className={`flex-shrink-0 w-6 h-6 rounded-full flex items-center justify-center ${c.icon}`}>
                            <Icon className="h-3 w-3" />
                          </div>
                          <div className="flex items-baseline gap-1.5 min-w-0">
                            <span className="text-xs font-mono text-gray-400">{idx + 1}.</span>
                            <span className={`text-xs font-semibold ${c.text}`}>{step.label}</span>
                            <span className="text-xs text-gray-500 truncate">{step.detail}</span>
                          </div>
                        </div>
                        {idx < STEPS.length - 1 && (
                          <div className="flex justify-center py-0.5">
                            <ArrowRight className="h-3 w-3 text-gray-300 rotate-90" />
                          </div>
                        )}
                      </li>
                    );
                  })}
                </ol>
              </div>
            </div>

            {/* Right: Live order results */}
            <div className="border rounded-lg overflow-hidden">
              <div className="bg-gray-50 px-4 py-2 border-b flex items-center justify-between">
                <span className="text-sm font-medium text-gray-700">
                  Live order results
                  {results.length > 0 && <span className="ml-1.5 text-xs text-gray-400 font-normal">top {results.length} by relevance</span>}
                </span>
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
                  <div className="text-sm text-gray-400 py-8 text-center italic">Enter a query to see live results...</div>
                ) : results.length === 0 ? (
                  <div className="text-sm text-gray-500 py-8 text-center">No results found.</div>
                ) : (
                  <div className="divide-y divide-gray-100">
                    {results.map((result, idx) => (
                      <div key={result.order_id} className={idx > 0 ? "pt-3 mt-3" : ""}>
                        <ResultCard
                          result={result}
                          rank={idx + 1}
                          flashedRows={flashedRowsByResult[idx] ?? new Set()}
                          embeddingFlashing={flashedEmbeddings.has(idx)}
                        />
                      </div>
                    ))}
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
