'use client';

import { ApiError } from '@/lib/api';

/**
 * One place that decides how a failure is shown. Network-level failures (status 0) get
 * a "is the API running?" hint rather than a bare message, because that is by far the
 * most common local-development cause.
 */
export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  const apiError = error instanceof ApiError ? error : null;
  const message = error instanceof Error ? error.message : String(error);
  return (
    <div className="alert" role="alert">
      <div>{message}</div>
      {apiError?.status ? (
        <div className="muted" style={{ marginTop: '0.3rem' }}>
          HTTP {apiError.status}
          {apiError.requestId ? ` · request ${apiError.requestId}` : ''}
        </div>
      ) : null}
    </div>
  );
}

export function Loading({ label }: { label: string }) {
  // <output> carries an implicit `status` role, so assistive tech announces the change
  // without a hand-written role attribute.
  return (
    <output className="muted" style={{ display: 'block' }}>
      <span className="spinner" aria-hidden="true" /> {label}
    </output>
  );
}

/** Renders a RAG status as a colour-coded badge. */
export function StatusBadge({ status }: { status: string }) {
  const tone =
    status === 'answered'
      ? 'badge-ok'
      : status === 'provider_error'
        ? 'badge-error'
        : 'badge-warn';
  return <span className={`badge ${tone}`}>{status.replace(/_/g, ' ')}</span>;
}
