"use client";

/**
 * The OpenUI library, defined once at module scope as the brief requires.
 *
 * Trust boundary: the only program the Renderer ever sees is the one
 * `answerProgram()` builds from a `result_id`. That program is parsed against
 * this library's own JSON Schema before it is handed over, so an id that could
 * not be a valid `Answer` argument fails loudly here instead of reaching a
 * component. The component itself does nothing but look the id up in a React
 * context that holds *validated* envelopes, so no model-supplied JavaScript,
 * HTML, SQL or action provider is ever evaluated.
 */
import { Renderer, createLibrary, createParser, defineComponent } from "@openuidev/react-lang";
import { createContext, useContext, useMemo } from "react";

import { ANSWER_COMPONENT_NAME, answerProgram, answerPropsSchema } from "@/lib/answerProgram";
import type { AnswerEnvelope } from "@/lib/contracts";

import { AnswerEnvelopeView, type AnswerActions } from "./AnswerEnvelopeView";

/** result_id -> Zod-validated AnswerEnvelope. */
export const AnswerRegistryContext = createContext<ReadonlyMap<string, AnswerEnvelope>>(new Map());

/** Workspace callbacks the answer needs (opening the evidence drawer). */
export const AnswerActionsContext = createContext<AnswerActions | null>(null);

function RegisteredAnswer({ resultId }: { resultId: string }) {
  const registry = useContext(AnswerRegistryContext);
  const actions = useContext(AnswerActionsContext);
  const envelope = registry.get(resultId);

  if (!envelope) {
    return (
      <div className="error-state">
        <p className="error-state__title">Answer not available</p>
        <p>
          This workspace has no validated envelope for result <span className="answer__meta-code">{resultId}</span>. It
          is not rendered from anything else.
        </p>
      </div>
    );
  }

  return <AnswerEnvelopeView envelope={envelope} actions={actions} />;
}

const Answer = defineComponent({
  name: ANSWER_COMPONENT_NAME,
  description: "Renders one server-validated asset intelligence answer envelope, identified by its result id.",
  props: answerPropsSchema,
  component: ({ props }) => <RegisteredAnswer resultId={props.resultId} />,
});

export const copilotLibrary = createLibrary({
  root: ANSWER_COMPONENT_NAME,
  components: [Answer],
});

/** The same schema the Renderer uses, so our own program is checked rather than assumed. */
const programParser = createParser(copilotLibrary.toJSONSchema(), copilotLibrary.root);

export function AnswerBlock({ resultId }: { resultId: string }) {
  const problems = useMemo<string[]>(() => {
    try {
      return programParser
        .parse(answerProgram(resultId))
        .meta.errors.map((error) => `${error.code}: ${error.message}`);
    } catch (error) {
      return [error instanceof Error ? error.message : String(error)];
    }
  }, [resultId]);

  if (problems.length > 0) {
    return (
      <div className="error-state">
        <p className="error-state__title">The renderer rejected this answer reference</p>
        <ul>
          {problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      </div>
    );
  }

  return <Renderer library={copilotLibrary} response={answerProgram(resultId)} isStreaming={false} />;
}
