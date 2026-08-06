/**
 * Mirrors the API's response contracts (apps/api schemas + libs/common contracts).
 * Hand-written rather than generated: the surface is small, and a generated client
 * would add a build step for no benefit at this size. If the API contract changes,
 * these types and the client tests are what should fail first.
 */

export interface TypeSlot {
  slot: number;
  name: string;
}

export interface AbilityEntry {
  name: string;
  is_hidden: boolean;
}

export interface PokemonSummary {
  id: number;
  name: string;
  types: TypeSlot[];
}

export interface PokemonListResponse {
  items: PokemonSummary[];
  page: number;
  page_size: number;
  total: number;
}

export interface PokemonCard {
  id: number;
  name: string;
  generation: number;
  color: string | null;
  habitat: string | null;
  is_legendary: boolean;
  is_mythical: boolean;
  height_decimetres: number | null;
  weight_hectograms: number | null;
  base_experience: number | null;
  types: TypeSlot[];
  abilities: AbilityEntry[];
  stats: Record<string, number>;
  flavor_text: string | null;
  sprite_kinds: string[];
}

export interface SpeciesRef {
  id: number;
  name: string;
}

export interface EvolutionEdge {
  from_species: SpeciesRef;
  to_species: SpeciesRef;
  trigger: string | null;
  min_level: number | null;
  item: string | null;
}

export interface EvolutionChainResponse {
  chain_id: number | null;
  edges: EvolutionEdge[];
}

export type SearchMode = 'vector' | 'lexical' | 'hybrid';

export interface SearchResult {
  document_id: number;
  pokemon_id: number;
  pokemon_name: string;
  doc_type: string;
  title: string;
  score: number;
}

export interface SearchResponse {
  mode: string;
  space: string;
  results: SearchResult[];
}

export type ResponseStatus =
  'answered' | 'corrected' | 'insufficient_evidence' | 'provider_error';

export interface Citation {
  marker: number;
  document_id: string;
  source_url: string | null;
  snippet: string | null;
}

export interface RAGResponse {
  status: ResponseStatus;
  answer: string | null;
  citations: Citation[];
  confidence: number | null;
  warnings: string[];
  corrections_applied: number;
  evaluation_id: string | null;
  request_id: string;
}

export interface JudgeVerdict {
  grounded: boolean;
  hallucination_detected: boolean;
  reasoning: string;
  /** False when the judge and this candidate are the same provider (Phase 6.2). */
  independent: boolean;
}

export interface CompareCandidate {
  provider: string;
  model: string;
  status: ResponseStatus;
  answer: string | null;
  citations: Citation[];
  warnings: string[];
  corrections_applied: number;
  judge: JudgeVerdict | null;
  latency_ms: number;
  prompt_tokens: number;
  output_tokens: number;
}

export interface CompareResponse {
  question: string;
  request_id: string;
  context_document_ids: number[];
  context_chars: number;
  candidates: CompareCandidate[];
}

export interface HealthResponse {
  status: string;
  dependencies: Record<string, { status: string; detail?: string }>;
}
