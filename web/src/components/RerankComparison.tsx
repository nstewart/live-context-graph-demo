import { useState, useEffect } from "react";
import { searchApi, RerankResponse } from "../api/client";

const fmtMs = (ms?: number) => (ms == null ? "—" : `${ms} ms`);

function Delta({ delta }: { delta: number }) {
  if (delta > 0) return <span className="text-green-600 font-semibold">▲{delta}</span>;
  if (delta < 0) return <span className="text-red-500 font-semibold">▼{-delta}</span>;
  return <span className="text-gray-400">—</span>;
}

// The three pipeline stages, in the order they run, as a proportional stacked bar.
const STAGES = [
  { key: "retrieval_ms", label: "retrieve", bar: "bg-gray-300", dot: "bg-gray-300" },
  { key: "feature_fetch_ms", label: "features from MZ", bar: "bg-purple-500", dot: "bg-purple-500" },
  { key: "rerank_ms", label: "cross-encoder", bar: "bg-indigo-400", dot: "bg-indigo-400" },
] as const;

function StageLatency({ timings }: { timings: Record<string, number | undefined> }) {
  const segs = STAGES.map((s) => ({ ...s, ms: timings[s.key] ?? 0 })).filter((s) => s.ms > 0);
  const total = segs.reduce((a, s) => a + s.ms, 0);
  if (!total) return null;
  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="text-[11px] text-gray-500">response latency</span>
        <span className="text-[11px] font-semibold text-gray-700">{fmtMs(Math.round(total))}</span>
      </div>
      <div className="flex h-5 w-full rounded overflow-hidden bg-gray-100">
        {segs.map((s) => {
          const pct = (s.ms / total) * 100;
          return (
            <div
              key={s.key}
              className={`${s.bar} flex items-center justify-center overflow-hidden`}
              style={{ width: `${pct}%` }}
              title={`${s.label}: ${Math.round(s.ms)} ms (${pct.toFixed(0)}%)`}
            >
              {pct >= 16 && <span className="px-1 text-[10px] font-medium text-white truncate">{Math.round(s.ms)}ms</span>}
            </div>
          );
        })}
      </div>
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1">
        {segs.map((s) => (
          <span key={s.key} className="flex items-center gap-1 text-[10px] text-gray-500">
            <span className={`inline-block w-2 h-2 rounded-sm ${s.dot}`} />
            <span>{s.label}</span>
            <span className="font-mono text-gray-400">{Math.round(s.ms)}ms</span>
          </span>
        ))}
      </div>
    </div>
  );
}

/** Two-stage retrieval comparison: kNN recall vs cross-encoder rerank.
 *  Row-per-candidate: ① where kNN ranked it · ② the document the reranker read
 *  (assembled live from Materialize) + the cross-encoder score · ③ new rank. */
export function RerankComparison({ query }: { query: string }) {
  const [data, setData] = useState<RerankResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!query) { setData(null); return; }
    let cancelled = false;
    setLoading(true);
    setError(null);
    searchApi.rerankedVectorSearch(query)
      .then((r) => { if (!cancelled) setData(r.data); })
      .catch(() => { if (!cancelled) setError("Rerank unavailable — ensure the embeddings service is running."); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [query]);

  if (!query) return null;

  const rows = (data?.results ?? []).slice(0, data?.limit ?? 8);
  const t = data?.timings ?? {};

  return (
    <div className="border rounded-lg overflow-hidden mt-4">
      <div className="bg-gray-50 px-4 py-2 border-b">
        <div className="flex items-center gap-3 flex-wrap mb-2">
          <span className="text-sm font-medium text-gray-700">Cross-Encoder Rerank</span>
          {data?.model && <span className="font-mono text-xs text-gray-400">{data.model}</span>}
        </div>
        <StageLatency timings={t} />
      </div>

      <div className="p-3 overflow-x-auto">
        {loading && !data ? (
          <div className="py-6 text-center text-sm text-gray-500">Reranking…</div>
        ) : error ? (
          <div className="py-6 text-center text-sm text-red-600">{error}</div>
        ) : rows.length === 0 ? (
          <div className="py-6 text-center text-sm text-gray-500">No results.</div>
        ) : (
          <table className="w-full border-collapse" style={{ fontSize: "12px" }}>
            <thead>
              <tr className="text-left text-gray-400 border-b border-gray-100">
                <th className="pb-1 pr-3 font-medium whitespace-nowrap">Order</th>
                <th className="pb-1 pr-3 font-medium whitespace-nowrap">① kNN</th>
                <th className="pb-1 pr-3 font-medium">② Reranker input — doc built live from Materialize</th>
                <th className="pb-1 font-medium whitespace-nowrap">③ Reranked</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.order_id} className="border-b border-gray-100 last:border-0 align-top">
                  <td className="py-2 pr-3 font-semibold text-gray-900 whitespace-nowrap">
                    #{c.order_number}
                    {c.status && <div className="text-gray-400 font-normal">{c.status}</div>}
                  </td>
                  <td className="py-2 pr-3 text-gray-600 whitespace-nowrap">
                    #{c.original_rank}
                    <div className="text-gray-400 font-mono">{c.knn_score.toFixed(3)}</div>
                  </td>
                  <td className="py-2 pr-3">
                    <code className="block bg-gray-100 text-gray-700 rounded px-2 py-1 leading-relaxed break-words">
                      {c.doc}
                    </code>
                    <span className="text-gray-500">x-enc <b className="text-purple-700 font-mono">{c.rerank_score.toFixed(2)}</b></span>
                  </td>
                  <td className="py-2 whitespace-nowrap">
                    <span className="font-semibold text-gray-900">#{c.new_rank}</span>{" "}
                    <Delta delta={c.delta} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="mt-2 text-xs text-gray-400">
          kNN gives the candidate set; the cross-encoder re-scores each on the document above — assembled fresh from
          Materialize (items · category · live price · stock · status) in <b>{fmtMs(t.feature_fetch_ms)}</b>.
        </p>
      </div>
    </div>
  );
}

export default RerankComparison;
