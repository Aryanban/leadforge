// @ts-check
/** @type {import('@playwright/test').PlaywrightTestConfig} */
const config = {
  testDir: './e2e',
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL || 'http://127.0.0.1:3000',
    viewport: { width: 1440, height: 900 },
    actionTimeout: 20_000,
    navigationTimeout: 45_000,
    screenshot: 'off',
    video: 'off',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
  // The suite has to boot the app itself, otherwise it silently tests nothing.
  // CI builds first (the build now type-checks) and starts the PRODUCTION
  // server via scripts/start-prod.mjs, which copies the static assets into
  // the standalone output - `next start` does not work with a standalone
  // build and serves a shell whose JS 404s, so the suite would test a page
  // that never finishes loading. Locally `next dev` is used so no build step
  // is required.
  // Skipped entirely when E2E_BASE_URL points at an already-running server,
  // so the suite can be run against a preview build without booting a second
  // copy of the app.
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        // The production server's heap is capped; the build's is not.
        //
        // The a11y spec injects axe-core into every route and runs a full
        // analysis on each, which is heavy on its own. With the default
        // heap the server and the browser together crossed the machine's
        // memory limit partway through the suite, and the server was
        // SIGKILLed - which the tests reported as a connection refused,
        // not as a memory problem. Capping the *server* keeps it inside the
        // budget so the suite finishes. The build needs more than the cap
        // allows, so it is deliberately left uncapped.
        command: process.env.CI
          ? 'npm run build && NODE_OPTIONS=--max-old-space-size=256 npm run start:prod'
          : 'NODE_OPTIONS=--max-old-space-size=256 npm run dev',
        url: 'http://127.0.0.1:3000',
        reuseExistingServer: !process.env.CI,
        timeout: 180_000,
        stdout: 'pipe',
        stderr: 'pipe',
      },
};

module.exports = config;
