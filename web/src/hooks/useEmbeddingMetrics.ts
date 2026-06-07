import { useState, useEffect } from "react";
import { searchApi, EmbeddingMetrics } from "../api/client";

const POLL_INTERVAL_MS = 3000;

/** Polls the embedding SMT metrics endpoint while `enabled`. Returns null
 *  until the first successful response, then holds the last good value across
 *  transient poll failures (the ticker shouldn't flicker on a dropped request). */
export function useEmbeddingMetrics(enabled: boolean = true): EmbeddingMetrics | null {
  const [metrics, setMetrics] = useState<EmbeddingMetrics | null>(null);

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;

    const poll = async () => {
      try {
        const res = await searchApi.embeddingMetrics();
        if (!cancelled) setMetrics(res.data);
      } catch {
        // Keep the last good value; a single dropped poll self-heals in 3s.
      }
    };

    poll();
    const timer = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [enabled]);

  return metrics;
}
