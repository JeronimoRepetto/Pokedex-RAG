/** The device end to end on fakes: intent dispatch, carousel, A/B, deep links. */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import { PokedexApp } from '@/components/pokedex/PokedexApp';
import {
  ANSWERED,
  BULBASAUR,
  COMPARISON,
  IMAGE_MATCHES,
  INTENT_CARD,
  INTENT_QUESTION,
  INTENT_VERSUS,
  MATCHUP,
  PIKACHU,
  fakeFetch,
} from './fixtures';

const GENGAR = { ...BULBASAUR, id: 94, name: 'gengar' };

const post = (path: string, body: unknown, status?: number) => ({
  match: (url: string) => url.includes(path),
  body,
  status,
});

async function type(user: ReturnType<typeof userEvent.setup>, text: string) {
  await user.type(screen.getByLabelText('Ask the Pokédex'), text);
  await user.click(screen.getByRole('button', { name: /Enviar/ }));
}

describe('intent dispatch', () => {
  it('routes a card intent to the card view', async () => {
    fakeFetch([post('/intent', INTENT_CARD), post('/pokemon/gengar', GENGAR)]);
    const user = userEvent.setup();
    render(<PokedexApp />);

    await type(user, 'Dime todo sobre Gengar');

    expect(await screen.findByRole('heading', { name: /gengar/i })).toBeInTheDocument();
  });

  it('routes a question to /chat and shows the cited answer', async () => {
    const { calls } = fakeFetch([post('/intent', INTENT_QUESTION), post('/chat', ANSWERED)]);
    const user = userEvent.setup();
    render(<PokedexApp />);

    await type(user, 'what type is bulbasaur?');

    expect(await screen.findByText(/grass\/poison type/)).toBeInTheDocument();
    expect(calls.some((c) => c.url.includes('/compare'))).toBe(false);
  });

  it('routes a comparison to /matchup and shows both sides in the screen', async () => {
    fakeFetch([
      post('/intent', INTENT_VERSUS),
      post('/matchup', MATCHUP),
      post('/chat', ANSWERED),
    ]);
    const user = userEvent.setup();
    render(<PokedexApp />);

    await type(user, 'Pickachu es mas fuerte que Gengar?');

    expect(await screen.findByText('VS')).toBeInTheDocument();
    // Fighter names appear in the header AND in the matchup notes.
    expect(screen.getAllByText(/pikachu/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/gengar/i).length).toBeGreaterThan(0);
    // The shared-grid layout labels each stat once, between the two values.
    expect(screen.getAllByText('hp')).toHaveLength(1);
    expect(screen.getByText(/not a battle simulation/)).toBeInTheDocument();
  });

  it('a numeric input skips /intent entirely', async () => {
    const { calls } = fakeFetch([post('/pokemon/25', PIKACHU)]);
    const user = userEvent.setup();
    render(<PokedexApp />);

    await type(user, '25');

    expect(await screen.findByRole('heading', { name: /pikachu/i })).toBeInTheDocument();
    expect(calls.some((c) => c.url.includes('/intent'))).toBe(false);
  });

  it('an unreachable intent service degrades to a question instead of dying', async () => {
    fakeFetch([
      {
        match: (url) => url.includes('/intent'),
        get body(): never {
          throw new TypeError('Failed to fetch');
        },
      },
      post('/chat', ANSWERED),
    ]);
    const user = userEvent.setup();
    render(<PokedexApp />);

    await type(user, 'anything at all really');

    expect(await screen.findByText(/grass\/poison type/)).toBeInTheDocument();
  });
});

describe('provider A/B', () => {
  it('when the toggle is ON a question makes exactly one /compare call and no /chat', async () => {
    const { calls } = fakeFetch([
      post('/intent', INTENT_QUESTION),
      post('/compare', COMPARISON),
    ]);
    const user = userEvent.setup();
    render(<PokedexApp />);

    await user.click(screen.getByRole('switch'));
    await type(user, 'what type is bulbasaur?');

    await screen.findByText('Provider comparison');
    expect(calls.filter((c) => c.url.includes('/compare'))).toHaveLength(1);
    expect(calls.some((c) => c.url.includes('/chat'))).toBe(false);
    // The primary provider is named twice BY DESIGN: as the in-screen answer's badge
    // and in the full grid below the chassis.
    expect(screen.getAllByText('vertex-gemini')).toHaveLength(2);
    expect(screen.getByText('self-graded')).toBeInTheDocument();
  });

  it('with the toggle OFF no comparison panel exists', async () => {
    fakeFetch([post('/intent', INTENT_QUESTION), post('/chat', ANSWERED)]);
    const user = userEvent.setup();
    render(<PokedexApp />);

    await type(user, 'what type is bulbasaur?');

    await screen.findByText(/grass\/poison type/);
    expect(screen.queryByText('Provider comparison')).not.toBeInTheDocument();
  });
});

