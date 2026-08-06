import { PokemonDetail } from '@/components/PokemonDetail';
import { allPokemonIds } from '@/lib/config';

/**
 * A static export has to know every route at build time. The ingested corpus is a
 * fixed id range, so one page per Pokémon is pre-rendered; each page is a shell that
 * fetches its own data in the browser, keeping the build free of API calls.
 */
export function generateStaticParams() {
  return allPokemonIds().map((id) => ({ id }));
}

export default async function PokemonPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <PokemonDetail idOrName={id} />;
}
