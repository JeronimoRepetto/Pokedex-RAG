import type { Metadata } from 'next';
import Link from 'next/link';
import './globals.css';

export const metadata: Metadata = {
  title: 'Pokédex AI — Multimodal RAG Lab',
  description:
    'Unofficial, educational Pokédex: multimodal search and RAG chat over Gen-1 data. Not affiliated with Nintendo, Game Freak, Creatures Inc. or The Pokémon Company.',
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="layout">
          <nav className="nav">
            <Link href="/" className="nav-brand">
              Pokédex AI
            </Link>
            <Link href="/">Search</Link>
            <Link href="/chat/">Chat</Link>
            <Link href="/compare/">Compare</Link>
          </nav>
          <main>{children}</main>
          {/* The IP disclaimer is part of the layout, so it cannot be forgotten on a
              page — same rule the root README and the OpenAPI description follow. */}
          <footer>
            <p>
              Educational, non-commercial project. <strong>Not affiliated with</strong>,
              sponsored or endorsed by Nintendo, Game Freak, Creatures Inc. or The Pokémon
              Company. Pokémon names, characters and images belong to their respective owners.
            </p>
            <p>
              Data obtained via <a href="https://pokeapi.co/">PokéAPI</a>. Sprites are shown for
              educational use and are not redistributed in this project&apos;s source
              repository.
            </p>
          </footer>
        </div>
      </body>
    </html>
  );
}
