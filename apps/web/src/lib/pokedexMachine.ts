/**
 * The Pokédex device's state machine. Pure: no React, no fetch, no timers — every
 * transition is a plain function call, which is what makes the device's behaviour
 * exhaustively testable offline.
 *
 * Two independent axes instead of one enum:
 * - `screen` is WHAT THE LEFT DISPLAY SHOWS. It only changes when new content arrives.
 * - `activity` is WHAT THE DEVICE IS DOING. Busy/failed live here.
 *
 * The invariant that split them: a failure must never blank the screen. Real hardware
 * keeps its display and lights an error lamp; a single enum forces choosing between
 * blanking on load and a combinatorial explosion of loading-while-showing states.
 *
 * Naming note: `versus` = two Pokémon compared (the user-facing feature);
 * `providerComparison` = the /compare LLM A/B (the lab feature). They are unrelated,
 * and calling either of them just "compare" is how they end up cross-wired.
 */

import type {
  CompareResponse,
  MatchupResponse,
  PokemonCard,
  RAGResponse,
  SearchResult,
} from './types';

export type Verdict =
  { kind: 'single'; response: RAGResponse } | { kind: 'compared'; response: CompareResponse };

export interface MatchRef {
  pokemonId: number;
  name: string;
  score: number;
}

export type Screen =
  | { kind: 'empty' }
  | { kind: 'card'; ref: string }
  | { kind: 'matches'; refs: MatchRef[]; index: number }
  | { kind: 'answer'; question: string; verdict: Verdict }
  | { kind: 'versus'; matchup: MatchupResponse; verdict: Verdict | null };

export type OpKind = 'intent' | 'card' | 'image' | 'question' | 'versus';

export type Activity =
  | { kind: 'idle' }
  | { kind: 'busy'; op: OpKind; label: string }
  | { kind: 'failed'; op: OpKind; error: unknown };

export interface PokedexState {
  screen: Screen;
  activity: Activity;
  input: string;
  /** The provider A/B toggle. A preference — always settable, only read by LLM ops. */
  compareMode: boolean;
  /** Mobile: which panel is visible. Desktop CSS shows both and ignores it. */
  panel: 'left' | 'right';
  cards: Record<string, PokemonCard>;
  /** Async generation counter: results stamped with an older seq are stale. */
  seq: number;
}

export type PokedexAction =
  | { type: 'SET_INPUT'; value: string }
  | { type: 'TOGGLE_COMPARE' }
  | { type: 'SET_PANEL'; panel: 'left' | 'right' }
  | { type: 'DISMISS_ERROR' }
  | { type: 'BEGIN'; op: OpKind; label: string; seq: number }
  | { type: 'CARD_LOADED'; seq: number; ref: string; card: PokemonCard }
  | { type: 'MATCHES_LOADED'; seq: number; refs: MatchRef[] }
  | { type: 'STEP'; delta: 1 | -1 }
  | { type: 'ANSWER_LOADED'; seq: number; question: string; verdict: Verdict }
  | {
      type: 'VERSUS_LOADED';
      seq: number;
      matchup: MatchupResponse;
      verdict: Verdict | null;
    }
  | { type: 'CACHE_CARD'; card: PokemonCard }
  | { type: 'FAILED'; seq: number; op: OpKind; error: unknown };

export function initialState(deepLink?: { card?: string }): PokedexState {
  // Deterministic on purpose: this runs during prerender of 152 static pages, so any
  // Date.now()/random here would be a hydration mismatch on every one of them.
  return {
    screen: deepLink?.card ? { kind: 'card', ref: deepLink.card } : { kind: 'empty' },
    activity: { kind: 'idle' },
    input: '',
    compareMode: false,
    panel: 'right',
    cards: {},
    seq: 0,
  };
}

const clamp = (value: number, max: number) => Math.min(Math.max(value, 0), max);

