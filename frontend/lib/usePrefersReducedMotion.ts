"use client";

import { useEffect, useState } from "react";

/**
 * `prefers-reduced-motion`, live.
 *
 * Taken from the border-beam reference: the rotate beam types (`md`, `line`,
 * `sm`) do not handle reduced motion themselves, so the caller must turn them
 * off. The pulse types ship their own reduce block; this hook keeps the whole
 * workspace consistent either way.
 */
export function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduced(query.matches);
    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, []);

  return reduced;
}
