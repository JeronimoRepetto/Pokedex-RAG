'use client';

import { useEffect, useRef } from 'react';
import { AnswerBody } from '@/components/AnswerCard';
import { CardView } from '@/components/CardView';
import type { PokedexActions } from '@/lib/usePokedex';
import type { PokedexState, Screen as ScreenState } from '@/lib/pokedexMachine';
import type { MatchupResponse } from '@/lib/types';

function screenKey(screen: ScreenState): string {
  switch (screen.kind) {
    case 'card':
      return `card-${screen.ref}`;
    case 'matches':
      return `matches-${screen.refs.map((r) => r.pokemonId).join('-')}`;
    case 'answer':
      return `answer-${screen.question}`;
    case 'versus':
      return `versus-${screen.matchup.a.id}-${screen.matchup.b.id}`;
    default:
      return 'empty';
  }
}

function VersusInScreen({ matchup }: { matchup: MatchupResponse }) {
  const advantage =
    matchup.type_advantage === 'a'
      ? matchup.a.name
      : matchup.type_advantage === 'b'
        ? matchup.b.name
        : null;
  return (
    <div className="stack">
      <p className="versus-verdict">
        {advantage ? (
          <>
            <strong style={{ textTransform: 'capitalize' }}>{advantage}</strong> has the type
            advantage.
          </>
        ) : (
          'No type advantage either way.'
        )}
      </p>
      <div className="versus-grid">
        <CardView card={matchup.a} compact />
        <div className="versus-vs" aria-hidden="true">
          VS
        </div>
        <CardView card={matchup.b} compact />
      </div>
      <ul className="citation-list">
        {matchup.notes.map((note) => (
          <li key={note}>{note}</li>
        ))}
      </ul>
      <p className="muted">{matchup.disclaimer}</p>
    </div>
  );
}

export function Screen({ state, actions }: { state: PokedexState; actions: PokedexActions }) {
  const { screen, activity, cards } = state;
  const contentRef = useRef<HTMLDivElement>(null);
  const headingRef = useRef<HTMLDivElement>(null);
  const key = screenKey(screen);
  const previousKey = useRef(key);

  // When the screen's identity changes, reset scroll and move focus to the content so
  // keyboard/screen-reader users land on the result they just asked for.
  useEffect(() => {
    if (previousKey.current === key) return;
    previousKey.current = key;
    if (contentRef.current) contentRef.current.scrollTop = 0;
    headingRef.current?.focus({ preventScroll: true });
  }, [key]);

  const failed = activity.kind === 'failed';

  return (
    <div className="screen-content" ref={contentRef}>
      {/* Focus target: not in the tab order, focused programmatically on new results. */}
      <div ref={headingRef} tabIndex={-1} />
      {failed ? (
        <div className="alert" role="alert">
          {activity.error instanceof Error ? activity.error.message : String(activity.error)}
          <div>
            <button type="button" className="secondary" onClick={actions.dismissError}>
              OK
            </button>
          </div>
        </div>
      ) : null}

      {screen.kind === 'empty' ? (
        <p className="muted screen-hint">
          Escribe a la derecha — un nombre («Gengar»), una pregunta («¿de qué tipo es
          Bulbasaur?») o una comparación («¿Pikachu vs Gengar?») — o sube una imagen.
        </p>
      ) : null}

      {screen.kind === 'card' ? (
        cards[screen.ref] ? (
          <CardView card={cards[screen.ref]} />
        ) : (
          <p className="muted">Cargando #{screen.ref}…</p>
        )
      ) : null}

      {screen.kind === 'matches' ? (
        screen.refs.length === 0 ? (
          <p className="muted">Sin coincidencias.</p>
        ) : (
          <section aria-label="Image matches" className="stack">
            <p className="muted">
              <span aria-hidden="true">▸ </span>
              {screen.index + 1} of {screen.refs.length} ·{' '}
              <span style={{ textTransform: 'capitalize' }}>
                {screen.refs[screen.index].name}
              </span>{' '}
              <span className="mono">{screen.refs[screen.index].score.toFixed(3)}</span>
            </p>
            {cards[String(screen.refs[screen.index].pokemonId)] ? (
              <CardView card={cards[String(screen.refs[screen.index].pokemonId)]} />
            ) : (
              <p className="muted">Cargando ficha…</p>
            )}
          </section>
        )
      ) : null}

      {screen.kind === 'answer' ? (
        <div className="stack">
          <strong>{screen.question}</strong>
          {screen.verdict.kind === 'single' ? (
            <AnswerBody
              status={screen.verdict.response.status}
              answer={screen.verdict.response.answer}
              citations={screen.verdict.response.citations}
              warnings={screen.verdict.response.warnings}
              correctionsApplied={screen.verdict.response.corrections_applied}
            />
          ) : (
            // A/B mode: the screen shows the FIRST candidate, labelled with its
            // provider; the full grid renders below the chassis. One /compare call
            // feeds both — never a second retrieval for the same question.
            <>
              <span className="badge">{screen.verdict.response.candidates[0]?.provider}</span>
              {screen.verdict.response.candidates[0] ? (
                <AnswerBody
                  status={screen.verdict.response.candidates[0].status}
                  answer={screen.verdict.response.candidates[0].answer}
                  citations={screen.verdict.response.candidates[0].citations}
                  warnings={screen.verdict.response.candidates[0].warnings}
                  correctionsApplied={screen.verdict.response.candidates[0].corrections_applied}
                />
              ) : null}
              <p className="muted">Comparativa completa de proveedores debajo de la Pokédex.</p>
            </>
          )}
        </div>
      ) : null}

      {screen.kind === 'versus' ? (
        <div className="stack">
          <VersusInScreen matchup={screen.matchup} />
          {screen.verdict ? (
            <div className="stack">
              <h3 className="muted" style={{ margin: 0 }}>
                Análisis
              </h3>
              {screen.verdict.kind === 'single' ? (
                <AnswerBody
                  status={screen.verdict.response.status}
                  answer={screen.verdict.response.answer}
                  citations={screen.verdict.response.citations}
                  warnings={screen.verdict.response.warnings}
                  correctionsApplied={screen.verdict.response.corrections_applied}
                />
              ) : screen.verdict.response.candidates[0] ? (
                <>
                  <span className="badge">
                    {screen.verdict.response.candidates[0].provider}
                  </span>
                  <AnswerBody
                    status={screen.verdict.response.candidates[0].status}
                    answer={screen.verdict.response.candidates[0].answer}
                    citations={screen.verdict.response.candidates[0].citations}
                    warnings={screen.verdict.response.candidates[0].warnings}
                    correctionsApplied={
                      screen.verdict.response.candidates[0].corrections_applied
                    }
                  />
                </>
              ) : null}
            </div>
          ) : (
            <p className="muted">El análisis narrativo no está disponible ahora mismo.</p>
          )}
        </div>
      ) : null}
    </div>
  );
}