describe('image matches carousel', () => {
  function route() {
    return fakeFetch([
      post('/search/image', IMAGE_MATCHES),
      post('/pokemon/1', BULBASAUR),
      post('/pokemon/25', PIKACHU),
    ]);
  }

  async function upload(user: ReturnType<typeof userEvent.setup>) {
    await user.upload(
      screen.getByTestId('image-input'),
      new File([new Uint8Array([1])], 'sprite.png', { type: 'image/png' }),
    );
  }

  it('shows deduped matches one at a time with a position readout', async () => {
    route();
    const user = userEvent.setup();
    render(<PokedexApp />);

    await upload(user);

    expect(await screen.findByText(/1 of 2/)).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: /bulbasaur/i })).toBeInTheDocument();
  });

  it('steps forward with the d-pad and disables at the ends', async () => {
    route();
    const user = userEvent.setup();
    render(<PokedexApp />);
    await upload(user);
    await screen.findByText(/1 of 2/);

    expect(screen.getByRole('button', { name: 'Previous match' })).toBeDisabled();
    await user.click(screen.getByRole('button', { name: 'Next match' }));

    expect(await screen.findByText(/2 of 2/)).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: /pikachu/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Next match' })).toBeDisabled();
  });

  it('rejects a wrong file type locally with a visible error', async () => {
    // fireEvent.change, not user.upload: upload honours the input's `accept` (the
    // Phase-7 lesson) and would silently drop the PDF before the handler ever ran.
    const { calls } = route();
    render(<PokedexApp />);

    fireEvent.change(screen.getByTestId('camera-input'), {
      target: { files: [new File(['x'], 'notes.pdf', { type: 'application/pdf' })] },
    });

    expect(await screen.findByRole('alert')).toHaveTextContent(/no está soportado/);
    expect(calls.some((c) => c.url.includes('/search/image'))).toBe(false);
  });
});

describe('deep links and failure display', () => {
  it('a deep link loads and shows that card on mount', async () => {
    fakeFetch([post('/pokemon/25', PIKACHU)]);
    render(<PokedexApp deepLink={{ card: '25' }} />);

    expect(await screen.findByRole('heading', { name: /pikachu/i })).toBeInTheDocument();
  });

  it('an API failure shows the error while keeping the previous screen usable', async () => {
    fakeFetch([
      post('/pokemon/25', PIKACHU),
      post('/intent', INTENT_QUESTION),
      post('/chat', { detail: 'provider exploded' }, 503),
    ]);
    const user = userEvent.setup();
    render(<PokedexApp deepLink={{ card: '25' }} />);
    await screen.findByRole('heading', { name: /pikachu/i });

    await type(user, 'what type is bulbasaur?');

    expect(await screen.findByRole('alert')).toHaveTextContent('provider exploded');
    // The card is still on screen behind the error.
    expect(screen.getByRole('heading', { name: /pikachu/i })).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'OK' }));
    await waitFor(() => expect(screen.queryByRole('alert')).not.toBeInTheDocument());
  });
});

describe('paused service', () => {
  const HEALTH_PAUSED = {
    status: 'ok',
    paused: true,
    contact: 'demo@example.com',
    dependencies: { database: { status: 'ok' } },
  };

  it('shows the bilingual notice and disables the controls', async () => {
    fakeFetch([{ match: (url) => url.includes('/health'), body: HEALTH_PAUSED }]);

    render(<PokedexApp />);

    expect(await screen.findByText(/Servicio pausado/)).toBeInTheDocument();
    expect(screen.getByText(/Service paused/)).toBeInTheDocument();
    expect(screen.getAllByText(/demo@example.com/).length).toBeGreaterThan(0);
    expect(screen.getByRole('button', { name: 'Enviar' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Imagen…' })).toBeDisabled();
  });

  it('stays usable when the service is running', async () => {
    fakeFetch([
      {
        match: (url) => url.includes('/health'),
        body: { ...HEALTH_PAUSED, paused: false, contact: '' },
      },
    ]);

    render(<PokedexApp />);

    await waitFor(() => expect(screen.queryByText(/Servicio pausado/)).not.toBeInTheDocument());
    expect(screen.getByLabelText('Ask the Pokédex')).toBeInTheDocument();
  });

  it('an unreachable API is NOT reported as paused', async () => {
    // Being switched off on purpose and being broken are different facts; guessing
    // would tell the visitor the wrong thing.
    fakeFetch([
      {
        match: () => {
          throw new TypeError('Failed to fetch');
        },
        body: null,
      },
    ]);

    render(<PokedexApp />);

    await waitFor(() => expect(screen.queryByText(/Servicio pausado/)).not.toBeInTheDocument());
  });
});
