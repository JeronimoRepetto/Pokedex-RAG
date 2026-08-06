'use client';

import { StatusBadge } from '@/components/Feedback';
import type { Citation } from '@/lib/types';

/**
 * Shared rendering for anything the RAG pipeline answers — /chat and each /compare
 * candidate. Everything the pipeline reports is surfaced: an abstention, a correction,
 * a judge warning and an unusable citation are all information the user should see,
 * not detail to hide behind a clean-looking answer.
 */
export function AnswerBody({
  status,
  answer,
  citations,
  warnings,
  correctionsApplied,
}: {
  status: string;
  answer: string | null;
  citations: Citation[];
  warnings: string[];
  correctionsApplied: number;
}) {
  return (
    <>
      <div className="row">
        <StatusBadge status={status} />
        {correctionsApplied > 0 ? (
          <span className="badge badge-warn">
            {correctionsApplied} correction{correctionsApplied > 1 ? 's' : ''} applied
          </span>
        ) : null}
      </div>

      {answer ? (
        <p className="answer">{answer}</p>
      ) : (
        <p className="muted answer">
          {status === 'insufficient_evidence'
            ? 'The assistant abstained: the retrieved documents did not support an answer.'
            : 'No answer was produced.'}
        </p>
      )}

      {citations.length > 0 ? (
        <>
          <div className="muted">Sources</div>
          <ul className="citation-list">
            {citations.map((citation) => (
              <li key={citation.marker}>
                <span className="mono">[{citation.marker}]</span>{' '}
                {citation.source_url ? (
                  <a href={citation.source_url} target="_blank" rel="noreferrer">
                    {citation.snippet ?? `document ${citation.document_id}`}
                  </a>
                ) : (
                  (citation.snippet ?? `document ${citation.document_id}`)
                )}
              </li>
            ))}
          </ul>
        </>
      ) : null}

      {warnings.length > 0 ? (
        <div className="stack" style={{ marginTop: '0.7rem' }}>
          {warnings.map((warning) => (
            <div className="notice" key={warning}>
              {warning}
            </div>
          ))}
        </div>
      ) : null}
    </>
  );
}
