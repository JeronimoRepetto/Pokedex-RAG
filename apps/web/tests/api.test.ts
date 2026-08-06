/** The API client: URL shapes, error translation, and the contracts it depends on. */

import { describe, expect, it } from 'vitest';
import {
  ApiError,
  chat,
  compare,
  getPokemon,
  searchImage,
  searchText,
  spriteUrl,
} from '@/lib/api';
import { ANSWERED, BULBASAUR, COMPARISON, SEARCH_RESPONSE, fakeFetch } from './fixtures';

const anyRoute = (body: unknown, status?: number) => [{ match: () => true, body, status }];

describe('request shapes', () => {
  it('searches text with the mode and limit the caller chose', async () => {
    const { calls } = fakeFetch(anyRoute(SEARCH_RESPONSE));

    await searchText({ query: 'seed pokemon', mode: 'vector', limit: 5 });

    expect(calls[0].url).toContain('/search/text');
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({
      query: 'seed pokemon',
      mode: 'vector',
      limit: 5,
    });
  });

  it('omits the space unless one is requested', async () => {
    const { calls } = fakeFetch(anyRoute(SEARCH_RESPONSE));

    await searchText({ query: 'seed pokemon' });

    expect(JSON.parse(String(calls[0].init?.body))).not.toHaveProperty('space');
  });

  it('passes a chosen embedding space through', async () => {
    const { calls } = fakeFetch(anyRoute(SEARCH_RESPONSE));

    await searchText({ query: 'seed', space: 'embeddinggemma-768-v1' });

    expect(JSON.parse(String(calls[0].init?.body)).space).toBe('embeddinggemma-768-v1');
  });

  it('uploads an image as multipart without forcing a Content-Type', async () => {
    // The browser must set the multipart boundary itself; a hand-set header breaks it.
    const { calls } = fakeFetch(anyRoute(SEARCH_RESPONSE));
    const file = new File([new Uint8Array([1, 2, 3])], 'pikachu.png', {
      type: 'image/png',
    });

    await searchImage(file, 5);

    expect(calls[0].url).toContain('/search/image?limit=5');
    expect(calls[0].init?.body).toBeInstanceOf(FormData);
    const headers = (calls[0].init?.headers ?? {}) as Record<string, string>;
    expect(headers['Content-Type']).toBeUndefined();
  });

  it('encodes names safely into the path', async () => {
    const { calls } = fakeFetch(anyRoute(BULBASAUR));

    await getPokemon('mr mime');

    expect(calls[0].url).toContain('/pokemon/mr%20mime');
  });

  it('builds sprite URLs with the requested kind', () => {
    expect(spriteUrl(25)).toContain('/pokemon/25/sprite?kind=official-artwork');
    expect(spriteUrl(25, 'default')).toContain('kind=default');
  });

  it('sends providers to /compare only when given', async () => {
    const { calls } = fakeFetch(anyRoute(COMPARISON));

    await compare('what type is bulbasaur?');
    await compare('what type is bulbasaur?', ['a', 'b']);

    expect(JSON.parse(String(calls[0].init?.body))).not.toHaveProperty('providers');
    expect(JSON.parse(String(calls[1].init?.body)).providers).toEqual(['a', 'b']);
  });
});

describe('error translation', () => {
  it('surfaces the API detail string', async () => {
    fakeFetch(anyRoute({ detail: 'unknown provider' }, 422));

    await expect(chat('hello there')).rejects.toThrow('unknown provider');
  });

  it('flattens FastAPI validation errors into one message', async () => {
    fakeFetch(
      anyRoute({ detail: [{ msg: 'string too short' }, { msg: 'field required' }] }, 422),
    );

    await expect(chat('hi')).rejects.toThrow('string too short; field required');
  });

  it('keeps the status and request id on the error', async () => {
    fakeFetch(anyRoute({ detail: 'boom' }, 503));

    const error = await chat('a question').catch((caught) => caught);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(503);
    expect(error.requestId).toBe('req-test');
  });

  it('falls back to the status code when the body is not JSON', async () => {
    fakeFetch([
      {
        match: () => true,
        status: 502,
        get body() {
          throw new Error('not json');
        },
      },
    ]);

    await expect(chat('a question')).rejects.toThrow('HTTP 502');
  });

  it('explains an unreachable API instead of leaking a fetch error', async () => {
    fakeFetch([
      {
        match: () => {
          throw new TypeError('Failed to fetch');
        },
        body: null,
      },
    ]);

    const error = await chat('a question').catch((caught) => caught);

    expect(error.message).toMatch(/Cannot reach the API/);
    expect(error.status).toBe(0);
  });

  it('returns the parsed body on success', async () => {
    fakeFetch(anyRoute(ANSWERED));

    await expect(chat('what type is bulbasaur?')).resolves.toEqual(ANSWERED);
  });
});
