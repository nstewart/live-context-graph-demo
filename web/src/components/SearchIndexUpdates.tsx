import { useState, useEffect, useMemo } from "react";
import { searchApi } from "../api/client";
import { usePropagation } from "../contexts/PropagationContext";

const VIRTUAL_SIZE = 65536;

function hashDocId(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) {
    h = Math.imul(31, h) + id.charCodeAt(i) >>> 0;
  }
  return h % VIRTUAL_SIZE;
}

const OP_COLORS: Record<string, string> = {
  INSERT: '#10b981',
  UPDATE: '#a855f7',
  DELETE: '#ef4444',
};

interface SearchIndexUpdatesProps {
  writeTrigger: { mzLowerBound: number; wallClock: number } | null;
}

export const SearchIndexUpdates = ({ writeTrigger }: SearchIndexUpdatesProps) => {
  const [impact, setImpact] = useState<{ impacted: number; total: number; pct: number } | null>(null);
  const [watchingImpact, setWatchingImpact] = useState(false);
  const { events } = usePropagation();

  const marks = useMemo(() => {
    if (!writeTrigger) return null;
    const relevant = events.filter((e) => e.timestamp >= writeTrigger.wallClock);
    if (relevant.length === 0) return null;
    const seen = new Map<string, string>();
    for (const e of relevant) {
      seen.set(e.doc_id, OP_COLORS[e.operation] ?? '#6b7280');
    }
    return Array.from(seen.entries()).map(([doc_id, color]) => ({
      doc_id,
      color,
      pct: (hashDocId(doc_id) / VIRTUAL_SIZE) * 100,
    }));
  }, [events, writeTrigger]);

  useEffect(() => {
    if (!writeTrigger) return;
    let cancelled = false;
    const watch = async () => {
      setWatchingImpact(true);
      setImpact(null);
      let lastImpacted = -1;
      for (let i = 0; i < 8; i++) {
        await new Promise(r => setTimeout(r, 1000));
        if (cancelled) break;
        try {
          const res = await searchApi.indexImpact(writeTrigger.mzLowerBound);
          const data = res.data;
          if (data.impacted > 0 && data.impacted === lastImpacted) break;
          lastImpacted = data.impacted;
          setImpact(data);
        } catch {
          break;
        }
      }
      if (!cancelled) setWatchingImpact(false);
    };
    watch();
    return () => { cancelled = true; };
  }, [writeTrigger]);

  return (
    <div className="bg-gray-50 rounded-lg p-4">
      <div className="flex items-center gap-2 mb-3">
        <span className="font-medium text-gray-900">Search Index Updates</span>
      </div>
      <div className="relative h-4 rounded overflow-hidden bg-gray-200">
        {marks?.map(({ doc_id, color, pct }) => (
          <div
            key={doc_id}
            className="absolute top-0 bottom-0"
            style={{ left: `${pct}%`, width: '2px', backgroundColor: color }}
            title={doc_id}
          />
        ))}
      </div>
      {(watchingImpact || impact) && (
        <div className="mt-1 text-xs text-gray-500 flex items-center gap-2">
          {watchingImpact && !impact && (
            <span className="text-gray-400 animate-pulse">Watching pipeline…</span>
          )}
          {impact && (
            <>
              <span className="font-mono font-semibold text-purple-700">{impact.impacted}</span>
              <span className="text-gray-400">/</span>
              <span className="font-mono text-gray-600">{impact.total}</span>
              <span>docs re-indexed</span>
              <span className={`font-semibold ${impact.pct > 10 ? 'text-orange-600' : 'text-purple-600'}`}>
                ({impact.pct}%)
              </span>
              {watchingImpact && <span className="text-gray-400 animate-pulse">…</span>}
            </>
          )}
          <div className="ml-auto flex items-center gap-3 text-gray-400">
            <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-sm" style={{ backgroundColor: OP_COLORS.INSERT }} />insert</span>
            <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-sm" style={{ backgroundColor: OP_COLORS.UPDATE }} />update</span>
            <span className="flex items-center gap-1"><span className="inline-block w-2 h-2 rounded-sm" style={{ backgroundColor: OP_COLORS.DELETE }} />delete</span>
          </div>
        </div>
      )}
    </div>
  );
};

export default SearchIndexUpdates;
