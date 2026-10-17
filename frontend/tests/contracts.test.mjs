/**
 * Contract, privacy and renderer-mapping tests.
 *
 * Run with `npm test` (node's built-in test runner plus node's own TypeScript
 * type stripping, so the real `lib/*.ts` modules are exercised rather than a
 * copy). Nothing here touches the network or the DOM.
 */
import assert from "node:assert/strict";
import test from "node:test";

import { createLibrary, createParser, defineComponent } from "@openuidev/react-lang";

import { answerProgram, answerPropsSchema } from "../lib/answerProgram.ts";
import { AnswerEnvelopeSchema, VisualKindSchema } from "../lib/contracts.ts";
import { buildTurns, emptySession, PrivacyGuard, reduceWorkspace, sessionForUser } from "../lib/session.ts";

/** A minimal envelope that satisfies the schema, with per-test overrides. */
function envelope(overrides = {}) {
  return AnswerEnvelopeSchema.parse({
    result_id: "res-1",
    question: "Which wells are not producing right now?",
    analysis_date: "2026-10-17",
    summary: "Two wells are not producing.",
    visual: { kind: "text", title: "Non-producing wells" },
    ...overrides,
  });
}

test("the envelope schema accepts a backend-shaped answer", () => {
  const parsed = envelope({
    findings: [{ label: "Not producing", value: [{ well_id: "W-1", delta_c: 12.5 }], evidence_ids: ["doc:1:2"] }],
    evidence: [
      {
        id: "doc:1:2",
        source_id: "doc",
        record_id: "W-1",
        path: "inspections/W-1.txt",
        title: "W-1 inspection",
        excerpt: "not producing",
        start_line: 1,
        end_line: 2,
      },
    ],
    warnings: ["Recorded status is stale."],
  });
  assert.equal(parsed.result_id, "res-1");
  assert.equal(parsed.findings[0].evidence_ids[0], "doc:1:2");
  assert.equal(parsed.evidence[0].path, "inspections/W-1.txt");
});

test("the envelope schema rejects an unknown visual kind instead of guessing", () => {
  assert.equal(VisualKindSchema.safeParse("pie").success, false);
  const bad = AnswerEnvelopeSchema.safeParse({
    result_id: "res-1",
    question: "q",
    analysis_date: "2026-10-17",
    summary: "s",
    visual: { kind: "pie", title: "Nope" },
  });
  assert.equal(bad.success, false);
});

test("the envelope schema rejects an answer missing a required field", () => {
  const bad = AnswerEnvelopeSchema.safeParse({
    result_id: "res-1",
    question: "q",
    analysis_date: "2026-10-17",
    // summary is required by schemas.py
    visual: { kind: "text", title: "t" },
  });
  assert.equal(bad.success, false);
});

test("sessionForUser returns a brand new, independent, empty session", () => {
  const a = sessionForUser("user-a");
  const b = sessionForUser("user-b");
  assert.deepEqual(a, { ...emptySession(), userId: "user-a" });
  assert.notEqual(a, b);
  assert.notEqual(a.threads, b.threads);
  assert.equal(a.threadId, null);
  assert.equal(a.pending, null);
  assert.equal(a.evidence, null);
});

test("switching user clears thread, messages, results and evidence in one transition", () => {
  let state = { session: emptySession(), users: [], usersStatus: "idle", usersError: null };
  state = reduceWorkspace(state, { type: "users-ready", users: [{ id: "user-a", name: "Ada" }] });
  state = reduceWorkspace(state, { type: "switch-user", userId: "user-a" });
  state = reduceWorkspace(state, {
    type: "threads-ready",
    threads: [{ id: "t1", title: "Downtime", created_at: "2026-10-17T09:00:00" }],
  });
  state = reduceWorkspace(state, {
    type: "thread-detail",
    threadId: "t1",
    messages: [{ id: "m1", role: "user", content: "q", created_at: "2026-10-17T09:00:00" }],
    envelopes: [envelope()],
  });
  state = reduceWorkspace(state, {
    type: "turn-start",
    pending: { clientMessageId: "c1", content: "q", analysisDate: "2026-10-17", sentAt: 1 },
  });
  state = reduceWorkspace(state, {
    type: "evidence-open",
    state: {
      answerQuestion: "q",
      analysisDate: "2026-10-17",
      refs: envelope().evidence,
      selectedId: "doc:1:2",
      source: null,
      status: "loading",
      error: null,
    },
  });

  // Sanity: the previous user's session really is populated before the switch.
  assert.equal(state.session.threadId, "t1");
  assert.equal(state.session.envelopes.length, 1);
  assert.notEqual(state.session.evidence, null);
  assert.notEqual(state.session.pending, null);

  const switched = reduceWorkspace(state, { type: "switch-user", userId: "user-b" });

  // The whole session equals a fresh one: nothing from user-a survives.
  assert.deepEqual(switched.session, sessionForUser("user-b"));
  assert.equal(switched.session.userId, "user-b");
  assert.deepEqual(switched.session.threads, []);
  assert.deepEqual(switched.session.messages, []);
  assert.deepEqual(switched.session.envelopes, []);
  assert.equal(switched.session.evidence, null);
  assert.equal(switched.session.pending, null);

  // The user list is not user-scoped data, so it survives.
  assert.deepEqual(switched.users, state.users);
});