export function reducer(state: PokedexState, action: PokedexAction): PokedexState {
  switch (action.type) {
    case 'SET_INPUT':
      return { ...state, input: action.value };
    case 'TOGGLE_COMPARE':
      return { ...state, compareMode: !state.compareMode };
    case 'SET_PANEL':
      return { ...state, panel: action.panel };
    case 'DISMISS_ERROR':
      return state.activity.kind === 'failed'
        ? { ...state, activity: { kind: 'idle' } }
        : state;
    case 'BEGIN':
      // The CALLER allocates seq (from a synchronous counter) and BEGIN carries it.
      // Deriving it here as state.seq + 1 breaks under React StrictMode's double
      // effects: two BEGINs dispatch before any render, both callers read the same
      // pre-dispatch seq, and every response gets dropped as stale — found live.
      return {
        ...state,
        seq: action.seq,
        activity: { kind: 'busy', op: action.op, label: action.label },
      };
    case 'CARD_LOADED': {
      if (action.seq !== state.seq) return state;
      return {
        ...state,
        screen: { kind: 'card', ref: action.ref },
        activity: { kind: 'idle' },
        input: '',
        panel: 'left', // results auto-switch the phone to the display panel
        cards: { ...state.cards, [action.ref]: action.card },
      };
    }
    case 'MATCHES_LOADED': {
      if (action.seq !== state.seq) return state;
      return {
        ...state,
        screen: { kind: 'matches', refs: action.refs, index: 0 },
        activity: { kind: 'idle' },
        panel: 'left',
      };
    }
    case 'STEP': {
      if (state.screen.kind !== 'matches') return state;
      const index = clamp(state.screen.index + action.delta, state.screen.refs.length - 1);
      return { ...state, screen: { ...state.screen, index } };
    }
    case 'ANSWER_LOADED': {
      if (action.seq !== state.seq) return state;
      return {
        ...state,
        screen: { kind: 'answer', question: action.question, verdict: action.verdict },
        activity: { kind: 'idle' },
        input: '',
        panel: 'left',
      };
    }
    case 'VERSUS_LOADED': {
      if (action.seq !== state.seq) return state;
      return {
        ...state,
        screen: { kind: 'versus', matchup: action.matchup, verdict: action.verdict },
        activity: { kind: 'idle' },
        input: '',
        panel: 'left',
      };
    }
    case 'CACHE_CARD':
      return { ...state, cards: { ...state.cards, [String(action.card.id)]: action.card } };
    case 'FAILED': {
      if (action.seq !== state.seq) return state;
      // Only the activity changes — the screen keeps whatever it was showing.
      return { ...state, activity: { kind: 'failed', op: action.op, error: action.error } };
    }
    default:
      return state;
  }
}

/**
 * The provider A/B panel below the chassis is DERIVED, never stored: it exists exactly
 * when the current screen's verdict came from /compare. Structurally impossible to
 * show it for a card or image lookup, which is the requirement.
 */
export function selectProviderComparison(state: PokedexState): CompareResponse | null {
  const verdict =
    state.screen.kind === 'answer' || state.screen.kind === 'versus'
      ? state.screen.verdict
      : null;
  return verdict?.kind === 'compared' ? verdict.response : null;
}

/** The status line on the device's screen — short, uppercase, announceable. */
export function statusLine(state: PokedexState): string {
  if (state.activity.kind === 'busy') return state.activity.label.toUpperCase();
  if (state.activity.kind === 'failed') return 'ERROR';
  switch (state.screen.kind) {
    case 'empty':
      return 'READY';
    case 'card':
      return `#${state.screen.ref}`.toUpperCase();
    case 'matches':
      return `${state.screen.index + 1} OF ${state.screen.refs.length}`;
    case 'answer':
      return 'ANSWER';
    case 'versus':
      return 'VERSUS';
  }
}

/** Dedupe raw search hits (documents) into one entry per Pokémon, best score first. */
export function toMatchRefs(results: SearchResult[]): MatchRef[] {
  const best = new Map<number, MatchRef>();
  for (const hit of results) {
    const existing = best.get(hit.pokemon_id);
    if (!existing || hit.score > existing.score) {
      best.set(hit.pokemon_id, {
        pokemonId: hit.pokemon_id,
        name: hit.pokemon_name,
        score: hit.score,
      });
    }
  }
  return [...best.values()].toSorted((a, b) => b.score - a.score);
}
