/** @type {import('next').NextConfig} */

// Type-check and lint run during `next build` so a type error can never ship
// silently again. Local dev can opt out with SKIP_TYPECHECK=1 (or
// SKIP_LINT=1) when a backend contract is still in flux.
const skipTypecheck = process.env.SKIP_TYPECHECK === '1';
const skipLint = process.env.SKIP_LINT === '1';

// Where the browser's /api/* calls are proxied to. Keep this in sync with the
// backend's listen port; it is read at RUNTIME (not baked into the bundle),
// which is what makes LAN/Docker installs work.
const API_PROXY_URL = process.env.API_PROXY_URL || 'http://localhost:8000/api';

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
