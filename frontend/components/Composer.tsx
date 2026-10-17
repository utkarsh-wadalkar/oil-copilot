"use client";

import { PaperPlaneRight } from "@phosphor-icons/react";
import { BorderBeam } from "border-beam";
import { useCallback, useEffect, useRef, type ChangeEvent, type FormEvent, type KeyboardEvent } from "react";

import { usePrefersReducedMotion } from "@/lib/usePrefersReducedMotion";

/**
 * The chat composer.
 *
 * libraries.dev placement: `border-beam`, `size="line"`.
 * The reference files this under "an input that loads after the user submits
 * text (search, ask, command bar): `size="line"`, active from submit until
 * results arrive" and documents the chat-composer case for a long agent run.
 * `active` is driven by the real pending flag, and because the rotate types do
 * not handle reduced motion themselves, the reference's own `usePrefersReducedMotion`
 * pattern turns the beam off when the operator asks for less motion. The wait is
 * still announced: `aria-busy` on the form plus the visible status line.
 */
export function Composer({
  value,
  onChange,
  onSubmit,
  busy,
  ready,
  analysisDate,
  focusToken,
}: {
  value: string;
  onChange: (next: string) => void;
  onSubmit: () => void;
  busy: boolean;
  ready: boolean;
  analysisDate: string;
  /**
   * Bumped by the workspace when it wants the input focused (a starter question
   * was chosen, a thread was opened). Only a positive value focuses, so the
   * composer is not stolen into focus on first paint.
   */
  focusToken?: number;
}) {
  const reducedMotion = usePrefersReducedMotion();
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!focusToken) return;
    inputRef.current?.focus();
  }, [focusToken]);

  const canSend = ready && !busy && value.trim().length > 0;
  const send = useCallback(() => {
    if (!canSend) return;
    onSubmit();
    inputRef.current?.focus();
  }, [canSend, onSubmit]);

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key !== "Enter" || event.shiftKey) return;
    if (event.nativeEvent.isComposing) return;
    event.preventDefault();
    send();
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    send();
  };

  const handleChange = (event: ChangeEvent<HTMLTextAreaElement>) => onChange(event.target.value);

  return (
    <>
      <BorderBeam size="line" colorVariant="mono" theme="light" strength={0.9} active={busy && !reducedMotion}>
        <form className="composer" onSubmit={handleSubmit} aria-busy={busy}>
          <div className="composer__field">
            <label className="sr-only" htmlFor="composer-input">
              Ask about the wells in this dataset
            </label>
            <textarea
              id="composer-input"
              ref={inputRef}
              className="composer__input"
              rows={2}
              value={value}
              onChange={handleChange}
              onKeyDown={handleKeyDown}
              placeholder={
                ready ? "Ask about well status, downtime, spills or compliance" : "Choose a dataset user first"
              }
              disabled={!ready || busy}
            />
          </div>
          <div className="composer__actions">
            <button type="submit" className="button button--primary button--cta" disabled={!canSend}>
              <span className="button__label">Send</span>
              <span className="button__orb" aria-hidden="true">
                <PaperPlaneRight size={14} weight="regular" />
              </span>
            </button>
          </div>
        </form>
      </BorderBeam>
      <p className="composer__hint">
        <kbd>Enter</kbd> sends, <kbd>Shift</kbd>+<kbd>Enter</kbd> starts a new line. Answers use the analysis date{" "}
        <span className="answer__meta-code">{analysisDate}</span>.
        {busy ? (
          <span role="status"> Waiting for the backend answer before another question can be sent.</span>
        ) : null}
      </p>
    </>
  );
}
