/**
 * The OpenUI Lang program this workspace renders.
 *
 * The program is built by us, not by a model: the backend returns a validated
 * `AnswerEnvelope`, and all the renderer needs is the `result_id` to look that
 * envelope up in the registry. `JSON.stringify` is what makes that safe: the id
 * is emitted as a JSON string literal, so a value containing quotes, brackets or
 * newlines stays inside the argument and cannot escape into program syntax.
 *
 * Kept free of React and JSX so `npm test` can parse it with the real library
 * schema under node.
 */
import { z } from "zod/v4";

export const ANSWER_COMPONENT_NAME = "Answer";

/**
 * Mirrors the only prop our registered component accepts. The OpenUI parser
 * type-checks call arguments against this, which is why a non-string id fails to
 * render instead of reaching the component.
 */
export const answerPropsSchema = z.object({
  resultId: z.string().describe("The id of a server-validated answer envelope held by the workspace."),
});

export function answerProgram(resultId: string): string {
  return `root = ${ANSWER_COMPONENT_NAME}(${JSON.stringify(resultId)})`;
}
