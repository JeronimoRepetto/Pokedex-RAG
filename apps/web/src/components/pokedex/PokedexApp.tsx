'use client';

import { useRef } from 'react';
import { ProviderComparison } from '@/components/ProviderComparison';
import { PausedNotice } from '@/components/pokedex/PausedNotice';
import { Screen } from '@/components/pokedex/Screen';
import { selectProviderComparison, statusLine } from '@/lib/pokedexMachine';
import { usePokedex } from '@/lib/usePokedex';

const ACCEPTED = 'image/png,image/jpeg,image/webp';

/**
 * The whole device. Every piece of chrome is either a real control or aria-hidden
 * decoration — nothing focusable does nothing. The chassis is an original CSS
 * interpretation (no franchise art asset; see the IP policy).
 */
export function PokedexApp({ deepLink }: { deepLink?: { card?: string } }) {
  const { state, actions, paused } = usePokedex(deepLink);
  const pickerRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const screenRef = useRef<HTMLDivElement>(null);
  const providerComparison = selectProviderComparison(state);
  const busy = state.activity.kind === 'busy';
  const isPaused = paused?.paused === true;

  // The d-pad's vertical buttons page the screen's content. `scrollBy` is optional-
  // chained because jsdom doesn't implement it; smoothness comes from the CSS
  // scroll-behavior rule, which reduced-motion users don't get.
  function scrollScreen(direction: 1 | -1) {
    const content = screenRef.current;
    content?.scrollBy?.({ top: direction * Math.round(content.clientHeight * 0.7) });
  }

  function acceptFile(file: File | undefined) {
    // Validation lives in usePokedex.submitImage so the rejection flows through the
    // machine like every other failure (and camera photos get downscaled there too).
    if (file) actions.submitImage(file);
  }

  const inMatches = state.screen.kind === 'matches';
  const atStart = inMatches && state.screen.kind === 'matches' && state.screen.index === 0;
  const atEnd =
    inMatches &&
    state.screen.kind === 'matches' &&
    state.screen.index >= state.screen.refs.length - 1;

  return (
    <>
      <h1 className="stage-title">Pokédex-RAG</h1>
      <div className={`pokedex panel-${state.panel}`}>
        {/* ---- left half: display ---- */}
        <section className="pokedex-left" aria-label="Display panel" data-panel="left">
          <div className="lens-row">
            <span className="lens" data-busy={busy} aria-hidden="true" />
            <span className="lamp lamp-red" aria-hidden="true" />
            <span className="lamp lamp-yellow" aria-hidden="true" />
            <span className="lamp lamp-green" aria-hidden="true" />
          </div>
          <div className="screen-bezel">
            <div className="screen">
              <output className="screen-status mono">
                {isPaused ? 'PAUSED · PAUSADO' : statusLine(state)}
              </output>
              {isPaused ? (
                <PausedNotice contact={paused?.contact ?? ''} />
              ) : (
                <Screen state={state} actions={actions} contentRef={screenRef} />
              )}
            </div>
            <div className="speaker" aria-hidden="true" />
          </div>
          <div className="left-controls">
            <span className="round-button" aria-hidden="true" />
            <fieldset className="dpad">
              <legend className="visually-hidden">
                Browse matches (left/right) and scroll the screen (up/down)
              </legend>
              <button
                type="button"
                className="dpad-button dpad-up"
                aria-label="Scroll the screen up"
                onClick={() => scrollScreen(-1)}
              >
                <span aria-hidden="true">▲</span>
              </button>
              <button
                type="button"
                className="dpad-button dpad-left"
                aria-label="Previous match"
                disabled={!inMatches || atStart}
                onClick={() => actions.step(-1)}
              >
                <span aria-hidden="true">◀</span>
              </button>
              <span className="dpad-center" aria-hidden="true" />
              <button
                type="button"
                className="dpad-button dpad-right"
                aria-label="Next match"
                disabled={!inMatches || atEnd}
                onClick={() => actions.step(1)}
              >
                <span aria-hidden="true">▶</span>
              </button>
              <button
                type="button"
                className="dpad-button dpad-down"
                aria-label="Scroll the screen down"
                onClick={() => scrollScreen(1)}
              >
                <span aria-hidden="true">▼</span>
              </button>
            </fieldset>
          </div>
        </section>

        {/* ---- hinge, with the mobile panel switch ---- */}
        <div className="hinge">
          <div className="hinge-tabs" role="tablist" aria-label="Pokédex panels">
            <button
              type="button"
              role="tab"
              aria-selected={state.panel === 'left'}
              tabIndex={state.panel === 'left' ? 0 : -1}
              onClick={() => actions.setPanel('left')}
              onKeyDown={(e) => {
                if (e.key === 'ArrowDown' || e.key === 'ArrowRight') actions.setPanel('right');
              }}
            >
              Display
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={state.panel === 'right'}
              tabIndex={state.panel === 'right' ? 0 : -1}
              onClick={() => actions.setPanel('right')}
              onKeyDown={(e) => {
                if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') actions.setPanel('left');
              }}
            >
              Console
            </button>
          </div>
          <span className="hinge-screw" aria-hidden="true" />
          <span className="hinge-screw" aria-hidden="true" />
        </div>

        {/* ---- right half: console ---- */}
        <section className="pokedex-right" aria-label="Console panel" data-panel="right">
          <div className="readout mono" aria-hidden="true">
            {state.input ? state.input.toUpperCase() : '···'}
          </div>
          <form
            className="stack"
            onSubmit={(event) => {
              event.preventDefault();
              actions.submitText();
            }}
          >
            <textarea
              aria-label="Ask the Pokédex"
              placeholder={'«Gengar» · «¿de qué tipo es Bulbasaur?» · «¿Pikachu vs Gengar?»'}
              value={state.input}
              rows={3}
              maxLength={500}
              onChange={(event) => actions.setInput(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && !event.shiftKey) {
                  event.preventDefault();
                  actions.submitText();
                }
              }}
            />
            <div className="row">
              <button
                type="submit"
                disabled={
                  isPaused ||
                  busy ||
                  (state.input.trim().length < 3 && !/^\d+$/.test(state.input.trim()))
                }
              >
                {busy ? 'Procesando…' : 'Enviar'}
              </button>
              <button
                type="button"
                className="secondary"
                disabled={isPaused || busy}
                onClick={() => pickerRef.current?.click()}
              >
                Imagen…
              </button>
              <button
                type="button"
                className="secondary camera-button"
                disabled={isPaused || busy}
                onClick={() => cameraRef.current?.click()}
              >
                Cámara
              </button>
            </div>
          </form>
          <input
            ref={pickerRef}
            type="file"
            accept={ACCEPTED}
            hidden
            data-testid="image-input"
            onChange={(event) => {
              acceptFile(event.target.files?.[0]);
              event.target.value = '';
            }}
          />
          {/* `capture` opens the phone camera directly; a separate input so choosing an
              existing screenshot stays possible via the picker button. */}
          <input
            ref={cameraRef}
            type="file"
            accept="image/*"
            capture="environment"
            hidden
            data-testid="camera-input"
            onChange={(event) => {
              acceptFile(event.target.files?.[0]);
              event.target.value = '';
            }}
          />

          <label className="ab-toggle">
            <input
              type="checkbox"
              role="switch"
              aria-checked={state.compareMode}
              checked={state.compareMode}
              onChange={actions.toggleCompare}
            />
            <span>
              Comparar proveedores (A/B)
              <span className="muted ab-hint">
                Solo aplica a respuestas generadas por IA; el detalle aparece debajo.
              </span>
            </span>
          </label>

          <div className="keypad" aria-hidden="true">
            {Array.from({ length: 10 }, (_, i) => (
              <span className="key" key={i} />
            ))}
          </div>
          <div className="console-bars" aria-hidden="true">
            <span className="bar bar-dark" />
            <span className="bar bar-dark" />
          </div>
        </section>
      </div>

      {providerComparison ? <ProviderComparison result={providerComparison} /> : null}
    </>
  );
}
