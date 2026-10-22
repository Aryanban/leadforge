/** @type {import('next').NextConfig} */

// Type-check and lint run during `next build` so a type error can never ship
// silently again. Local dev can opt out with SKIP_TYPECHECK=1 (or
// SKIP_LINT=1) when a backend contract is still in flux.
const skipTypecheck = process.env.SKIP_TYPECHECK === '1';
const skipLint = process.env.SKIP_LINT === '1';

// Where the browser's /api/* calls are proxied to.
//
// This is read at BUILD time, not at runtime: Next.js serialises the rewrite
// into routes-manifest.json when it builds, and the standalone server copies
// that manifest verbatim. Setting API_PROXY_URL when *starting* the server
// therefore does nothing - it has to be set when *building*.
//
// Docker does this correctly (the Dockerfile takes API_PROXY_URL as a build
// ARG). A manual `npm run build` without it silently produces a dashboard
// that proxies to localhost:8000, which works on the build machine and
// nowhere else - so we say so loudly.
const API_PROXY_URL = process.env.API_PROXY_URL || 'http://localhost:8000/api';

if (!process.env.API_PROXY_URL) {
    console.warn(
        '\n  [leadforge] API_PROXY_URL was not set, so /api/* will proxy to\n' +
        `  ${API_PROXY_URL} (baked into this build).\n` +
        '  Set it at BUILD time, e.g.\n' +
        '    API_PROXY_URL=http://backend:8000/api npm run build\n'
    );
}

const nextConfig = {
    output: 'standalone',
    eslint: { ignoreDuringBuilds: skipLint },
    typescript: { ignoreBuildErrors: skipTypecheck },
    async rewrites() {
        return [
            {
                source: '/api/:path*',
                destination: `${API_PROXY_URL}/:path*`,
            },
        ];
    },
};

export default nextConfig;
