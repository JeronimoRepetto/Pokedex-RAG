'use client';

import Link from 'next/link';
import { spriteUrl } from '@/lib/api';
import type { SearchResult } from '@/lib/types';

export function SearchResults({ results }: { results: SearchResult[] }) {
  if (results.length === 0) {
    return <p className="muted">No matches.</p>;
  }
  return (
    <ul className="results">
      {results.map((result) => (
        <li key={`${result.doc_type}-${result.document_id}`}>
          <Link className="result-item" href={`/pokemon/${result.pokemon_id}/`}>
            {/* Plain <img>: static export has no image optimizer, and a broken sprite
                must not break the row — hide it and keep the text. */}
            <img
              src={spriteUrl(result.pokemon_id)}
              alt=""
              loading="lazy"
              onError={(event) => {
                event.currentTarget.style.visibility = 'hidden';
              }}
            />
            <span className="grow">
              <strong style={{ textTransform: 'capitalize' }}>{result.pokemon_name}</strong>
              <span className="muted"> #{result.pokemon_id}</span>
              <br />
              <span className="muted">{result.title}</span>
            </span>
            <span className="badge">{result.doc_type}</span>
            <span className="mono muted">{result.score.toFixed(4)}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
