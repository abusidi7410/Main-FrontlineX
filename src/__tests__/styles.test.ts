import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Scroll-lock contract for the app shell.
 *
 * The header is `position: sticky` and the document is the page's scroll
 * container. Radix locks the page for every modal layer (profile menu, theme
 * menu, search, mobile nav) by setting `overflow: hidden` on <body>, and the
 * browser honours that lock by propagating <body>'s overflow to the viewport.
 * That propagation only happens while <html> declares no overflow of its own.
 *
 * With `overflow-x: clip` on <html> the lock never reaches the viewport: it
 * lands on <body>, which becomes a scroll container pinned at scrollTop 0. The
 * sticky header then sticks to the top of the *document* rather than the
 * viewport, so every menu opened while the page is scrolled down made the
 * toolbar vanish. Measured against the real stylesheet in headless Edge: at
 * scrollY 1500 the header sat at -1488px (gone); without the <html> rule it
 * stayed at 12px.
 *
 * The horizontal clip still belongs on <body> -- it propagates to the viewport
 * the same way, so nothing can push the page sideways either way.
 */

const css = readFileSync(resolve(process.cwd(), "src", "styles.css"), "utf8");

const ruleBody = (selector: string) =>
  css.match(new RegExp(`(?:^|\\n)\\s*${selector}\\s*\\{([^}]*)\\}`))?.[1] ?? null;

describe("the modal scroll lock reaches the viewport", () => {
  const html = ruleBody("html");
  const body = ruleBody("body");

  it("parses both base rules out of the stylesheet", () => {
    expect(html).not.toBeNull();
    expect(body).not.toBeNull();
  });

  it("<html> declares no overflow, so <body>'s lock propagates to the viewport", () => {
    expect(html).not.toMatch(/\boverflow\b/);
  });

  it("horizontal overflow is still clipped on <body>", () => {
    expect(body).toMatch(/\boverflow-x:\s*clip\b/);
  });
});
