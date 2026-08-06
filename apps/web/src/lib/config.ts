/**
 * Build-time configuration. Values that differ per environment live in env vars, never
 * inline in components (project guideline 2).
 */

/**
 * Highest Pokémon id the API has ingested. A static export must know its routes at
 * build time, so one page per id in 1..MAX is pre-rendered. The project ingests
 * generation 1 (`pipeline ingest --generation 1`), hence the default of 151; raise it
 * when a later generation is ingested and rebuild.
 */
export const MAX_POKEMON_ID = Number(process.env.NEXT_PUBLIC_POKEDEX_MAX_ID ?? '151');

export function allPokemonIds(): string[] {
  return Array.from({ length: MAX_POKEMON_ID }, (_, index) => String(index + 1));
}
