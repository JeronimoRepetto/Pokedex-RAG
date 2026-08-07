'use client';

import { spriteUrl } from '@/lib/api';
import type { PokemonCard } from '@/lib/types';

/**
 * Presentational card, sized for the device's screen. No fetching: the machine hands
 * it a loaded card, so it renders identically inside the carousel, the card screen and
 * the versus split.
 */
export function CardView({ card, compact = false }: { card: PokemonCard; compact?: boolean }) {
  return (
    <article className="cardview">
      <header className="cardview-head">
        <img
          src={spriteUrl(card.id)}
          alt={`${card.name} artwork`}
          width={compact ? 72 : 110}
          height={compact ? 72 : 110}
          loading="lazy"
          onError={(event) => {
            event.currentTarget.style.visibility = 'hidden';
          }}
        />
        <div>
          <h2 className="cardview-name">
            {card.name} <span className="muted">#{card.id}</span>
          </h2>
          <div className="row">
            {card.types.map((type) => (
              <span key={type.slot} className="badge">
                {type.name}
              </span>
            ))}
            {card.is_legendary ? <span className="badge badge-warn">legendary</span> : null}
            {card.is_mythical ? <span className="badge badge-warn">mythical</span> : null}
          </div>
        </div>
      </header>

      {!compact && card.flavor_text ? (
        <p className="cardview-flavor">{card.flavor_text.replace(/\s+/g, ' ')}</p>
      ) : null}

      <dl className="cardview-stats">
        {Object.entries(card.stats).map(([name, value]) => (
          <div className="stat" key={name}>
            <dt className="muted">{name.replace(/-/g, ' ')}</dt>
            <dd>
              <strong>{value}</strong>
            </dd>
          </div>
        ))}
      </dl>

      {!compact ? (
        <p className="muted cardview-meta">
          Gen {card.generation}
          {card.habitat ? ` · ${card.habitat}` : ''}
          {card.height_decimetres != null
            ? ` · ${(card.height_decimetres / 10).toFixed(1)} m`
            : ''}
          {card.weight_hectograms != null
            ? ` · ${(card.weight_hectograms / 10).toFixed(1)} kg`
            : ''}
          {card.abilities.length > 0
            ? ` · ${card.abilities.map((a) => a.name.replace(/-/g, ' ')).join(', ')}`
            : ''}
        </p>
      ) : null}
    </article>
  );
}
