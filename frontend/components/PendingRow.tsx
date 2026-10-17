"use client";

import { ThinkingOrb } from "thinking-orbs";

/**
 * The pending assistant row.
 *
 * libraries.dev placement: `thinking-orbs`, `ThinkingOrb state="working" size={20}`.
 * The reference puts an orb "beside a text label" for any loading state and
 * tunes `working` for "generic agent work, tool running", which is exactly what a
 * pending turn is from the browser's point of view: the backend is resolving
 * facts, collecting evidence and composing one answer. `size={20}` is the
 * inline-text preset, `theme="light"` is pinned because this surface is light
 * (`auto` would follow the OS setting and could draw pale dots on white), and
 * the orb is unmounted the moment the turn settles rather than being left
 * animating. Reduced motion is the package's own: one static frame, no loop.
 */
export function PendingRow({ analysisDate }: { analysisDate: string }) {
  return (
    <div className="pending" role="status">
      <ThinkingOrb state="working" size={20} theme="light" aria-hidden="true" />
      <span className="pending__label">Working on your question against the {analysisDate} dataset</span>
    </div>
  );
}
