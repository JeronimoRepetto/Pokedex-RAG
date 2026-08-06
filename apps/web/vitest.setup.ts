import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach, vi } from 'vitest';

// Unit tests never touch the network (project guideline 5). Every test installs its own
// fetch fake; this guard turns an un-faked call into an obvious failure rather than a
// hanging request or a real one.
beforeEach(() => {
  vi.stubGlobal(
    'fetch',
    vi.fn(() => {
      throw new Error('Unexpected network call: install a fetch fake in the test.');
    }),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
