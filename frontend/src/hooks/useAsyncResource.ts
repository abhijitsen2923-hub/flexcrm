import { useCallback, useEffect, useRef, useState } from "react";

import { getCached, hasCache, setCached } from "./resourceCache";


interface UseAsyncResourceOptions {
  /**
   * When set, results are cached under this key (stale-while-revalidate): a
   * revisit renders the last value instantly and refetches in the background.
   * Vary it with the query, e.g. `"leads:" + JSON.stringify(query)`.
   */
  cacheKey?: string;
  /** Flip `slow` true if a fetch runs longer than this (default 4s) — used to
   * surface a "waking the server…" hint on a cold backend. */
  slowAfterMs?: number;
}


export function useAsyncResource<T, TArgs extends unknown[]>(
  executor: (...args: TArgs) => Promise<T>,
  initialData: T,
  options: UseAsyncResourceOptions = {}
) {
  const { cacheKey, slowAfterMs = 4000 } = options;

  const [data, setData] = useState<T>(() =>
    cacheKey ? getCached<T>(cacheKey) ?? initialData : initialData
  );
  const [loading, setLoading] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [slow, setSlow] = useState(false);
  const [error, setError] = useState<unknown>(null);

  // Read the latest cacheKey inside execute without changing execute's identity
  // (callers memoize `refresh` on `execute`); keep a stable initialData too.
  const cacheKeyRef = useRef(cacheKey);
  cacheKeyRef.current = cacheKey;
  const initialRef = useRef(initialData);

  // On key change, seed from cache (instant paint on revisit) or reset to the
  // initial value (so a cold key shows a skeleton instead of the old key's data).
  useEffect(() => {
    if (!cacheKey) return;
    const cached = getCached<T>(cacheKey);
    setData(cached !== undefined ? cached : initialRef.current);
  }, [cacheKey]);

  const execute = useCallback(
    async (...args: TArgs) => {
      const key = cacheKeyRef.current;
      const warm = key ? hasCache(key) : false;
      // Warm cache → quiet background refresh; cold → blocking load (skeleton).
      if (warm) {
        setIsValidating(true);
      } else {
        setLoading(true);
      }
      setError(null);
      setSlow(false);
      const slowTimer = setTimeout(() => setSlow(true), slowAfterMs);

      try {
        const result = await executor(...args);
        setData(result);
        if (key) setCached(key, result);
        return result;
      } catch (requestError) {
        setError(requestError);
        throw requestError;
      } finally {
        clearTimeout(slowTimer);
        setLoading(false);
        setIsValidating(false);
        setSlow(false);
      }
    },
    [executor, slowAfterMs]
  );

  return {
    data,
    setData,
    loading,
    isValidating,
    slow,
    error,
    execute
  };
}
