/**
 * Production start for the Next.js standalone build.
 *
 * `next build` with `output: "standalone"` produces a self-contained server
 * in `.next/standalone/`, but it deliberately leaves out the static assets
 * (`.next/static`) and the `public/` folder - Next documents that they have
 * to be copied in by hand.
 *
 * `next start` does not work with a standalone build at all: it prints
 * `"next start" does not work with "output: standalone" configuration`
 * and then serves the HTML shell while every JS chunk 404s. The page loads,
 * the client JavaScript never does, and the app sits on a spinner forever -
 * so an end-to-end suite would "pass" against a dead page.
 *
 * This script does the copy and then execs the real standalone server, so
 * `npm run start:prod` behaves identically locally, in CI and in Docker.
 */

import { cp, mkdir } from "node:fs/promises";
import { existsSync } from "node:fs";
import { spawn } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const standalone = path.join(root, ".next", "standalone");

if (!existsSync(standalone)) {
  console.error(
    "No standalone build found. Run `npm run build` first (the build needs API_PROXY_URL set)."
  );
  process.exit(1);
}

await mkdir(path.join(standalone, ".next"), { recursive: true });
await cp(path.join(root, ".next", "static"), path.join(standalone, ".next", "static"), {
  recursive: true,
});
if (existsSync(path.join(root, "public"))) {
  await cp(path.join(root, "public"), path.join(standalone, "public"), {
    recursive: true,
  });
}

process.env.PORT = process.env.PORT || "3000";
process.env.HOSTNAME = process.env.HOSTNAME || "127.0.0.1";

const child = spawn(process.execPath, [path.join(standalone, "server.js")], {
  stdio: "inherit",
  env: process.env,
});

child.on("exit", (code) => process.exit(code ?? 0));
for (const signal of ["SIGINT", "SIGTERM"]) {
  process.on(signal, () => child.kill(signal));
}
