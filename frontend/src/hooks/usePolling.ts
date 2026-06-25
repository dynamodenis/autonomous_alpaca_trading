import { useCallback, useEffect, useRef, useState } from "react";

interface PollingState<T> {
  data: T | null;
  error: Error | null;
  /** True only during the very first load (no data yet). */
  loading: boolean;
  /** True whenever a fetch is in flight, including background refreshes. */
  refreshing: boolean;
  lastUpdated: number | null;
  refresh: () => void;
}

/**
 * Polls an async fetcher on an interval. Keeps the previous data visible while
 * refreshing (no flicker) and survives transient errors without wiping the UI.
 */
export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs: number,
): PollingState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<number | null>(null);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;
  const mountedRef = useRef(true);

  const run = useCallback(async () => {
    setRefreshing(true);
    try {
      const result = await fetcherRef.current();
      if (!mountedRef.current) return;
      setData(result);
      setError(null);
      setLastUpdated(Date.now());
    } catch (err) {
      if (!mountedRef.current) return;
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      if (mountedRef.current) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    run();
    const id = window.setInterval(run, intervalMs);
    return () => {
      mountedRef.current = false;
      window.clearInterval(id);
    };
  }, [run, intervalMs]);

  return {
    data,
    error,
    loading: data === null && error === null,
    refreshing,
    lastUpdated,
    refresh: run,
  };
}
