'use client';

import { useState } from 'react';
import { AnswerBody } from '@/components/AnswerCard';
import { ErrorBox, Loading } from '@/components/Feedback';
import { compare } from '@/lib/api';
import type { CompareCandidate, CompareResponse } from '@/lib/types';

function JudgeVerdict({ candidate }: { candidate: CompareCandidate }) {
  if (!candidate.judge) {
    return <span className="badge">unjudged</span>;
  }
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

export default function ComparePage() {
  const [question, setQuestion] = useState('');
  const [result, setResult] = useState<CompareResponse | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function run(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (trimmed.length < 3) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await compare(trimmed));
    } catch (caught) {
      setError(caught);
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Provider comparison</h1>
      <p className="subtitle">
        One retrieval, one prompt, two models. Because both providers receive the identical
        context, any difference below is a difference between the models — not between two
        pipelines.
      </p>

      <form className="row" onSubmit={run}>
        <input
          type="text"
          className="grow"
          placeholder="e.g. what type is Gengar and what is it weak to?"
          aria-label="Question to compare"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          maxLength={500}
        />
        <button type="submit" disabled={busy || question.trim().length < 3}>
          Compare
        </button>
      </form>

      {busy ? <Loading label="Generating with every provider and judging each…" /> : null}
      <ErrorBox error={error} />

      {result && !busy ? (
        <>
          <p className="muted" style={{ marginTop: '1rem' }}>
            Shared context: {result.context_document_ids.length} document(s) (
            <span className="mono">{result.context_document_ids.join(', ')}</span>),{' '}
            {result.context_chars} characters · request{' '}
            <span className="mono">{result.request_id}</span>
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
                  <JudgeVerdict candidate={candidate} />
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
        </>
      ) : null}

      {!result && !busy && !error ? (
        <p className="muted" style={{ marginTop: '1.5rem' }}>
          Ask a question to compare the configured providers side by side.
        </p>
      ) : null}
    </>
  );
}
