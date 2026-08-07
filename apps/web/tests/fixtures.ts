/**
 * Deterministic fakes for the API's responses. Unit tests build every response from
 * these — no network, no running API (project guideline 5).
 */

import { vi } from 'vitest';
import type {
  CompareResponse,
  EvolutionChainResponse,
  IntentResponse,
  MatchupResponse,
  PokemonCard,
  RAGResponse,
  SearchResponse,
} from '@/lib/types';

export const BULBASAUR: PokemonCard = {
  id: 1,
  name: 'bulbasaur',
  generation: 1,
  color: 'green',
  habitat: 'grassland',
  is_legendary: false,
  is_mythical: false,
  height_decimetres: 7,
  weight_hectograms: 69,
  base_experience: 64,
  types: [
    { slot: 1, name: 'grass' },
    { slot: 2, name: 'poison' },
  ],
  abilities: [
    { name: 'overgrow', is_hidden: false },
    { name: 'chlorophyll', is_hidden: true },
  ],
  stats: { hp: 45, attack: 49, defense: 49 },
  flavor_text: 'A strange seed was planted on its back at birth.',
  sprite_kinds: ['default', 'official-artwork'],
};

export const CHAIN: EvolutionChainResponse = {
  chain_id: 1,
  edges: [
    {
      from_species: { id: 1, name: 'bulbasaur' },
      to_species: { id: 2, name: 'ivysaur' },
      trigger: 'level-up',
      min_level: 16,
      item: null,
    },
  ],
};

export const SEARCH_RESPONSE: SearchResponse = {
  mode: 'hybrid',
  space: 'gemini-embedding-2-768-v1',
  results: [
    {
      document_id: 1,
      pokemon_id: 1,
      pokemon_name: 'bulbasaur',
      doc_type: 'card',
      title: 'Bulbasaur (#1) — Pokédex card',
      score: 0.0328,
    },
  ],
};

export const ANSWERED: RAGResponse = {
  status: 'answered',
  answer: 'Bulbasaur is a grass/poison type Pokémon [1].',
  citations: [
    {
      marker: 1,
      document_id: '1',
      source_url: 'https://pokeapi.co/api/v2/pokemon/1/',
      snippet: 'Bulbasaur (#1) — Pokédex card',
    },
  ],
  confidence: null,
  warnings: [],
  corrections_applied: 0,
  evaluation_id: null,
  request_id: 'req-answered',
};

export const COMPARISON: CompareResponse = {
  question: 'what type is bulbasaur?',
  request_id: 'req-compare',
  context_document_ids: [2, 1],
  context_chars: 812,
  candidates: [
    {
      provider: 'vertex-gemini',
      model: 'gemini-3.6-flash',
      status: 'answered',
      answer: 'Bulbasaur is Grass/Poison [1].',
      citations: [],
      warnings: [],
      corrections_applied: 0,
      judge: {
        grounded: true,
        hallucination_detected: false,
        reasoning: 'supported by the card',
        independent: true,
      },
      latency_ms: 2884,
      prompt_tokens: 2000,
      output_tokens: 40,
    },
    {
      provider: 'ai-studio-gemini',
      model: 'gemini-3.5-flash-lite',
      status: 'answered',
      answer: 'Grass and poison [1]. Grass beats water.',
      citations: [],
      warnings: ["judge provider is 'ai-studio-gemini' — verdict is not independent"],
      corrections_applied: 0,
      judge: {
        grounded: false,
        hallucination_detected: true,
        reasoning: 'type effectiveness is not in the context',
        independent: false,
      },
      latency_ms: 599,
      prompt_tokens: 2000,
      output_tokens: 25,
    },
  ],
};

export const PIKACHU: PokemonCard = {
  ...BULBASAUR,
  id: 25,
  name: 'pikachu',
  types: [{ slot: 1, name: 'electric' }],
  stats: { hp: 35, attack: 55, speed: 90 },
  flavor_text: 'It stores electricity in its cheeks.',
};

export const INTENT_CARD: IntentResponse = {
  intent: 'card',
  entities: [{ id: 94, name: 'gengar', matched_text: 'gengar', match: 'exact', score: 1 }],
  confidence: 0.9,
  method: 'deterministic',
  warnings: [],
};

export const INTENT_QUESTION: IntentResponse = {
  intent: 'question',
  entities: [],
  confidence: 0.6,
  method: 'deterministic',
  warnings: [],
};

export const INTENT_VERSUS: IntentResponse = {
  intent: 'compare',
  entities: [
    { id: 25, name: 'pikachu', matched_text: 'pickachu', match: 'fuzzy', score: 0.93 },
    { id: 94, name: 'gengar', matched_text: 'gengar', match: 'exact', score: 1 },
  ],
  confidence: 0.95,
  method: 'deterministic',
  warnings: [],
};

export const MATCHUP: MatchupResponse = {
  a: PIKACHU,
  b: { ...BULBASAUR, id: 94, name: 'gengar', types: [{ slot: 1, name: 'ghost' }] },
  a_side: {
    name: 'pikachu',
    best_multiplier: 1,
    best_types: [],
    verdict: 'neutral',
    weak_to: ['ground'],
    immune_to: [],
    stat_total: 180,
  },
  b_side: {
    name: 'gengar',
    best_multiplier: 1,
    best_types: [],
    verdict: 'neutral',
    weak_to: ['dark', 'ghost'],
    immune_to: ['normal', 'fighting'],
    stat_total: 500,
  },
  type_advantage: 'none',
  stat_advantage: 'b',
  notes: ['Pikachu has no type advantage over Gengar (1x at best).'],
  disclaimer: 'Type and base-stat comparison only — not a battle simulation.',
};

/** IMAGE_MATCHES deliberately repeats pokemon_id 1 so dedupe is exercised. */
export const IMAGE_MATCHES: SearchResponse = {
  mode: 'image',
  space: 'gemini-embedding-2-768-v1',
  results: [
    {
      document_id: 11,
      pokemon_id: 1,
      pokemon_name: 'bulbasaur',
      doc_type: 'sprite',
      title: 'bulbasaur — default sprite',
      score: 0.99,
    },
    {
      document_id: 12,
      pokemon_id: 1,
      pokemon_name: 'bulbasaur',
      doc_type: 'sprite',
      title: 'bulbasaur — shiny sprite',
      score: 0.91,
    },
    {
      document_id: 13,
      pokemon_id: 25,
      pokemon_name: 'pikachu',
      doc_type: 'sprite',
      title: 'pikachu — default sprite',
      score: 0.85,
    },
  ],
};

interface Route {
  match: (url: string, init?: RequestInit) => boolean;
  status?: number;
  body: unknown;
}

/**
 * Installs a fetch fake that answers from a route table and records every call.
 * Anything unmatched rejects loudly — a silently-wrong URL is the bug most worth
 * catching in an API client.
 */
export function fakeFetch(routes: Route[]) {
  const calls: { url: string; init?: RequestInit }[] = [];
  const impl = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    const route = routes.find((candidate) => candidate.match(url, init));
    if (!route) throw new Error(`No fake route for ${init?.method ?? 'GET'} ${url}`);
    const status = route.status ?? 200;
    return {
      ok: status >= 200 && status < 300,
      status,
      headers: new Headers({ 'X-Request-ID': 'req-test' }),
      json: async () => route.body,
    } as Response;
  });
  vi.stubGlobal('fetch', impl);
  return { calls, impl };
}
