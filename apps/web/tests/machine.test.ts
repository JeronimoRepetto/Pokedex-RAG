/** The device's state machine: pure functions, no DOM, no fetch. */

import { describe, expect, it } from 'vitest';
import {
  initialState,
  reducer,
  selectProviderComparison,
  statusLine,
  toMatchRefs,
  type PokedexState,
} from '@/lib/pokedexMachine';
import { ANSWERED, COMPARISON, IMAGE_MATCHES, MATCHUP, PIKACHU } from './fixtures';

const begin = (state: PokedexState) =>
  reducer(state, { type: 'BEGIN', op: 'card', label: 'loading', seq: state.seq + 1 });

describe('initial state and deep links', () => {
  it('starts empty by default and on the card for a deep link', () => {
    expect(initialState().screen).toEqual({ kind: 'empty' });
    expect(initialState({ card: '25' }).screen).toEqual({ kind: 'card', ref: '25' });
  });
});

describe('sequencing', () => {
  it('drops results stamped with a stale seq', () => {
    let state = begin(initialState()); // seq 1
    state = begin(state); // seq 2 supersedes 1

    const stale = reducer(state, {
      type: 'CARD_LOADED',
      seq: 1,
      ref: '25',
      card: PIKACHU,
    });

    expect(stale.screen.kind).toBe('empty');
    expect(stale.activity.kind).toBe('busy');
  });

  it('applies results from the current seq', () => {
    const state = reducer(begin(initialState()), {
      type: 'CARD_LOADED',
      seq: 1,
      ref: '25',
      card: PIKACHU,
    });

    expect(state.screen).toEqual({ kind: 'card', ref: '25' });
    expect(state.activity.kind).toBe('idle');
    expect(state.cards['25']).toBe(PIKACHU);
  });
});

describe('failure behaviour', () => {
  it('a failure never blanks the screen', () => {
    let state = reducer(begin(initialState()), {
      type: 'CARD_LOADED',
      seq: 1,
      ref: '25',
      card: PIKACHU,
    });
    state = begin(state);

    state = reducer(state, {
      type: 'FAILED',
      seq: 2,
      op: 'question',
      error: new Error('boom'),
    });

    expect(state.screen).toEqual({ kind: 'card', ref: '25' }); // untouched
    expect(state.activity).toMatchObject({ kind: 'failed', op: 'question' });
    expect(statusLine(state)).toBe('ERROR');
  });

  it('dismissing the error returns to idle without touching the screen', () => {
    let state = reducer(begin(initialState()), {
      type: 'FAILED',
      seq: 1,
      op: 'card',
      error: 'x',
    });

    state = reducer(state, { type: 'DISMISS_ERROR' });

    expect(state.activity.kind).toBe('idle');
  });
});

describe('the match carousel', () => {
  const withMatches = () =>
    reducer(begin(initialState()), {
      type: 'MATCHES_LOADED',
      seq: 1,
      refs: toMatchRefs(IMAGE_MATCHES.results),
    });

  it('dedupes documents into one entry per Pokémon, best score first', () => {
    const refs = toMatchRefs(IMAGE_MATCHES.results);

    expect(refs).toHaveLength(2); // bulbasaur appears twice in the raw hits
    expect(refs[0]).toMatchObject({ pokemonId: 1, score: 0.99 });
    expect(refs[1]).toMatchObject({ pokemonId: 25 });
  });

  it('starts at the first match and switches the phone to the display panel', () => {
    const state = withMatches();

    expect(state.screen).toMatchObject({ kind: 'matches', index: 0 });
    expect(state.panel).toBe('left');
    expect(statusLine(state)).toBe('1 OF 2');
  });

  it('steps clamp at both ends instead of wrapping', () => {
    let state = withMatches();

    state = reducer(state, { type: 'STEP', delta: -1 });
    expect(state.screen).toMatchObject({ index: 0 });

    state = reducer(state, { type: 'STEP', delta: 1 });
    state = reducer(state, { type: 'STEP', delta: 1 });
    expect(state.screen).toMatchObject({ index: 1 }); // clamped at the last match
  });
});

describe('the provider comparison panel is derived, never stored', () => {
  it('exists only when the verdict came from /compare', () => {
    const single = reducer(begin(initialState()), {
      type: 'ANSWER_LOADED',
      seq: 1,
      question: 'q',
      verdict: { kind: 'single', response: ANSWERED },
    });
    const compared = reducer(begin(initialState()), {
      type: 'ANSWER_LOADED',
      seq: 1,
      question: 'q',
      verdict: { kind: 'compared', response: COMPARISON },
    });

    expect(selectProviderComparison(single)).toBeNull();
    expect(selectProviderComparison(compared)).toBe(COMPARISON);
  });

  it('is structurally impossible for cards and image matches', () => {
    const card = reducer(begin(initialState()), {
      type: 'CARD_LOADED',
      seq: 1,
      ref: '25',
      card: PIKACHU,
    });

    expect(selectProviderComparison(card)).toBeNull();
  });

  it('works for a versus verdict too', () => {
    const versus = reducer(begin(initialState()), {
      type: 'VERSUS_LOADED',
      seq: 1,
      matchup: MATCHUP,
      verdict: { kind: 'compared', response: COMPARISON },
    });

    expect(selectProviderComparison(versus)).toBe(COMPARISON);
    expect(statusLine(versus)).toBe('VERSUS');
  });
});

describe('input and toggle', () => {
  it('a successful answer clears the input; a failure preserves it', () => {
    let state = reducer(initialState(), { type: 'SET_INPUT', value: 'what type is gengar?' });
    state = begin(state);

    const failed = reducer(state, { type: 'FAILED', seq: 1, op: 'question', error: 'x' });
    expect(failed.input).toBe('what type is gengar?'); // the user can retry or edit

    const answered = reducer(state, {
      type: 'ANSWER_LOADED',
      seq: 1,
      question: 'q',
      verdict: { kind: 'single', response: ANSWERED },
    });
    expect(answered.input).toBe('');
  });

  it('the A/B toggle flips freely', () => {
    const state = reducer(initialState(), { type: 'TOGGLE_COMPARE' });

    expect(state.compareMode).toBe(true);
  });
});
