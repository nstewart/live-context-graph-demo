/**
 * Wraps an async function so that overlapping invocations are skipped while a
 * previous call is still in flight.
 *
 * Fixed-interval pollers (setInterval) fire on a fixed cadence regardless of how
 * long each call takes. If the backend/tunnel slows down so a call takes longer
 * than the interval, requests pile up faster than they drain and can exhaust the
 * browser's per-origin HTTP connection pool — which then stalls unrelated
 * requests (like a triple write) indefinitely. Guarding the poller so at most one
 * call is ever in flight prevents that pile-up.
 */
export function singleFlight<Args extends unknown[]>(
  fn: (...args: Args) => Promise<void>,
): (...args: Args) => Promise<void> {
  let inFlight = false;
  return async (...args: Args) => {
    if (inFlight) return;
    inFlight = true;
    try {
      await fn(...args);
    } finally {
      inFlight = false;
    }
  };
}
