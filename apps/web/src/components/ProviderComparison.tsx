'use client';

import { AnswerBody } from '@/components/AnswerCard';
import type { CompareCandidate, CompareResponse } from '@/lib/types';

function JudgeVerdictView({ candidate }: { candidate: CompareCandidate }) {
  if (!candidate.judge) return <span className="badge">unjudged</span>;
  const { grounded, hallucination_detected, independent, reasoning } = candidate.judge;
  return (
    <div className="stack" style={{ gap: '0.3rem' }}>
      <div className="row">
        <span className={`badge ${grounded ? 'badge-ok' : 'badge-error'}`}>
          {grounded ? 'grounded' : 'ungrounded'}
        </span>
        {hallucination_detected ? (
          <span className="badge badge-error">hallucination</span>
        ) : null}
        {!independent ? <span className="badge badge-warn">self-graded</span> : null}
      </div>
      {reasoning ? <div className="muted">“{reasoning}”</div> : null}
      {!independent ? (
        <div className="muted">
          This provider is also the configured judge, so the verdict is not independent.
        </div>
      ) : null}
    </div>
  );
}

/**
 * The provider A/B lab. Renders BELOW the chassis, never inside it — it exists only
 * when the current answer came from /compare (see selectProviderComparison).
 */
export function ProviderComparison({ result }: { result: CompareResponse }) {
  return (
    <section aria-label="Provider comparison" className="stack" style={{ marginTop: '1.5rem' }}>
      <h2>Provider comparison</h2>
      <p className="muted">
        Same retrieved context for every provider ({result.context_document_ids.length}{' '}
        document(s): <span className="mono">{result.context_document_ids.join(', ')}</span>) ·
        request <span className="mono">{result.request_id}</span>
      </p>
      <div className="compare-grid">
        {result.candidates.map((candidate) => (
          <article className="card stack" key={candidate.provider}>
            <div>
              <strong>{candidate.provider}</strong>
              <div className="muted mono">{candidate.model || 'no model reported'}</div>
            </div>
            <AnswerBody
              status={candidate.status}
              answer={candidate.answer}
              citations={candidate.citations}
              warnings={candidate.warnings}
              correctionsApplied={candidate.corrections_applied}
            />
            <div>
              <div className="muted">Judge</div>
              <JudgeVerdictView candidate={candidate} />
            </div>
            <table>
              <tbody>
                <tr>
                  <th>Latency</th>
                  <td>{candidate.latency_ms} ms</td>
                </tr>
                <tr>
                  <th>Prompt tokens</th>
                  <td>{candidate.prompt_tokens}</td>
                </tr>
                <tr>
                  <th>Output tokens</th>
                  <td>{candidate.output_tokens}</td>
                </tr>
              </tbody>
            </table>
          </article>
        ))}
      </div>
    </section>
  );
}
