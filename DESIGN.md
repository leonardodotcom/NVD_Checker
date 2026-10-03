# NVD Checker design system (TEXA)

The UI is built on a small, token-driven design system that follows the TEXA brand. Open
**`/static/styleguide.html`** on a running instance to see every token and component live, in light and dark.

```
static/
  brand/texa-logo-white.svg   vector wordmark for dark/brand backgrounds
  brand/texa-logo-navy.svg    vector wordmark for light backgrounds
  favicon.svg                 app mark: the TEXA "T" on the brand gradient
  fonts/                      self-hosted Bitter + Inter (SIL OFL, licences included)
  css/tokens.css              ① design tokens: the single source of truth
  css/components.css          ② reusable components, built only from tokens
  css/app.css                 ③ page layout (sidebar shell, login screen)
  css/styleguide.css          styles for the living style guide only
  styleguide.html             living style guide
```

CSS loads in that order: tokens → components → app. New UI should reuse a component, then add a component, and
only as a last resort add page-specific CSS. **Never hard-code a colour, size or duration. Use a token.**

## Brand

- **Logo.** The wordmark was vectorised from the official TEXA artwork, so it stays crisp at any size. Use the
  white version on navy or gradient backgrounds and the navy version on light backgrounds. Leave generous clear space
  around it, and never recolour or stretch it. If TEXA's official brand guidelines specify clear-space or minimum
  sizes, those take precedence.
- **Primary colour.** `--texa-navy` **#012168**, sampled from the logo. Every other blue is derived from it.
- **Accent.** `--texa-cyan` **#00a3e0**. Use it for gradients, focus rings, the active-item indicator and sort
  arrows only. Never use it for body text on white.

## Colour tokens

| Group | Tokens | Use |
| --- | --- | --- |
| Brand scale | `--texa-navy-950 … --texa-navy-50` | backgrounds, borders, chips, hover states |
| Accent | `--texa-cyan`, `--texa-cyan-300` | gradients, focus, highlights |
| Neutrals | `--gray-900 … --gray-50` | text and surfaces (navy-tinted) |
| Severity | `--sev-critical/high/medium/low/none` | CVSS badges and stat tiles only |
| Semantic | `--color-bg`, `--color-surface`, `--color-text`, `--color-text-muted`, `--color-primary`, `--color-link`, `--color-border`, `--color-danger`, `--color-focus` … | **what components use**; these switch automatically in dark mode |

Components reference **semantic** tokens (`--color-surface`), not palette tokens (`--gray-50`). That is what
makes dark mode a pure token swap.

Every text/background pair used in the UI meets **WCAG AA (≥ 4.5:1)**. The medium-severity amber is the one
exception to white text: it uses `--sev-medium-text` (dark brown) instead.

## Gradients

| Token | Where |
| --- | --- |
| `--gradient-brand` | primary buttons, the "Total" stat tile, the card accent bar, the favicon |
| `--gradient-brand-animated` | sidebar and login background (a slow 18 s drift) |
| `--gradient-text` | page titles (`.gradient-text`) |
| `--gradient-page` | soft cyan/blue radial glows behind the content |
| `--gradient-sheen` | the light sweep across primary buttons on hover |

## Typography

The TEXA wordmark is a heavy, Clarendon-style slab serif with bracketed serifs. The UI pairs it with:

- **Bitter** (`--font-display`): a bracketed slab serif in the same family of shapes. Used for headings, titles
  and big numbers.
- **Inter** (`--font-body`): a neutral, highly legible sans for everything else: body, tables, forms.

Both are self-hosted, so the app works on an intranet with no internet access and keeps the strict
Content-Security-Policy. If TEXA's marketing team has an official corporate typeface, drop its `.woff2` files
into `static/fonts/`, add `@font-face` rules in `tokens.css`, and change `--font-display` / `--font-body`.
Nothing else needs to change.

Scale: `--text-xs` 12 · `--text-sm` 13 · `--text-md` 14 (body) · `--text-lg` 16 · `--text-xl` 20 · `--text-2xl` 26 ·
`--text-3xl` 36. Section labels use `.eyebrow` (uppercase, tracked, muted).

## Spacing, radius, elevation

- **Spacing:** a 4 px grid, `--space-1` (4) … `--space-12` (48).
- **Radius:** `--radius-sm` 6 (inputs, buttons) · `--radius-md` 10 (tiles) · `--radius-lg` 16 (cards) ·
  `--radius-xl` 24 (login card) · `--radius-pill`.
- **Elevation:** `--shadow-sm` (cards at rest) · `--shadow-md` (primary button) · `--shadow-lg` (floating
  panels) · `--shadow-glow` (cyan glow on primary hover) · `--ring` (focus).

## Components

| Component | Class | Notes |
| --- | --- | --- |
| Button | `button`, `.primary`, `.ghost`, `.danger`, `.icon`, `.is-loading` | primary = gradient + sheen; `.is-loading` adds a spinner |
| Field | `input`, `select`, `.field-label`, `.check`, `.inline-form` | cyan focus ring |
| Card | `.card`, `.card.accent-top`, `.card-head` | `accent-top` = gradient bar, for the main card on a page |
| Chip | `.chip`, `.chip .exact`, `.chip.is-new` | trigger words; `is-new` pops in |
| Tag | `.tag`, `.tag.mono` | matched keywords, CWE ids |
| Severity badge | `.sev .sev-CRITICAL` … | critical badge pulses gently |
| Stat tile | `.stats > .stat`, `.stat.total`, `.stat.sev-tile-HIGH` … | number counts up on render |
| Alert | `.alert` | errors (role="alert") |
| Table | `.table-wrap > table`, `th[data-sort]`, `tr.row-in` | sticky header; rows stagger in |
| Skeleton | `.skeleton .w-40/60/80/100` | shimmer placeholder while searching |

## Motion

| Token | Value | Use |
| --- | --- | --- |
| `--ease-out` | `cubic-bezier(.16,1,.3,1)` | entrances, hovers (the default) |
| `--ease-spring` | `cubic-bezier(.34,1.56,.64,1)` | small "pop" moments (chips) |
| `--ease-in-out` | `cubic-bezier(.65,0,.35,1)` | ambient loops |
| `--duration-fast / base / slow` | 150 / 250 / 500 ms | press, hover, entrance |
| `--duration-ambient` | 18 s | background gradient drift |

The animations in use:
- logo blur-in on load;
- drifting gradient and floating orbs on the sidebar and login;
- cards and titles rise in;
- chips pop in when added;
- a sheen sweeps across primary buttons on hover;
- a shimmer skeleton while searching;
- stat counters count up;
- result rows stagger in;
- the critical badge pulses;
- the login card shakes on a wrong password.

**Rules:** motion should explain a change, never decorate idle content (ambient loops are the one exception and
stay slow and low-contrast). Animate only `transform`, `opacity`, `filter` and `background-position`.
`prefers-reduced-motion: reduce` turns everything off. This is handled globally in `tokens.css`, and the count-up
checks it in JS.

## Dark mode

Dark mode follows the operating system (`prefers-color-scheme`). The semantic tokens are redefined to deep-navy
surfaces (`#050b1f` / `#0b1534`), while the brand sidebar and gradients stay the same in both themes.

## Accessibility checklist

- All interactive elements are reachable by keyboard: project items accept Enter/Space, and the focus ring is
  always visible.
- Icon-only buttons have an `aria-label`.
- Errors use `role="alert"`.
- Colour is never the only signal: severity badges also carry their text label.
- Layout works down to 360 px wide with no horizontal page scroll (tables scroll inside their own container).
