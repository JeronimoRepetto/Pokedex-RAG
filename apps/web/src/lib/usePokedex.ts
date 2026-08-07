'use client';

/**
 * The only file in the app that awaits API calls. Owns the intent → dispatch chain and
 * stamps every async result with the seq it was issued under, so the reducer can drop
 * stale responses (two fast submissions cannot land out of order).
 */

import { useCallback, useEffect, useReducer, useRef } from 'react';
import { chat, classifyIntent, compare, getMatchup, getPokemon, searchImage } from './api';
import { prepareImage, validateImage } from './image';
import {
  initialState,
  reducer,
  toMatchRefs,
  type OpKind,
  type PokedexState,
  type Verdict,
} from './pokedexMachine';
import type { IntentResponse } from './types';

export interface PokedexActions {
  setInput: (value: string) => void;
  toggleCompare: () => void;
  setPanel: (panel: 'left' | 'right') => void;
  dismissError: () => void;
  submitText: () => void;
  submitImage: (file: File) => void;
  showCard: (ref: string) => void;
  step: (delta: 1 | -1) => void;
}

/**
 * `/intent` classifies; failures degrade to `question` CLIENT-side too, so even an
 * unreachable classifier leaves the device able to answer.
 */
async function resolveIntent(question: string): Promise<IntentResponse> {
  try {
    return await classifyIntent(question);
  } catch {
    return {
      intent: 'question',
      entities: [],
      confidence: 0,
      method: 'fallback',
      warnings: ['intent service unreachable — treated as a question'],
    };
  }
}

export function usePokedex(deepLink?: { card?: string }) {
  const [state, dispatch] = useReducer(reducer, deepLink, initialState);
  const stateRef = useRef<PokedexState>(state);
  stateRef.current = state;
  // seq lives in a ref and is incremented SYNCHRONOUSLY: two begins in the same tick
  // (StrictMode double effects, double-click) get distinct numbers, and each caller
  // knows exactly which one is its own.
  const seqRef = useRef(0);

  const begin = useCallback((op: OpKind, label: string) => {
    const seq = ++seqRef.current;
    dispatch({ type: 'BEGIN', op, label, seq });
    return seq;
  }, []);

  const loadCard = useCallback(
    async (ref: string) => {
      const seq = begin('card', 'buscando ficha…');
      try {
        const card = await getPokemon(ref);
        dispatch({ type: 'CARD_LOADED', seq, ref: String(card.id), card });
      } catch (error) {
        dispatch({ type: 'FAILED', seq, op: 'card', error });
      }
    },
    [begin],
  );

  const askQuestion = useCallback(
    async (question: string) => {
      const seq = begin('question', 'consultando…');
      try {
        // A/B mode: ONE /compare call serves both the in-screen answer (primary
        // candidate) and the panel below — never /chat plus /compare, which would run
        // the whole RAG twice for the same question.
        const verdict: Verdict = stateRef.current.compareMode
          ? { kind: 'compared', response: await compare(question) }
          : { kind: 'single', response: await chat(question) };
        dispatch({ type: 'ANSWER_LOADED', seq, question, verdict });
      } catch (error) {
        dispatch({ type: 'FAILED', seq, op: 'question', error });
      }
    },
    [begin],
  );

  const runVersus = useCallback(
    async (question: string, a: string, b: string) => {
      const seq = begin('versus', 'comparando…');
      try {
        // The table is deterministic and instant; the narrative verdict is the slow,
        // paid part — fetch them together but tolerate the narrative failing alone.
        const matchupPromise = getMatchup(a, b);
        const verdictPromise: Promise<Verdict | null> = (
          stateRef.current.compareMode
            ? compare(question).then((response): Verdict => ({ kind: 'compared', response }))
            : chat(question).then((response): Verdict => ({ kind: 'single', response }))
        ).catch(() => null);
        const [matchup, verdict] = await Promise.all([matchupPromise, verdictPromise]);
        dispatch({ type: 'VERSUS_LOADED', seq, matchup, verdict });
      } catch (error) {
        dispatch({ type: 'FAILED', seq, op: 'versus', error });
      }
    },
    [begin],
  );

  const submitText = useCallback(async () => {
    const question = stateRef.current.input.trim();
    // Free local fast path FIRST: a bare number is a card, no /intent round-trip —
    // and ids 1..99 are shorter than the 3-character question minimum, so this must
    // not sit behind that guard.
    if (/^\d+$/.test(question)) {
      void loadCard(question);
      return;
    }
    if (question.length < 3) return;

    const seq = begin('intent', 'identificando…');
    const intent = await resolveIntent(question);
    if (seqRef.current !== seq) return; // a newer submission superseded this one

    if (intent.intent === 'card' && intent.entities.length > 0) {
      void loadCard(intent.entities[0].name);
    } else if (intent.intent === 'compare' && intent.entities.length >= 2) {
      void runVersus(question, intent.entities[0].name, intent.entities[1].name);
    } else {
      void askQuestion(question);
    }
  }, [begin, loadCard, askQuestion, runVersus]);

  const submitImage = useCallback(
    async (file: File) => {
      const seq = begin('image', 'analizando imagen…');
      try {
        // Camera photos get downscaled/re-encoded first (HEIC and >5MB both become
        // small JPEGs); validation runs on the PREPARED file, so a huge phone photo
        // passes instead of bouncing off the size limit.
        const prepared = await prepareImage(file);
        const problem = validateImage(prepared);
        if (problem) {
          dispatch({ type: 'FAILED', seq, op: 'image', error: new Error(problem) });
          return;
        }
        const response = await searchImage(prepared);
        dispatch({ type: 'MATCHES_LOADED', seq, refs: toMatchRefs(response.results) });
      } catch (error) {
        dispatch({ type: 'FAILED', seq, op: 'image', error });
      }
    },
    [begin],
  );

  // Carousel: make sure the card for the current index is loaded (cache hit = free).
  const screen = state.screen;
  useEffect(() => {
    if (screen.kind !== 'matches' || screen.refs.length === 0) return;
    const ref = String(screen.refs[screen.index].pokemonId);
    if (stateRef.current.cards[ref]) return;
    let cancelled = false;
    getPokemon(ref)
      .then((card) => {
        if (!cancelled) dispatch({ type: 'CACHE_CARD', card });
      })
      .catch(() => {
        // The carousel row still renders name + score; the card body shows a notice.
      });
    return () => {
      cancelled = true;
    };
  }, [screen]);

  // Deep link: /pokemon/25/ starts on that card and loads it on mount.
  useEffect(() => {
    if (deepLink?.card) void loadCard(deepLink.card);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- mount-only by design
  }, []);

  const actions: PokedexActions = {
    setInput: (value) => dispatch({ type: 'SET_INPUT', value }),
    toggleCompare: () => dispatch({ type: 'TOGGLE_COMPARE' }),
    setPanel: (panel) => dispatch({ type: 'SET_PANEL', panel }),
    dismissError: () => dispatch({ type: 'DISMISS_ERROR' }),
    submitText: () => void submitText(),
    submitImage: (file) => void submitImage(file),
    showCard: (ref) => void loadCard(ref),
    step: (delta) => dispatch({ type: 'STEP', delta }),
  };
  return { state, actions };
}
