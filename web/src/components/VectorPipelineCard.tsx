import { useState, useCallback, useEffect, useRef } from "react";
import {
  ChevronDown,
  ChevronRight,
  Search,
  RefreshCw,
} from "lucide-react";
import { searchApi, VectorSearchResult, VectorLineItem } from "../api/client";
import { WriteTripleForm } from "./WriteTripleForm";
import { SearchIndexUpdates } from "./SearchIndexUpdates";
import { RerankComparison } from "./RerankComparison";
import { copy, Entity, enumLabel, enumOptions, placeholder, searchQueries } from '../label'
const vp = copy("vector_pipeline");

// ── Embedding fingerprint ─────────────────────────────────────────────────────

function embeddingFingerprint(vector: number[]): string {
  if (!vector || vector.length < 8) return '—';
  return vector.slice(0, 12)
    .map(v => Math.round(((v + 1) / 2) * 255) & 0xff)
    .map(b => b.toString(16).padStart(2, '0'))
    .join(' ') + '…';
}

const EmbeddingStrip = ({ vector, flashing }: { vector: number[]; flashing?: boolean; height?: number }) => {
  const fp = embeddingFingerprint(vector);
  return (
    <span
      className={`font-mono text-xs flex-1 transition-all duration-300 ${flashing ? "text-yellow-400 font-semibold" : "text-gray-400"}`}
      title="384-dim embedding vector (first 12 values as hex)"
    >
      {fp}
    </span>
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

// ── Compact result card ───────────────────────────────────────────────────────

interface ResultCardProps {
  result: VectorSearchResult;
  rank: number;
  flashedRows: Set<number>;
  embeddingFlashing: boolean;
  statusFlashing: boolean;
  onSelectSubject?: (id: string) => void;
}

const ResultCard = ({ result, rank: _rank, flashedRows, embeddingFlashing, statusFlashing, onSelectSubject }: ResultCardProps) => (
  <div className="space-y-1.5">
    {/* Header row */}
    <div className="flex items-center gap-2 flex-wrap">
      <span className="font-semibold text-gray-900 text-sm">#{result.order_number ?? result.order_id}</span>
      {result.order_status && (
        /* Ring sits over the status colors so DELIVERED stays green while it pulses */
        <span
          data-testid="order-status"
          data-flashing={statusFlashing || undefined}
          className={`px-1.5 py-0.5 text-xs font-medium rounded border transition-all duration-300 ${getStatusClasses(result.order_status)} ${
            statusFlashing
              ? "ring-2 ring-yellow-400 shadow-[0_0_10px_2px_rgba(250,204,21,0.4)] animate-pulse"
              : ""
          }`}
        >
          {enumLabel('order_status', result.order_status)}
        </span>
      )}
      <span className="text-xs text-gray-500 truncate">
        {[result.customer_name, result.store_name && `${result.store_name}${result.store_zone ? ` (${enumLabel('zone', result.store_zone)})` : ""}`]
          .filter(Boolean).join(" · ")}
      </span>
      <button
        onClick={() => onSelectSubject?.(result.order_id)}
        className="font-mono text-xs text-gray-400 hover:text-purple-600 hover:bg-purple-50 px-1.5 py-0.5 rounded border border-transparent hover:border-purple-200 transition-colors whitespace-nowrap"
        title="Fill into Write Triple subject"
      >
        {result.order_id}
      </button>
      <span className="ml-auto text-xs text-purple-700 font-semibold whitespace-nowrap">
        {(result.score * 100).toFixed(1)}% match
      </span>
    </div>

    {/* Embedding fingerprint bar */}
    <div className={`flex items-center gap-2 bg-gray-900 rounded px-2 py-1 transition-all duration-300 ${embeddingFlashing ? "ring-2 ring-yellow-400 shadow-[0_0_10px_2px_rgba(250,204,21,0.4)]" : ""}`}>
      <span className="text-xs font-medium text-gray-500 whitespace-nowrap flex-shrink-0">emb</span>
      <EmbeddingStrip vector={result.embedding} flashing={embeddingFlashing} />
      <span className="text-xs text-gray-500 font-mono whitespace-nowrap flex-shrink-0">
        {embeddingFlashing
          ? <span className="text-yellow-400 font-semibold animate-pulse">↻ re-embedded</span>
          : fmtTime(result.embedded_at)}
      </span>
    </div>
    {result.embedding_text && (
      <code className={`block text-xs font-mono px-2 py-1 rounded break-words leading-relaxed transition-all duration-300 ${embeddingFlashing ? "bg-yellow-950 text-yellow-300 ring-2 ring-yellow-400 shadow-[0_0_10px_2px_rgba(250,204,21,0.4)]" : "bg-gray-100 text-gray-600"}`}>
        {result.embedding_text}
      </code>
    )}

    {/* Line items */}
    {result.line_items && result.line_items.length > 0 && (
      <div className="overflow-x-auto">
        <table className="w-full border-collapse" style={{ fontSize: "11px" }}>
          <thead>
            <tr className="text-left text-gray-400 border-b border-gray-100">
              <th className="pb-0.5 pr-2 font-medium">{Entity('product')}</th>
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

// Explicit searches show the top few by relevance; the silent value-refresh
// re-queries a much wider window so it can still find (and update) a pinned
// order that has fallen in rank. Kept ≤ MAX_SEARCH_LIMIT on the API.
const EXPLICIT_SEARCH_LIMIT = 5;
const REFRESH_SEARCH_LIMIT = 50;
const MIN_SCORE = 0.6;

export const VectorPipelineCard = ({ defaultExpanded = false }: { defaultExpanded?: boolean }) => {
  const [isExpanded, setIsExpanded]         = useState(defaultExpanded);
  const [searchQuery, setSearchQuery]       = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [isSearching, setIsSearching]       = useState(false);
  const [searchError, setSearchError]       = useState<string | null>(null);
  const [results, setResults]               = useState<VectorSearchResult[]>([]);
  const [hasSearched, setHasSearched]       = useState(false);
  const [flashedRowsByResult, setFlashedRowsByResult] = useState<Record<number, Set<number>>>({});
  const [flashedEmbeddings, setFlashedEmbeddings]     = useState<Set<number>>(new Set());
  const [flashedStatuses, setFlashedStatuses]         = useState<Set<number>>(new Set());
  const [lastRefresh, setLastRefresh]       = useState<Date | null>(null);
  const [writeSubject, setWriteSubject]     = useState("");
  const [writeTrigger, setWriteTrigger]     = useState<{ mzLowerBound: number; wallClock: number } | null>(null);
  const [filterZone, setFilterZone]         = useState("");
  const [filterStatus, setFilterStatus]     = useState("");

  // Keyed by order_id so they survive result reordering. Holds a per-line
  // signature of every field the row displays (name, category, qty, price) so a
  // change to ANY of them flashes the row — not just a price change.
  const prevRowSigRef     = useRef<Record<string, Record<number, string>>>({});
  // The server no longer stamps embedded_at (the perfect-embeddings SMT adds the
  // vector but no timestamp). We detect a re-embed by the embedding vector itself
  // changing — prevEmbFpRef holds the last fingerprint, embedObservedAtRef the
  // local time we last saw it change (used as the displayed "embedded at").
  const prevEmbFpRef      = useRef<Record<string, string>>({});
  const embedObservedAtRef = useRef<Record<string, string>>({});
  // Order status lives in the header, not the line-item table, and isn't part of
  // embedding_text (that's product names + categories only). Without its own
  // tracking a DELIVERED → CREATED edit swaps the badge with nothing to catch
  // the eye, so keep the last seen status per order and flash on change.
  const prevStatusRef     = useRef<Record<string, string>>({});
  const refreshTimerRef   = useRef<ReturnType<typeof setInterval> | null>(null);
  // The displayed result set is *pinned*: its membership and order are fixed by
  // the last explicit search. The silent auto-refresh only updates each pinned
  // order's live values in place — it never re-ranks. pinnedIdsRef holds that
  // frozen order; displayedByIdRef is the last-shown value for each id, used as
  // a fallback for a pinned order that dropped out of the refresh window.
  const pinnedIdsRef      = useRef<string[]>([]);
  const displayedByIdRef  = useRef<Record<string, VectorSearchResult>>({});

  const applyResults = useCallback((newResults: VectorSearchResult[]) => {
    const newFlashedRows: Record<number, Set<number>> = {};
    const newFlashedEmbeddings = new Set<number>();
    const newFlashedStatuses = new Set<number>();

    newResults.forEach((result, resultIdx) => {
      const id = result.order_id;
      const prevSigs = prevRowSigRef.current[id] ?? {};
      const rowFlash = new Set<number>();

      (result.line_items ?? []).forEach((item, lineIdx) => {
        // Signature over every field the row renders, so editing the product
        // name (or category/qty), not just the price, flashes the row.
        const price = item.live_price ?? item.unit_price ?? 0;
        const curr = [item.product_name ?? "", item.category ?? "", item.quantity ?? "", price].join("|");
        const prev = prevSigs[lineIdx];
        if (prev !== undefined && prev !== curr) rowFlash.add(lineIdx);
        prevSigs[lineIdx] = curr;
      });
      prevRowSigRef.current[id] = prevSigs;
      if (rowFlash.size > 0) newFlashedRows[resultIdx] = rowFlash;

      // Re-embed detection: the vector (hence its fingerprint) changes only when
      // the SMT re-embeds. Flash on change; first sighting just records a baseline.
      const fp = embeddingFingerprint(result.embedding);
      const prevFp = prevEmbFpRef.current[id];
      if (prevFp === undefined) {
        embedObservedAtRef.current[id] = new Date().toISOString();
      } else if (prevFp !== fp) {
        newFlashedEmbeddings.add(resultIdx);
        embedObservedAtRef.current[id] = new Date().toISOString();
      }
      prevEmbFpRef.current[id] = fp;
      // Surface the observed embed time to the card (replaces server embedded_at).
      result.embedded_at = embedObservedAtRef.current[id] ?? null;

      // Status change. Like the embedding, first sighting only sets a baseline
      // so an explicit search doesn't light up every card at once.
      const status = result.order_status ?? "";
      const prevStatus = prevStatusRef.current[id];
      if (prevStatus !== undefined && prevStatus !== status) {
        newFlashedStatuses.add(resultIdx);
      }
      prevStatusRef.current[id] = status;
    });

    displayedByIdRef.current = Object.fromEntries(newResults.map(r => [r.order_id, r]));
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
    // Held as long as the embedding flash, not the shorter row flash: a status
    // change is the headline event in this demo and has to survive a glance away.
    if (newFlashedStatuses.size > 0) {
      setFlashedStatuses(newFlashedStatuses);
      setTimeout(() => setFlashedStatuses(new Set()), 2000);
    }
  }, []);

  const executeSearch = useCallback(async (query: string, silent = false) => {
    if (!query) {
      setResults([]); setSearchError(null); setSubmittedQuery(""); setHasSearched(false);
      pinnedIdsRef.current = []; displayedByIdRef.current = {};
      return;
    }
    if (!silent) { setIsSearching(true); setSearchError(null); setSubmittedQuery(query); setHasSearched(true); }
    try {
      const filters = {
        ...(filterZone ? { store_zone: filterZone } : {}),
        ...(filterStatus ? { order_status: filterStatus } : {}),
      };
      if (!silent) {
        // Explicit search: this is the ONLY path that (re-)ranks. Take the top
        // matches by relevance and pin that set + order for the value-refresh.
        const response = await searchApi.vectorSearchOrders(query, EXPLICIT_SEARCH_LIMIT, filters);
        const ranked = (response.data.results ?? []).filter(r => r.score >= MIN_SCORE);
        pinnedIdsRef.current = ranked.map(r => r.order_id);
        applyResults(ranked);
      } else {
        // Silent refresh: update the pinned orders' live values in place without
        // re-ranking. Query a wide window and reconcile by order_id so an order
        // that has fallen in rank still refreshes; the MIN_SCORE gate does not
        // apply here (a pinned order whose score dropped must still update, not
        // vanish). Orders that fell out of the window keep their last values.
        if (pinnedIdsRef.current.length === 0) return;
        const response = await searchApi.vectorSearchOrders(query, REFRESH_SEARCH_LIMIT, filters);
        const freshById = new Map((response.data.results ?? []).map(r => [r.order_id, r]));
        const reconciled = pinnedIdsRef.current
          .map(id => freshById.get(id) ?? displayedByIdRef.current[id])
          .filter((r): r is VectorSearchResult => Boolean(r));
        applyResults(reconciled);
      }
    } catch (err) {
      if (!silent) {
        console.error("Vector search failed:", err);
        setSearchError("Vector search unavailable. Ensure OpenSearch and the embedding service are running.");
        setResults([]);
        pinnedIdsRef.current = []; displayedByIdRef.current = {};
      }
    } finally {
      if (!silent) setIsSearching(false);
    }
  }, [applyResults, filterZone, filterStatus]);

  // Auto-refresh every 2s after a successful search
  useEffect(() => {
    if (refreshTimerRef.current) clearInterval(refreshTimerRef.current);
    if (!submittedQuery) return;
    refreshTimerRef.current = setInterval(() => {
      executeSearch(submittedQuery, true);
    }, 2000);
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
            <h3 className="text-lg font-semibold text-gray-900">{vp.heading}</h3>
            <p className="text-xs text-gray-500">{vp.subhead}</p>
          </div>
        </div>
      </button>

      {isExpanded && (
        <div className="px-6 pb-6">
          <div className="mb-4 text-sm text-gray-600 leading-relaxed">
            <p>{vp.explainer}</p>
          </div>

          {/* Search box */}
          <div className="border rounded-lg overflow-hidden mb-4">
            <div className="bg-gray-50 px-4 py-2 border-b flex items-center gap-2">
              <Search className="h-4 w-4 text-purple-500" />
              <span className="text-sm font-medium text-gray-700">{vp.search_heading}</span>
            </div>
            <div className="p-4 space-y-3">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={searchQuery}
                  onChange={e => setSearchQuery(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder={placeholder("semantic_search")}
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent"
                />
                <button
                  onClick={performSearch}
                  disabled={isSearching || !searchQuery.trim()}
                  className="px-4 py-2 bg-accent-600 text-white text-sm font-medium rounded-md hover:bg-accent-700 disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  <Search className="h-4 w-4" />
                  Search
                </button>
              </div>
              <div className="flex gap-2 items-center">
                <span className="text-xs text-gray-500">Filters:</span>
                <select
                  value={filterZone}
                  onChange={e => setFilterZone(e.target.value)}
                  className="px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent"
                >
                  <option value="">{vp.all_zones}</option>
                  {enumOptions("zone").map(o => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
                <select
                  value={filterStatus}
                  onChange={e => setFilterStatus(e.target.value)}
                  className="px-3 py-2 border border-gray-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-accent-500 focus:border-transparent"
                >
                  <option value="">{vp.all_statuses}</option>
                  {enumOptions("order_status")
                    .filter(o => o.value !== "CANCELLED")
                    .map(o => (
                      <option key={o.value} value={o.value}>{o.label}</option>
                    ))}
                </select>
              </div>
              <div className="text-xs text-gray-500">
                Try:{" "}
                {searchQueries.map((q, i) => (
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
            <WriteTripleForm
              initialSubject={writeSubject}
              onWriteComplete={(mzLowerBound, wallClock) => setWriteTrigger({ mzLowerBound, wallClock })}
            />
          </div>
          <div className="mb-4">
            <SearchIndexUpdates writeTrigger={writeTrigger} />
          </div>

          {/* Live order results */}
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
                        statusFlashing={flashedStatuses.has(idx)}
                        onSelectSubject={setWriteSubject}
                      />
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          {submittedQuery && <RerankComparison query={submittedQuery} />}

        </div>
      )}
    </div>
  );
};

export default VectorPipelineCard;
