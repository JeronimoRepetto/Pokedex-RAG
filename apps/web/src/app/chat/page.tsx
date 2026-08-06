'use client';

import { useState } from 'react';
import { AnswerBody } from '@/components/AnswerCard';
import { ErrorBox, Loading } from '@/components/Feedback';
import { chat } from '@/lib/api';
import type { RAGResponse } from '@/lib/types';

interface Exchange {
  question: string;
  response: RAGResponse;
}

export default function ChatPage() {
  const [question, setQuestion] = useState('');
  const [history, setHistory] = useState<Exchange[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function ask(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = question.trim();
    if (trimmed.length < 3) return;
    setBusy(true);
    setError(null);
    try {
      const response = await chat(trimmed);
      // Newest first: the answer you just asked for should not require scrolling.
      setHistory((previous) => [{ question: trimmed, response }, ...previous]);
      setQuestion('');
    } catch (caught) {
      setError(caught);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Chat</h1>
      <p className="subtitle">
        Grounded answers over the Gen-1 corpus. Every claim is cited; the pipeline validates
        types against the database and a second model judges groundedness, so it will abstain
        rather than guess.
      </p>

      <form className="row" onSubmit={ask}>
        <input
          type="text"
          className="grow"
          placeholder="e.g. what advantages does Bulbasaur have against Squirtle?"
          aria-label="Question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          maxLength={500}
        />
        <button type="submit" disabled={busy || question.trim().length < 3}>
          Ask
        </button>
      </form>

      {busy ? <Loading label="Retrieving, generating and judging…" /> : null}
      <ErrorBox error={error} />

      {history.length === 0 && !busy ? (
        <p className="muted" style={{ marginTop: '1.5rem' }}>
          Ask something to see a grounded answer with its sources.
        </p>
      ) : null}

      <div className="stack" style={{ marginTop: '1.25rem' }}>
        {history.map((exchange) => (
          <article className="card stack" key={exchange.response.request_id}>
            <strong>{exchange.question}</strong>
            <AnswerBody
              status={exchange.response.status}
              answer={exchange.response.answer}
              citations={exchange.response.citations}
              warnings={exchange.response.warnings}
              correctionsApplied={exchange.response.corrections_applied}
            />
            <div className="mono muted">request {exchange.response.request_id}</div>
          </article>
        ))}
      </div>
    </>
  );
}
