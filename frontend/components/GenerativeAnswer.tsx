"use client";

import { Renderer } from "@openuidev/react-lang";
import { useEffect, useState } from "react";

import { getUiProgram } from "@/lib/api";
import type { PrivacyGuard } from "@/lib/session";

import { AnswerBlock } from "./answerLibrary";
import { generativeLibrary } from "./uiLibrary";

/**
 * One answer, rendered either by the generative UI model or deterministically.
 *
 * Generative is an enhancement with no authority: the program selects which parts of the
 * already validated envelope to show, and every value still comes from the registry. If
 * the model is off, unreachable, or composed something the guard rejected, this renders
 * the deterministic answer instead and never shows an error for a working product.
 */
export function GenerativeAnswer({
  resultId,
  userId,
  guard,
}: {
  resultId: string;
  userId: string;
  guard: PrivacyGuard;
}) {
  const [program, setProgram] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setProgram(null);
    const scope = guard.begin();
    (async () => {
      try {
        const ui = await getUiProgram(userId, resultId, scope);
        if (cancelled || !scope.isCurrent()) return;
        if (ui.program) setProgram(ui.program);
      } catch {
        // The deterministic rendering below is the answer; a failed enrichment is not an error.
      } finally {
        guard.release(scope);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [resultId, userId, guard]);

  if (!program) return <AnswerBlock resultId={resultId} />;

  return (
    <Renderer library={generativeLibrary} response={program} isStreaming={false} onError={() => setProgram(null)} />
  );
}
