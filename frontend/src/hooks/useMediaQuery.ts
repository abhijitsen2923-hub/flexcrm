import { useEffect, useState } from "react";


/**
 * Subscribe to a CSS media query and re-render when it flips.
 *
 * SSR/first-paint safe: returns `false` when `matchMedia` is unavailable, then
 * syncs on mount. Use for JS-side responsive branches the CSS breakpoints can't
 * express (e.g. rendering a different component tree on phones).
 *
 *   const isPhone = useMediaQuery("(max-width: 639px)");
 */
export function useMediaQuery(query: string): boolean {
  const getMatch = () =>
    typeof window !== "undefined" && typeof window.matchMedia === "function"
      ? window.matchMedia(query).matches
      : false;

  const [matches, setMatches] = useState<boolean>(getMatch);

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
      return;
    }
    const mql = window.matchMedia(query);
    const onChange = () => setMatches(mql.matches);
    // Sync immediately in case the query changed between render and effect.
    onChange();
    // addEventListener is the modern API; older Safari only has addListener.
    if (typeof mql.addEventListener === "function") {
      mql.addEventListener("change", onChange);
      return () => mql.removeEventListener("change", onChange);
    }
    mql.addListener(onChange);
    return () => mql.removeListener(onChange);
  }, [query]);

  return matches;
}
