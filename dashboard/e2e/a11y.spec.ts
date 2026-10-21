/**
 * Accessibility gate.
 *
 * Runs axe-core (WCAG 2.1 A/AA + best-practice) against every route and
 * FAILS the build on any `critical` or `serious` violation.
 *
 * This exists because the contrast and landmark bugs were invisible to
 * every other check we had: TypeScript was clean, the build was green, the
 * e2e suite passed, and 48 elements still failed WCAG AA at 2.56:1. An
 * accessibility regression should be as loud as a type error, so it gets a
 * test that fails CI.
 *
 * `moderate` and `minor` findings are reported but do not fail the build -
 * they are tracked, not blocking.
 */

import { test, expect } from "@playwright/test";
import * as fs from "fs";
import * as path from "path";

interface AxeResult {
  violations: Array<{
    id: string;
    impact?: string | null;
    help: string;
    nodes: Array<{ html: string }>;
  }>;
}

const AXE_SOURCE = fs.readFileSync(
  path.join(__dirname, "..", "node_modules", "axe-core", "axe.min.js"),
  "utf8"
);

const ROUTES = [
  "/",
  "/leads",
  "/find",
  "/sequences",
  "/inbox",
  "/scrape",
  "/settings",
  "/companies",
  "/email-health",
  "/setup",
];

/** Violations at these levels block the build. */
const BLOCKING = new Set(["critical", "serious"]);

test.describe("accessibility", () => {
  for (const route of ROUTES) {
    test(`${route} has no critical or serious accessibility violations`, async ({
      page,
    }) => {
      const consoleErrors: string[] = [];
      page.on("console", (msg) => {
        if (msg.type() === "error") consoleErrors.push(msg.text());
      });

      await page.goto(route, { waitUntil: "networkidle" });
      // Let the data-driven views finish rendering: a violation that only
      // appears once the table has loaded is still a violation.
      await page.waitForTimeout(1200);

      await page.addScriptTag({ content: AXE_SOURCE });
      const result = (await page.evaluate(async () => {
        // axe is injected at runtime, so it is not on the window type.
        return await (
          window as unknown as {
            axe: { run: (ctx: unknown, opts: unknown) => Promise<unknown> };
          }
        ).axe.run(document, {
          runOnly: {
            type: "tag",
            values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "best-practice"],
          },
        });
      })) as AxeResult;

      const blocking = result.violations.filter((v) =>
        BLOCKING.has(v.impact ?? "")
      );

      const report = blocking
        .map(
          (v) =>
            `  [${v.impact}] ${v.id} (${v.nodes.length} node(s)): ${v.help}\n` +
            v.nodes
              .slice(0, 3)
              .map((n) => `      ${n.html.slice(0, 120)}`)
              .join("\n")
        )
        .join("\n");

      expect(
        blocking.length,
        `Accessibility violations on ${route}:\n${report}`
      ).toBe(0);

      // A page that throws a 404 for its own assets renders a dead shell.
      // That is a broken page, not a passing test.
      const assetErrors = consoleErrors.filter((e) =>
        /Failed to load resource/.test(e)
      );
      expect(
        assetErrors,
        `Failed to load resources on ${route}:\n${assetErrors.join("\n")}`
      ).toHaveLength(0);
    });
  }

  test("every page exposes a main landmark and a single h1", async ({ page }) => {
    for (const route of ROUTES) {
      await page.goto(route, { waitUntil: "networkidle" });
      await page.waitForTimeout(600);

      const mainCount = await page.locator("main").count();
      expect(mainCount, `${route} must have exactly one <main>`).toBe(1);

      const h1Count = await page.locator("h1").count();
      expect(h1Count, `${route} must have exactly one <h1>`).toBe(1);
    }
  });

  test("the layout does not shift while data loads", async ({ page }) => {
    // Cumulative Layout Shift above 0.1 is "poor" - the user watches the
    // content jump under the cursor as the table replaces a placeholder.
    for (const route of ["/", "/leads", "/sequences", "/companies"]) {
      await page.addInitScript(() => {
        const w = window as unknown as { __cls: number };
        w.__cls = 0;
        new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            w.__cls += (entry as unknown as { value: number }).value;
          }
        }).observe({ type: "layout-shift", buffered: true });
      });

      await page.goto(route, { waitUntil: "networkidle" });
      await page.waitForTimeout(1500);

      const cls = await page.evaluate(
        () => (window as unknown as { __cls: number }).__cls
      );
      expect(cls, `${route} CLS should be under 0.1 (was ${cls})`).toBeLessThan(
        0.1
      );
    }
  });
});
