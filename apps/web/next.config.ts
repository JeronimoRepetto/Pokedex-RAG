import type { NextConfig } from 'next';

/**
 * Static export: this UI is pure client-side and talks to the Pokédex API over HTTP,
 * so it ships as static files (guideline: frontends deploy as static, no Dockerfile).
 * There is no server component doing data fetching and no Next.js API route acting as
 * a proxy — the browser calls the API directly, which is why the API needs a CORS
 * allowlist (CORS_ALLOWED_ORIGINS).
 */
const nextConfig: NextConfig = {
  output: 'export',
  reactStrictMode: true,
  // The floating "N" button in the corner is Next's dev-tools indicator. It never
  // ships in a production build, but it also has no business on top of the device
  // while developing — off.
  devIndicators: false,
  // next/image's optimizer needs a server; static export has none. Sprites are already
  // small PNGs served by the API with a cache header, so plain <img> is the honest
  // choice here rather than shipping an optimizer that cannot run.
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
