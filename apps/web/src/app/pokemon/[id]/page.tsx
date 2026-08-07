import { PokedexApp } from '@/components/pokedex/PokedexApp';
import { allPokemonIds } from '@/lib/config';

/**
 * Deep link: /pokemon/25/ opens the Pokédex already showing that card. The static
 * export pre-renders one page per ingested id (the build makes no API calls; each page
 * is a shell that fetches in the browser).
 */
export function generateStaticParams() {
  return allPokemonIds().map((id) => ({ id }));
}

export default async function PokemonPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <PokedexApp deepLink={{ card: id }} />;
}
