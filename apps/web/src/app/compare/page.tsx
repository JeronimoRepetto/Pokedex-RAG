import { PokedexApp } from '@/components/pokedex/PokedexApp';

/**
 * Alias kept alive (static export cannot redirect). Provider comparison is now the A/B
 * toggle on the device's console; its results render below the chassis.
 */
export default function CompareAlias() {
  return <PokedexApp />;
}
