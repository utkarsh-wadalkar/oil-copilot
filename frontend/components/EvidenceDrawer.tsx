"use client";

import { ArrowClockwise, FileText, X } from "@phosphor-icons/react";

import { API_BASE_URL } from "@/lib/api";
import type { EvidenceState } from "@/lib/session";

/**
 * The evidence drawer.
 *
 * It lists the citations carried by one answer envelope, and when a citation is
 * opened it fetches that one source through `GET /evidence/{id:path}`. The
 * fetched payload is a server-built `EvidenceRef`, so what is shown is the
 * server's own excerpt and line range, never a client-side re-slice of an
 * excerpt the answer already carried.
 *
 * The analysis date is labelled as the answer's evaluation date rather than a
 * date of the source file: `EvidenceRef` carries no source date, and inventing
 * one would be a lie about provenance.
 */
export function EvidenceDrawer({
  state,
  onSelect,
  onRetry,
  onClose,
}: {
  state: EvidenceState;
  onSelect: (evidenceId: string) => void;
  onRetry: () => void;
  onClose: () => void;
}) {
  const selectedRef = state.refs.find((ref) => ref.id === state.selectedId) ?? null;
  const fetchPath = `/evidence/${state.selectedId.split(":").map(encodeURIComponent).join(":")}`;

  return (
    <aside className="drawer" aria-label="Evidence">
      <div className="drawer__head">
        <div className="drawer__titles">
          <p className="drawer__title">Evidence</p>
          <p className="drawer__subtitle">
            {state.refs.length} source reference{state.refs.length === 1 ? "" : "s"} for “{state.answerQuestion}”
          </p>
          <p className="drawer__subtitle">
            Answer date <span className="answer__meta-code">{state.analysisDate}</span>
          </p>
        </div>
        <button type="button" className="button button--quiet" onClick={onClose} aria-label="Close evidence">
          <X size={16} weight="regular" aria-hidden="true" />
        </button>
      </div>

      <div className="drawer__body">
        <ul className="evidence-list">
          {state.refs.map((ref) => (
            <li key={ref.id}>
              <button
                type="button"
                className="evidence-item"
                aria-current={ref.id === state.selectedId}
                onClick={() => onSelect(ref.id)}
              >
                <span className="evidence-item__title">{ref.title}</span>
                <span className="evidence-item__path">{ref.path}</span>
                <span className="answer__meta-code">
                  record {ref.record_id ?? "not recorded"} · lines{" "}
                  {ref.start_line === null ? "not recorded" : `${ref.start_line}-${ref.end_line ?? ref.start_line}`}
                </span>
                <span className="evidence-item__excerpt">{ref.excerpt}</span>
              </button>
            </li>
          ))}
        </ul>

        <div className="evidence-detail">
          <p className="section__title">
            <FileText size={13} weight="regular" aria-hidden="true" /> {selectedRef ? selectedRef.title : "Source"}
          </p>

          {state.status === "loading" ? (
            <div className="stack" aria-hidden="true">
              <div className="skeleton skeleton--line" />
              <div className="skeleton skeleton--block" />
            </div>
          ) : null}

          {state.status === "error" ? (
            <div className="error-state">
              <p className="error-state__title">Could not fetch this source</p>
              <p>{state.error}</p>
              <button type="button" className="button" onClick={onRetry}>
                <ArrowClockwise size={15} weight="regular" aria-hidden="true" />
                Retry
              </button>
            </div>
          ) : null}

          {state.status === "ready" && state.source ? (
            <>
              <dl className="record">
                <div className="record__row">
                  <dt className="record__key">path</dt>
                  <dd className="record__value">{state.source.path}</dd>
                </div>
                <div className="record__row">
                  <dt className="record__key">record</dt>
                  <dd className="record__value">{state.source.record_id ?? "not recorded"}</dd>
                </div>
                <div className="record__row">
                  <dt className="record__key">lines</dt>
                  <dd className="record__value">
                    {state.source.start_line === null
                      ? "not recorded"
                      : `${state.source.start_line}-${state.source.end_line ?? state.source.start_line}`}
                  </dd>
                </div>
                <div className="record__row">
                  <dt className="record__key">source</dt>
                  <dd className="record__value">{state.source.source_id}</dd>
                </div>
                <div className="record__row">
                  <dt className="record__key">evaluated for</dt>
                  <dd className="record__value">
                    {state.analysisDate} <span className="answer__meta-code">(answer date, not a source date)</span>
                  </dd>
                </div>
                <div className="record__row">
                  <dt className="record__key">fetched</dt>
                  <dd className="record__value">
                    <span className="answer__meta-code">
                      GET {API_BASE_URL}
                      {fetchPath}
                    </span>
                  </dd>
                </div>
              </dl>
              <pre className="evidence-detail__excerpt">{state.source.excerpt}</pre>
            </>
          ) : null}

          {state.status === "idle" ? <p className="empty-state">Select a reference to fetch its source.</p> : null}
        </div>
      </div>
    </aside>
  );
}