test("PrivacyGuard invalidates and aborts in-flight work on reset", () => {
  const guard = new PrivacyGuard();
  const scope = guard.begin();
  assert.equal(scope.isCurrent(), true);
  assert.equal(scope.signal.aborted, false);

  guard.reset();

  assert.equal(scope.isCurrent(), false);
  assert.equal(scope.signal.aborted, true);
  assert.equal(guard.isCurrent(scope.epoch), false);

  // The pattern every request uses: a stale response cannot paint.
  let painted = 0;
  if (scope.isCurrent()) painted += 1;
  assert.equal(painted, 0);

  // A scope started after the reset belongs to the new epoch and is live.
  const next = guard.begin();
  assert.equal(next.isCurrent(), true);
  assert.notEqual(next.epoch, scope.epoch);
});

/* ----------------------------------------------------- OpenUI mapping ---- */

const Answer = defineComponent({
  name: "Answer",
  description: "test double for the registered Answer component",
  props: answerPropsSchema,
  component: () => null,
});
const library = createLibrary({ root: "Answer", components: [Answer] });
const parser = createParser(library.toJSONSchema(), library.root);

test("answerProgram resolves to exactly one Answer element carrying the result id", () => {
  const parsed = parser.parse(answerProgram("res-1"));
  assert.deepEqual(parsed.meta.errors, []);
  assert.equal(parsed.meta.statementCount, 1);
  assert.equal(parsed.root.typeName, "Answer");
  assert.equal(parsed.root.props.resultId, "res-1");
});

test("an id containing quotes and program syntax stays a single literal argument", () => {
  const hostile = 'res-1") other = Answer("x';
  const parsed = parser.parse(answerProgram(hostile));
  assert.deepEqual(parsed.meta.errors, []);
  assert.equal(parsed.meta.statementCount, 1);
  assert.equal(parsed.root.typeName, "Answer");
  assert.equal(parsed.root.props.resultId, hostile);
});

test("a non-string result id is a type error, not a rendered answer", () => {
  const parsed = parser.parse("root = Answer(42)");
  assert.equal(parsed.meta.errors.length, 1);
  assert.equal(parsed.meta.errors[0].code, "type-mismatch");
});

/* ---------------------------------------------------------- turn pairing -- */

test("buildTurns pairs a question with the envelope whose question matches", () => {
  const e = envelope({ result_id: "r1", question: "Q1" });
  const turns = buildTurns(
    [
      { id: "u1", role: "user", content: "Q1", created_at: "" },
      { id: "a1", role: "assistant", content: "server text", created_at: "" },
    ],
    [e],
  );
  assert.deepEqual(turns, [
    { kind: "question", key: "u1", content: "Q1" },
    { kind: "answer", key: "r1", resultId: "r1" },
  ]);
});

test("buildTurns shows the server text verbatim when no envelope matches the question", () => {
  const e = envelope({ result_id: "r1", question: "A different question" });
  const turns = buildTurns(
    [
      { id: "u1", role: "user", content: "Q1", created_at: "" },
      { id: "a1", role: "assistant", content: "the server said this", created_at: "" },
    ],
    [e],
  );
  assert.deepEqual(turns, [
    { kind: "question", key: "u1", content: "Q1" },
    { kind: "note", key: "a1", content: "the server said this" },
    { kind: "answer", key: "r1", resultId: "r1" },
  ]);
});

test("buildTurns appends an envelope that has no assistant message yet", () => {
  const e = envelope({ result_id: "r9", question: "Q9" });
  const turns = buildTurns([{ id: "u9", role: "user", content: "Q9", created_at: "" }], [e]);
  assert.deepEqual(turns, [
    { kind: "question", key: "u9", content: "Q9" },
    { kind: "answer", key: "r9", resultId: "r9" },
  ]);
});
