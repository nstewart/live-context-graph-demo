import { useState, useEffect } from "react";
import { searchApi, RerankResponse } from "../api/client";

const fmtMs = (ms?: number) => (ms == null ? "—" : `${ms} ms`);

function Delta({ delta }: { delta: number }) {
  if (delta > 0) return <span className="text-green-600 font-semibold">▲{delta}</span>;
  if (delta < 0) return <span className="text-red-500 font-semibold">▼{-delta}</span>;
  return <span className="text-gray-400">—</span>;
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
      <div className="bg-gray-50 px-4 py-2 border-b flex items-center gap-3 flex-wrap">
        <span className="text-sm font-medium text-gray-700">Cross-Encoder Rerank</span>
        {data?.model && <span className="font-mono text-xs text-gray-400">{data.model}</span>}
        <span className="ml-auto flex items-center gap-3 text-xs text-gray-500">
          <span>retrieve <b className="text-gray-700">{fmtMs(t.retrieval_ms)}</b></span>
          <span className="text-purple-700">features from MZ <b>{fmtMs(t.feature_fetch_ms)}</b></span>
          <span>cross-encoder <b className="text-gray-700">{fmtMs(t.rerank_ms)}</b></span>
        </span>
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
