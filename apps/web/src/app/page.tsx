'use client';

import { useState } from 'react';
import { ImageDropzone } from '@/components/ImageDropzone';
import { ErrorBox, Loading } from '@/components/Feedback';
import { SearchResults } from '@/components/SearchResults';
import { searchImage, searchText } from '@/lib/api';
import type { SearchMode, SearchResponse } from '@/lib/types';

const MODES: SearchMode[] = ['hybrid', 'vector', 'lexical'];

export default function SearchPage() {
  const [query, setQuery] = useState('');
  const [mode, setMode] = useState<SearchMode>('hybrid');
  const [space, setSpace] = useState('');
  const [response, setResponse] = useState<SearchResponse | null>(null);
  const [busy, setBusy] = useState<'text' | 'image' | null>(null);
  const [error, setError] = useState<unknown>(null);

  async function run(kind: 'text' | 'image', call: () => Promise<SearchResponse>) {
    setBusy(kind);
    setError(null);
    try {
      setResponse(await call());
    } catch (caught) {
      setError(caught);
      setResponse(null);
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <h1>Search</h1>
      <p className="subtitle">
        Hybrid retrieval over Gen-1 documents (vector + full-text, fused with RRF), or
        image-to-image matching against sprite vectors.
      </p>

      <form
        className="stack"
        onSubmit={(event) => {
          event.preventDefault();
          if (query.trim().length >= 2) {
            void run('text', () =>
              searchText({
                query: query.trim(),
                mode,
                space: space || undefined,
              }),
            );
          }
        }}
      >
        <div className="row">
          <input
            type="search"
            className="grow"
            placeholder="e.g. which pokemon has a plant bulb on its back"
            aria-label="Search query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            minLength={2}
          />
          <button type="submit" disabled={busy !== null || query.trim().length < 2}>
            Search
          </button>
        </div>
        <div className="row">
          <label className="muted">
            Mode{' '}
            <select
              value={mode}
              aria-label="Search mode"
              onChange={(event) => setMode(event.target.value as SearchMode)}
            >
              {MODES.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
          <label className="muted">
            Embedding space{' '}
            <select
              value={space}
              aria-label="Embedding space"
              onChange={(event) => setSpace(event.target.value)}
            >
              <option value="">default (gemini-embedding-2)</option>
              <option value="embeddinggemma-768-v1">embeddinggemma-768-v1 (local)</option>
            </select>
          </label>
        </div>
      </form>

      <h2>Search by image</h2>
      <ImageDropzone
        disabled={busy !== null}
        onFile={(file) => void run('image', () => searchImage(file))}
      />

      <h2>Results</h2>
      {busy ? <Loading label={busy === 'image' ? 'Matching sprite…' : 'Searching…'} /> : null}
      <ErrorBox error={error} />
      {response && !busy ? (
        <>
          <p className="muted">
            mode <strong>{response.mode}</strong>
            {response.space ? (
              <>
                {' '}
                · space <strong>{response.space}</strong>
              </>
            ) : null}{' '}
            · {response.results.length} result(s)
          </p>
          <SearchResults results={response.results} />
        </>
      ) : null}
      {!response && !busy && !error ? (
        <p className="muted">Run a search to see results.</p>
      ) : null}
    </>
  );
}
