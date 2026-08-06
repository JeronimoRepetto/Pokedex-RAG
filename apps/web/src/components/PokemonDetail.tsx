'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { ErrorBox, Loading } from '@/components/Feedback';
import { getEvolutionChain, getPokemon, spriteUrl } from '@/lib/api';
import type { EvolutionChainResponse, PokemonCard } from '@/lib/types';

function describeTrigger(edge: EvolutionChainResponse['edges'][number]): string {
  if (edge.min_level) return `level ${edge.min_level}`;
  if (edge.item) return edge.item.replace(/-/g, ' ');
  return (edge.trigger ?? 'unknown').replace(/-/g, ' ');
}

export function PokemonDetail({ idOrName }: { idOrName: string }) {
  const [card, setCard] = useState<PokemonCard | null>(null);
  const [chain, setChain] = useState<EvolutionChainResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    // The chain is supporting detail: a card that loads must still render if the chain
    // call fails, so its rejection is swallowed into `null` rather than failing both.
    Promise.all([getPokemon(idOrName), getEvolutionChain(idOrName).catch(() => null)])
      .then(([loadedCard, loadedChain]) => {
        if (cancelled) return;
        setCard(loadedCard);
        setChain(loadedChain);
      })
      .catch((caught) => {
        if (!cancelled) setError(caught);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [idOrName]);

  if (loading) return <Loading label={`Loading ${idOrName}…`} />;
  if (error) {
    return (
      <>
        <ErrorBox error={error} />
        <p>
          <Link href="/">← Back to search</Link>
        </p>
      </>
    );
  }
  if (!card) return null;

  return (
    <>
      <div className="row" style={{ alignItems: 'flex-start', gap: '1.25rem' }}>
        <img
          src={spriteUrl(card.id)}
          alt={`${card.name} artwork`}
          width={180}
          height={180}
          style={{ objectFit: 'contain' }}
          onError={(event) => {
            event.currentTarget.style.display = 'none';
          }}
        />
        <div className="grow">
          <h1 style={{ textTransform: 'capitalize' }}>
            {card.name} <span className="muted">#{card.id}</span>
          </h1>
          <div className="row">
            {card.types.map((type) => (
              <span key={type.slot} className="badge">
                {type.name}
              </span>
            ))}
            {card.is_legendary ? <span className="badge badge-warn">legendary</span> : null}
            {card.is_mythical ? <span className="badge badge-warn">mythical</span> : null}
          </div>
          {card.flavor_text ? (
            <p style={{ marginBottom: 0 }}>{card.flavor_text.replace(/\s+/g, ' ')}</p>
          ) : null}
          <p className="muted">
            Generation {card.generation}
            {card.habitat ? ` · ${card.habitat}` : ''}
            {card.color ? ` · ${card.color}` : ''}
            {card.height_decimetres ? ` · ${(card.height_decimetres / 10).toFixed(1)} m` : ''}
            {card.weight_hectograms ? ` · ${(card.weight_hectograms / 10).toFixed(1)} kg` : ''}
          </p>
        </div>
      </div>

      <h2>Base stats</h2>
      <div className="stats-grid">
        {Object.entries(card.stats).map(([name, value]) => (
          <div className="stat" key={name}>
            <span className="muted">{name.replace(/-/g, ' ')}</span>
            <strong>{value}</strong>
          </div>
        ))}
      </div>

      <h2>Abilities</h2>
      <div className="row">
        {card.abilities.length === 0 ? (
          <span className="muted">None recorded.</span>
        ) : (
          card.abilities.map((ability) => (
            <span key={ability.name} className="badge">
              {ability.name.replace(/-/g, ' ')}
              {ability.is_hidden ? ' (hidden)' : ''}
            </span>
          ))
        )}
      </div>

      <h2>Evolution chain</h2>
      {chain && chain.edges.length > 0 ? (
        <div className="chain">
          {chain.edges.map((edge) => (
            <div
              className="chain-step card"
              key={`${edge.from_species.id}-${edge.to_species.id}`}
            >
              <Link
                href={`/pokemon/${edge.from_species.id}/`}
                style={{ textTransform: 'capitalize' }}
              >
                {edge.from_species.name}
              </Link>
              <span className="muted">→ {describeTrigger(edge)} →</span>
              <Link
                href={`/pokemon/${edge.to_species.id}/`}
                style={{ textTransform: 'capitalize' }}
              >
                {edge.to_species.name}
              </Link>
            </div>
          ))}
        </div>
      ) : (
        <p className="muted">
          {chain === null
            ? 'Evolution data could not be loaded.'
            : 'This Pokémon does not evolve.'}
        </p>
      )}

      <p style={{ marginTop: '2rem' }}>
        <Link href="/">← Back to search</Link>
      </p>
    </>
  );
}
