"use client";

/**
 * OpenUI Reliability SDK, initialised once at the client root.
 *
 * Two decisions worth stating:
 *
 * - **A module side effect, not a hook.** The SDK has to be listening before the
 *   first OpenUI program is parsed and rendered, and effects run after the tree is
 *   committed. Evaluating at module load happens before any OpenUI response can
 *   reach the screen.
 * - **Guarded to the browser.** This module is imported by the root layout, so it
 *   is also evaluated during server rendering. Telemetry must never start on the
 *   server: there is no browser to attribute events to, and it would emit noise.
 *
 * The key is a *client* key (created in the Thesys console as a client API key,
 * not a Gateway server key). It is safe to expose to the browser, which is why it
 * is a `NEXT_PUBLIC_` variable; `.env.local` is git-ignored so it is never
 * committed. When the variable is absent the SDK is simply not started, so local
 * development without a key still works.
 */
import * as Observability from "@openuidev/observability-cloud";

const apiKey = process.env.NEXT_PUBLIC_OPENUI_API_KEY;

if (typeof window !== "undefined" && apiKey) {
  Observability.init({ apiKey });
}

export {};
