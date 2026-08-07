import { PokedexApp } from '@/components/pokedex/PokedexApp';

/**
 * Alias kept alive: a static export cannot emit redirects, and old bookmarks should
 * keep working. The chat now lives inside the Pokédex.
 */
export default function ChatAlias() {
  return <PokedexApp />;
}
