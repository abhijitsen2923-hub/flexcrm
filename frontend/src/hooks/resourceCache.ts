/**
 * Tiny in-memory stale-while-revalidate cache for fetched resources.
 *
 * Keyed by a caller-supplied string (typically `"<domain>:" + JSON.stringify(query)`).
 * `useAsyncResource` reads a cached value to render instantly on revisit, then
 * refetches in the background and writes the fresh value back. There is no TTL —
 * every mount still revalidates; the cache only removes the *wait*, not the refresh.
 *
 * It lives for the lifetime of the tab and is wiped on logout (see AuthContext)
 * so one user's data never shows to the next.
 */

interface CacheEntry {
  data: unknown;
  ts: number;
}

const cache = new Map<string, CacheEntry>();

export function hasCache(key: string): boolean {
  return cache.has(key);
}

export function getCached<T>(key: string): T | undefined {
  const entry = cache.get(key);
  return entry ? (entry.data as T) : undefined;
}

export function setCached(key: string, data: unknown): void {
  cache.set(key, { data, ts: Date.now() });
}

/**
 * Drop cached entries. Pass an exact key, or a prefix like `"leads:"` to drop
 * every query under a domain (call after a create/update/delete so the next
 * visit to any filtered view refetches instead of showing pre-mutation data).
 */
export function invalidate(keyOrPrefix: string): void {
  for (const key of cache.keys()) {
    if (key === keyOrPrefix || key.startsWith(keyOrPrefix)) {
      cache.delete(key);
    }
  }
}

export function clearResourceCache(): void {
  cache.clear();
}
