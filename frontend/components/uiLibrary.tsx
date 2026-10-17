"use client";

/**
 * The library a generative program is allowed to use.
 *
 * The model chooses *composition*: which parts of an answer to lead with, in what order,
 * and what to annotate. It cannot supply a fact. `Answer` and `AnswerPart` take only a
 * `resultId` (and, for a part, which part), and resolve every value from the workspace's
 * registry of server-validated envelopes. `Note` is the only free-text component, and a
 * numeral it invents is caught by the answer audit (`tools/evalrun score`).
 *
 * The root stays one level deep: `Layout` holds parts and notes, but a part cannot hold a
 * layout, so a model cannot build unbounded nesting.
 */
import { createLibrary, defineComponent, useRenderNode } from "@openuidev/react-lang";
import { useContext } from "react";
import { z } from "zod/v4";

import { ANSWER_PARTS, type AnswerPart as AnswerPartName } from "@/lib/answerParts";
import type { AnswerEnvelope } from "@/lib/contracts";

import { AnswerActionsContext, AnswerRegistryContext } from "./answerLibrary";
import { AnswerEnvelopeView } from "./AnswerEnvelopeView";

function useAnswer(resultId: string): AnswerEnvelope | undefined {
  return useContext(AnswerRegistryContext).get(resultId);
}

const resultId = z.string().describe("The id of a server-validated answer envelope held by the workspace.");

const Answer = defineComponent({
  name: "Answer",
  description: "The complete answer: summary, findings, warnings, conflicts, visual, evidence and calculations.",
  props: z.object({ resultId }),
  component: ({ props }) => (
    <RegisteredAnswer resultId={props.resultId} parts={undefined} />
  ),
});

const AnswerPart = defineComponent({
  name: "AnswerPart",
  description:
    "One section of the answer. Use it to lead with the important part and drop sections the reader does not need.",
  props: z.object({
    resultId,
    part: z.enum(ANSWER_PARTS).describe("Which section of the answer to render."),
  }),
  component: ({ props }) => (
    <RegisteredAnswer resultId={props.resultId} parts={[props.part as AnswerPartName]} />
  ),
});

const Note = defineComponent({
  name: "Note",
  description:
    "A short annotation in your own words. Do not restate numbers; the answer already carries them.",
  props: z.object({ text: z.string().describe("Plain prose, one or two sentences.") }),
  component: ({ props }) => <p className="answer__summary generative-note">{props.text}</p>,
});

const Layout = defineComponent({
  name: "Layout",
  description: "The top of every program: an ordered stack of answer parts and notes.",
  props: z.object({
    children: z.array(z.union([Answer.ref, AnswerPart.ref, Note.ref])),
  }),
  component: ({ props }) => {
    const renderNode = useRenderNode();
    return <div className="generative-layout">{props.children.map((child) => renderNode(child))}</div>;
  },
});

function RegisteredAnswer({ resultId: id, parts }: { resultId: string; parts: readonly AnswerPartName[] | undefined }) {
  const envelope = useAnswer(id);
  const actions = useContext(AnswerActionsContext);
  if (!envelope) {
    return (
      <div className="error-state">
        <p className="error-state__title">Answer not available</p>
        <p>
          This workspace holds no validated envelope for result{" "}
          <span className="answer__meta-code">{id}</span>. Nothing is rendered from anything else.
        </p>
      </div>
    );
  }
  return <AnswerEnvelopeView envelope={envelope} actions={actions} parts={parts} />;
}

export const generativeLibrary = createLibrary({
  root: "Layout",
  components: [Layout, Answer, AnswerPart, Note],
});
