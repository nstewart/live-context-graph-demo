import { useCallback, useEffect, useRef } from "react";
import { queryStatsApi, ViewDefinitionResponse } from "../api/client";

/** How long to wait before retrying a failed prefetch. Long enough not to
 *  hammer a cold backend, short enough to self-heal before a demo starts. */
const RETRY_DELAY_MS = 5000;
const MAX_ATTEMPTS = 3;

export interface ViewDefinitionCache {
  /** Returns a definition if it was prefetched, else null (caller should fetch). */
  get: (viewName: string) => ViewDefinitionResponse | null;
  /** Stores a definition fetched via the fallback path so the next click is instant. */
  set: (viewName: string, definition: ViewDefinitionResponse) => void;
}

/** Prefetches every lineage-graph view definition once on mount and holds them
 *  in a ref-backed cache.
 *
 *  Clicking a node in the lineage graph otherwise fires a SHOW CREATE that
 *  queues behind the load generator's traffic on the Materialize pool, which
 *  during a demo can stall for seconds. Definitions are static for the life of
 *  the deployment, so fetching them all once up front makes every click render
 *  from memory.
 *
 *  Deliberately a ref, not state: filling the cache must not re-render the page
 *  (which would restart the metrics charts mid-demo). Callers read it only in
 *  event handlers, where a ref is always current. */
export function useViewDefinitions(): ViewDefinitionCache {
  const cacheRef = useRef<Map<string, ViewDefinitionResponse>>(new Map());

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const prefetch = async (attempt: number) => {
      try {
        const res = await queryStatsApi.getViewDefinitions();
        if (cancelled) return;

        for (const [name, definition] of Object.entries(res.data.definitions)) {
          cacheRef.current.set(name, definition);
        }

        // A partial result means some object was missing from the catalog.
        // Those fall back to per-click fetches, so warn rather than retry.
        if (res.data.cached_count < res.data.expected_count) {
          console.warn(
            `Prefetched ${res.data.cached_count}/${res.data.expected_count} view definitions; ` +
              `the rest will load on click.`
          );
        }
      } catch (err) {
        if (cancelled) return;
        if (attempt < MAX_ATTEMPTS) {
          timer = setTimeout(() => prefetch(attempt + 1), RETRY_DELAY_MS);
          return;
        }
        // Give up quietly: every click still works via the per-view endpoint.
        console.warn("Could not prefetch view definitions:", err);
      }
    };

    prefetch(1);

    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []);

  const get = useCallback(
    (viewName: string) => cacheRef.current.get(viewName) ?? null,
    []
  );

  const set = useCallback((viewName: string, definition: ViewDefinitionResponse) => {
    cacheRef.current.set(viewName, definition);
  }, []);

  return { get, set };
}
