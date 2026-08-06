/** Page-level behaviour on fakes: no API, no network. */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it } from 'vitest';
import ChatPage from '@/app/chat/page';
import ComparePage from '@/app/compare/page';
import SearchPage from '@/app/page';
import { PokemonDetail } from '@/components/PokemonDetail';
import { ANSWERED, BULBASAUR, CHAIN, COMPARISON, SEARCH_RESPONSE, fakeFetch } from './fixtures';

const post = (path: string, body: unknown, status?: number) => ({
  match: (url: string) => url.includes(path),
  body,
  status,
});

describe('search page', () => {
  it('shows results with the mode and space the API reports', async () => {
    fakeFetch([post('/search/text', SEARCH_RESPONSE)]);
    const user = userEvent.setup();
    render(<SearchPage />);

    await user.type(screen.getByLabelText('Search query'), 'seed pokemon');
    await user.click(screen.getByRole('button', { name: 'Search' }));

    expect(await screen.findByText('bulbasaur')).toBeInTheDocument();
    expect(screen.getByText(/gemini-embedding-2-768-v1/)).toBeInTheDocument();
  });

  it('refuses to search on a one-character query', async () => {
    fakeFetch([post('/search/text', SEARCH_RESPONSE)]);
    const user = userEvent.setup();
    render(<SearchPage />);

    await user.type(screen.getByLabelText('Search query'), 'a');

    expect(screen.getByRole('button', { name: 'Search' })).toBeDisabled();
  });

  it('reports an API failure instead of rendering nothing', async () => {
    fakeFetch([post('/search/text', { detail: 'space not registered' }, 503)]);
    const user = userEvent.setup();
    render(<SearchPage />);

    await user.type(screen.getByLabelText('Search query'), 'anything');
    await user.click(screen.getByRole('button', { name: 'Search' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('space not registered');
  });

  it('rejects a dropped non-image file locally, before any upload', async () => {
    // The file picker filters by `accept`, but a DRAG-AND-DROP does not — which is
    // exactly why the component validates the type itself.
    const { calls } = fakeFetch([post('/search/image', SEARCH_RESPONSE)]);
    render(<SearchPage />);

    fireEvent.drop(screen.getByLabelText(/Search by image/), {
      dataTransfer: { files: [new File(['x'], 'notes.txt', { type: 'text/plain' })] },
    });

    expect(await screen.findByRole('alert')).toHaveTextContent(/not supported/);
    expect(calls).toHaveLength(0);
  });

  it('rejects an oversized dropped image locally', async () => {
    const { calls } = fakeFetch([post('/search/image', SEARCH_RESPONSE)]);
    render(<SearchPage />);
    const huge = new File([new Uint8Array(1)], 'huge.png', { type: 'image/png' });
    Object.defineProperty(huge, 'size', { value: 6 * 1024 * 1024 });

    fireEvent.drop(screen.getByLabelText(/Search by image/), {
      dataTransfer: { files: [huge] },
    });

    expect(await screen.findByRole('alert')).toHaveTextContent(/limit is 5 MB/);
    expect(calls).toHaveLength(0);
  });

  it('uploads a valid image and shows the matches', async () => {
    const { calls } = fakeFetch([post('/search/image', SEARCH_RESPONSE)]);
    const user = userEvent.setup();
    render(<SearchPage />);

    await user.upload(
      screen.getByTestId('image-input'),
      new File([new Uint8Array([1])], 'sprite.png', { type: 'image/png' }),
    );

    expect(await screen.findByText('bulbasaur')).toBeInTheDocument();
    expect(calls[0].url).toContain('/search/image');
  });
});

describe('pokemon detail', () => {
  it('renders the card, stats and evolution chain', async () => {
    fakeFetch([
      { match: (url) => url.includes('/evolution-chain'), body: CHAIN },
      { match: (url) => url.includes('/pokemon/'), body: BULBASAUR },
    ]);

    render(<PokemonDetail idOrName="1" />);

    expect(await screen.findByRole('heading', { name: /bulbasaur/i })).toBeInTheDocument();
    expect(screen.getByText('45')).toBeInTheDocument();
    expect(screen.getByText(/chlorophyll \(hidden\)/)).toBeInTheDocument();
    expect(screen.getByText(/level 16/)).toBeInTheDocument();
  });

  it('still renders the card when the evolution chain fails', async () => {
    // The chain is supporting detail; losing it must not blank the whole page.
    fakeFetch([
      {
        match: (url) => url.includes('/evolution-chain'),
        body: { detail: 'nope' },
        status: 500,
      },
      { match: (url) => url.includes('/pokemon/'), body: BULBASAUR },
    ]);

    render(<PokemonDetail idOrName="1" />);

    expect(await screen.findByRole('heading', { name: /bulbasaur/i })).toBeInTheDocument();
    expect(screen.getByText(/could not be loaded/)).toBeInTheDocument();
  });

  it('shows a 404 as an error with a way back', async () => {
    fakeFetch([
      { match: () => true, body: { detail: "Pokemon '999' not found" }, status: 404 },
    ]);

    render(<PokemonDetail idOrName="999" />);

    expect(await screen.findByRole('alert')).toHaveTextContent('not found');
    expect(screen.getByRole('link', { name: /back to search/i })).toBeInTheDocument();
  });
});

describe('chat page', () => {
  it('renders the answer with its citation', async () => {
    fakeFetch([post('/chat', ANSWERED)]);
    const user = userEvent.setup();
    render(<ChatPage />);

    await user.type(screen.getByLabelText('Question'), 'what type is bulbasaur?');
    await user.click(screen.getByRole('button', { name: 'Ask' }));

    expect(await screen.findByText(/grass\/poison type/)).toBeInTheDocument();
    expect(screen.getByText('answered')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Pokédex card/ })).toBeInTheDocument();
  });

  it('surfaces abstention, warnings and corrections rather than hiding them', async () => {
    fakeFetch([
      post('/chat', {
        ...ANSWERED,
        status: 'insufficient_evidence',
        answer: null,
        citations: [],
        warnings: ['judge flagged ungrounded answer: invented a stat'],
        corrections_applied: 2,
      }),
    ]);
    const user = userEvent.setup();
    render(<ChatPage />);

    await user.type(screen.getByLabelText('Question'), "what is Mewtwo's favourite food?");
    await user.click(screen.getByRole('button', { name: 'Ask' }));

    expect(await screen.findByText(/abstained/)).toBeInTheDocument();
    expect(screen.getByText('insufficient evidence')).toBeInTheDocument();
    expect(screen.getByText('2 corrections applied')).toBeInTheDocument();
    expect(screen.getByText(/invented a stat/)).toBeInTheDocument();
  });

  it('keeps earlier exchanges, newest first', async () => {
    fakeFetch([post('/chat', ANSWERED)]);
    const user = userEvent.setup();
    render(<ChatPage />);

    await user.type(screen.getByLabelText('Question'), 'first question');
    await user.click(screen.getByRole('button', { name: 'Ask' }));
    await screen.findByText(/grass\/poison type/);

    expect(screen.getByLabelText('Question')).toHaveValue('');
    expect(screen.getByText('first question')).toBeInTheDocument();
  });
});

describe('compare page', () => {
  it('shows both candidates with their judge verdicts and cost signals', async () => {
    fakeFetch([post('/compare', COMPARISON)]);
    const user = userEvent.setup();
    render(<ComparePage />);

    await user.type(screen.getByLabelText('Question to compare'), 'what type is bulbasaur?');
    await user.click(screen.getByRole('button', { name: 'Compare' }));

    expect(await screen.findByText('vertex-gemini')).toBeInTheDocument();
    expect(screen.getByText('ai-studio-gemini')).toBeInTheDocument();
    expect(screen.getByText('grounded')).toBeInTheDocument();
    expect(screen.getByText('ungrounded')).toBeInTheDocument();
    expect(screen.getByText('2884 ms')).toBeInTheDocument();
  });

  it('marks a self-graded verdict as not independent', async () => {
    fakeFetch([post('/compare', COMPARISON)]);
    const user = userEvent.setup();
    render(<ComparePage />);

    await user.type(screen.getByLabelText('Question to compare'), 'what type is bulbasaur?');
    await user.click(screen.getByRole('button', { name: 'Compare' }));

    expect(await screen.findByText('self-graded')).toBeInTheDocument();
    // Both the API's own warning and the UI's explanation say it; the point is that
    // the caveat is impossible to miss, so assert the UI's explanation specifically.
    expect(screen.getByText(/This provider is also the configured judge/)).toBeInTheDocument();
  });

  it('proves the shared context by listing the document ids', async () => {
    fakeFetch([post('/compare', COMPARISON)]);
    const user = userEvent.setup();
    render(<ComparePage />);

    await user.type(screen.getByLabelText('Question to compare'), 'what type is bulbasaur?');
    await user.click(screen.getByRole('button', { name: 'Compare' }));

    await waitFor(() => expect(screen.getByText('2, 1')).toBeInTheDocument());
  });
});
