# Daily UI review

## 2026-10-02

### References reviewed

- [Linear](https://linear.app) — task-focused hierarchy and restrained product chrome.
- [Stripe](https://stripe.com) — clear typography and content-led product presentation.
- [Vercel](https://vercel.com) — strong contrast, concise product sections, and minimal decoration.
- [Framer](https://www.framer.com) — editorial layouts and customer-led visual storytelling.
- [Notion](https://www.notion.com) — approachable, content-first product navigation.
- [Figma](https://www.figma.com) — collaboration-focused product narrative and practical UI context.
- [Ramp](https://ramp.com) — concrete customer outcomes and specific product information.
- [Awwwards SaaS directory](https://www.awwwards.com/websites/saas/) — examples for reviewing current SaaS presentation patterns.

The requested searches for “best SaaS dashboard UI design 2026”, “modern web app frontend trends 2026”, and “award winning UI examples linear.app stripe.com” were also attempted. Search pages did not expose usable result listings in this environment, so the review relied on the product sites above rather than attributing claims to search snippets.

### Frontend review and changes

- Kept the existing green primary and role-specific, service-backed dashboard data; removed decorative dashboard circles, ambient page glow, and marketing-page radial decorations.
- Replaced Inter and DM Sans with Geist for interface and display typography.
- Replaced embossed, double-sided shadows with restrained surface and overlay shadows; removed blur/translucency from shared cards, application navigation, and sheet surfaces.
- Standardized shared panel corners and interactive transitions, simplified the admin greeting and pricing introduction into content-led, left-accented headings, and replaced the landing page's three-column icon cards with a two-column editorial feature list.
- Shifted dark surfaces and borders from blue-tinted navy toward neutral zinc while retaining the existing theme toggle and semantic status colors.
- Updated the browser theme color to match the green primary.

### Verification and scope

- Validation: `npm run build` and `npm run typecheck`; edited TypeScript files pass ESLint with its Prettier rule disabled. The full-repository lint command is blocked by pre-existing CRLF-versus-LF Prettier errors across the repository.
- This is a one-time review. No daily scheduler or autonomous design-review service is configured by this workspace.

## 2026-10-02 (second pass)

### Direction

The earlier entry kept the green primary and moved dark surfaces toward neutral zinc. This pass changes
the visual direction deliberately, at the user's request, to **refined institutional**: deep navy/ink
foundation with brass accents and confident serif display headings. Geist stays on body and interface
text so dense tables, forms and figures keep their legibility.

### Design system

- Replaced the green primary with deep navy (`222 62% 21%`) and introduced a brass accent family
  (`--brass`, `--brass-foreground`, `--brass-soft`) plus `--shadow-brass`. Surfaces moved from neutral
  gray to a warm parchment base.
- Added **Fraunces** as the display face, loaded with `SOFT` and `WONK` held at zero for a classical
  rather than quirky serif; headings track slightly looser to suit the serif.
- Added two system utilities: `fn-rule` (brass hairline) and `fn-eyebrow` (uppercase micro-label).
- Tightened the base radius from `0.75rem` to `0.625rem` and recolored every shadow navy-tinted
  rather than neutral black.

### Shell

- The sidebar is now a deep navy rail with a brass gradient cap, brass active indicator and brass active
  icons; nav states resolve against `sidebar-*` tokens so they work in both themes. The mobile nav sheet
  matches it.
- `PageHeader` gained the brass kicker rule and an optional `eyebrow`; `StatCard` gained an eyebrow label,
  a brass icon tile and a KPI rule; `BrandMark` became a brass crest whose ink "FN" reads as an engraved
  seal. `BrandLockup` took an explicit `tone` prop because it is also used on the light marketing pages.

### Bugs found and fixed

- `--shadow-*` tokens sat inside `@theme inline`, which bakes literal values into utilities, so
  `shadow-overlay`/`shadow-raised`/`shadow-glow` in dialogs, sheets, select and pricing were frozen to
  light-mode values and dead in dark mode. Moved to `:root`/`.dark` only, with all call sites switched to
  `shadow-[var(--shadow-*)]`.
- While doing that, the rewritten `:root` block dropped the light `--shadow-*` declarations entirely and
  left light mode with no shadows at all. Caught by inspecting the compiled CSS rather than trusting a
  green build.
- WCAG checks on the new palette found brass buttons at 3.42:1 and dark-mode primary at 4.15:1. Brass now
  uses ink-on-gold text (5.18:1) and dark-mode primary was lightened to `217 78% 60%` (5.46:1). The mobile
  tab bar was also using brass text on a pale tint for a real 10px label at 3.08:1 and now uses foreground
  text, keeping brass for the tint and rail.

### Verification and scope

- Validation: `npm run typecheck`, `npm run test` (110 passed across 12 files), `npm run build`, and ESLint
  on every edited TypeScript file. The compiled CSS was inspected directly to confirm the tokens, the new
  utilities and both themes' shadows were actually emitted.
- Scope: design system and application shell only. Individual screens inherit the refreshed system but have
  not been individually reworked yet.
- `src/styles.css` does not satisfy `prettier --check`, but neither does its previous committed version;
  the file has never been Prettier-formatted and the edits match its existing style, so it was left alone
  rather than reformatted into an unrelated diff.

