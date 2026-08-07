/**
 * The single place this UI talks to the Pokédex API. No component fetches directly.
 *
 * Everything is client-side: the browser calls the API host, which is why the API needs
 * this origin in CORS_ALLOWED_ORIGINS. There is no server-side proxy — the app is a
 * static export.
 */

import type {
  CompareResponse,
  EvolutionChainResponse,
  HealthResponse,
  IntentResponse,
  MatchupResponse,
  PokemonCard,
  PokemonListResponse,
  RAGResponse,
  SearchMode,
  SearchResponse,
} from './types';

/** Empty default keeps relative URLs working when the UI is served by the API itself. */
export const API_BASE_URL = (process.env.NEXT_PUBLIC_API_BASE_URL ?? '').replace(/\/$/, '');

/**
 * Sent as X-API-Key when configured. NOTE: anything in a NEXT_PUBLIC_ variable ships to
 * the browser and is readable by anyone using the app — this is fine for a local run or
 * a shared demo key, and is NOT a way to protect a public deployment. The deployment
 * runbook covers the real options.
 */
const API_KEY = process.env.NEXT_PUBLIC_API_KEY ?? '';

const DEFAULT_TIMEOUT_MS = 60_000;

export class ApiError extends Error {
  readonly status: number;
  readonly requestId: string | null;

  constructor(message: string, status: number, requestId: string | null = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.requestId = requestId;
  }
}

function authHeaders(): Record<string, string> {
  return API_KEY ? { 'X-API-Key': API_KEY } : {};
}

/** FastAPI returns `detail` as a string, or as a list of objects for 422s. */
function readDetail(payload: unknown, fallback: string): string {
  if (payload && typeof payload === 'object' && 'detail' in payload) {
    const detail = (payload as { detail: unknown }).detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) {
      const messages = detail
        .map((item) =>
          item && typeof item === 'object' && 'msg' in item
            ? String((item as { msg: unknown }).msg)
            : null,
        )
        .filter((msg): msg is string => Boolean(msg));
      if (messages.length > 0) return messages.join('; ');
    }
  }
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), DEFAULT_TIMEOUT_MS);
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { ...authHeaders(), ...init.headers },
      signal: controller.signal,
    });
  } catch (cause) {
    // An aborted fetch and a refused connection both land here; distinguish them so the
    // UI can say "the API is not reachable" instead of a generic failure.
    const aborted = cause instanceof DOMException && cause.name === 'AbortError';
    throw new ApiError(
      aborted
        ? `The API did not respond within ${DEFAULT_TIMEOUT_MS / 1000}s.`
        : `Cannot reach the API at ${API_BASE_URL || 'the same origin'}. Is it running?`,
      0,
    );
  } finally {
    clearTimeout(timeout);
  }

  const requestId = response.headers.get('X-Request-ID');
  if (!response.ok) {
    let payload: unknown = null;
    try {
      payload = await response.json();
    } catch {
      // A non-JSON error body (a proxy's HTML page, say) is not worth surfacing raw.
    }
    throw new ApiError(
      readDetail(payload, `Request failed with HTTP ${response.status}`),
      response.status,
      requestId,
    );
  }
  return (await response.json()) as T;
}

function jsonPost<T>(path: string, body: unknown): Promise<T> {
  return request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
}

export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/health');
}

export function listPokemon(params: {
  page?: number;
  pageSize?: number;
  type?: string;
  name?: string;
}): Promise<PokemonListResponse> {
  const query = new URLSearchParams();
  query.set('page', String(params.page ?? 1));
  query.set('page_size', String(params.pageSize ?? 20));
  if (params.type) query.set('type', params.type);
  if (params.name) query.set('name', params.name);
  return request<PokemonListResponse>(`/pokemon?${query.toString()}`);
}

export function getPokemon(idOrName: string): Promise<PokemonCard> {
  return request<PokemonCard>(`/pokemon/${encodeURIComponent(idOrName)}`);
}

export function getEvolutionChain(idOrName: string): Promise<EvolutionChainResponse> {
  return request<EvolutionChainResponse>(
    `/pokemon/${encodeURIComponent(idOrName)}/evolution-chain`,
  );
}

/** Sprite URLs are plain <img> sources, so this returns a URL rather than fetching. */
export function spriteUrl(idOrName: string | number, kind = 'official-artwork'): string {
  return `${API_BASE_URL}/pokemon/${encodeURIComponent(String(idOrName))}/sprite?kind=${encodeURIComponent(kind)}`;
}

export function searchText(params: {
  query: string;
  mode?: SearchMode;
  limit?: number;
  space?: string;
}): Promise<SearchResponse> {
  const body: Record<string, unknown> = {
    query: params.query,
    mode: params.mode ?? 'hybrid',
    limit: params.limit ?? 10,
  };
  if (params.space) body.space = params.space;
  return jsonPost<SearchResponse>('/search/text', body);
}

export async function searchImage(file: File, limit = 10): Promise<SearchResponse> {
  const form = new FormData();
  form.append('image', file);
  // Multipart: let the browser set Content-Type so it can add the boundary.
  return request<SearchResponse>(`/search/image?limit=${limit}`, {
    method: 'POST',
    body: form,
  });
}

export function chat(question: string, provider?: string): Promise<RAGResponse> {
  const body: Record<string, unknown> = { question };
  if (provider) body.provider = provider;
  return jsonPost<RAGResponse>('/chat', body);
}

export function compare(question: string, providers?: string[]): Promise<CompareResponse> {
  const body: Record<string, unknown> = { question };
  if (providers && providers.length > 0) body.providers = providers;
  return jsonPost<CompareResponse>('/compare', body);
}

export function classifyIntent(question: string): Promise<IntentResponse> {
  return jsonPost<IntentResponse>('/intent', { question });
}

/** Deterministic Pokémon-vs-Pokémon head-to-head — no LLM behind it, so it's instant. */
export function getMatchup(a: string, b: string): Promise<MatchupResponse> {
  return jsonPost<MatchupResponse>('/matchup', { a, b });
}
