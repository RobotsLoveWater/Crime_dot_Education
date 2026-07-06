# STYLEGUIDE.md — Minnesota Sentencing Explorer design system

The **design authority** for all UI work in this repo. Any change to `templates/` or
`static/` must follow this document. If an implementation needs to deviate, update this file
in the same commit so it never drifts from reality. Build sequencing lives in
`UI_OVERHAUL_PROMPTS.md`; this file says *what things look like and how they behave*.

Direction (decided with the author, 2026-07): **modern data-tool neutral** — calm slate
surfaces, one vivid accent, data-first density, light **and** dark themes, sidebar-workbench
layout, htmx-driven interactivity, Chart.js visuals. Audience: educators and students, often
on school networks and shared classroom hardware.

## Design principles

1. **The data state is always visible.** The active filter chain and case count are the app's
   core concept; they live in the persistent sidebar, never buried in a page.
2. **Progressive enhancement.** Server-rendered HTML first; htmx and JS make it smoother, not
   possible. Core flows (browse, filter, crosstab, lessons) must work with JS disabled.
3. **No runtime CDN dependencies.** School networks filter CDNs. All fonts, JS libraries, and
   assets are vendored into `static/` and pinned.
4. **Both themes are first-class.** Light and dark ship together; every component is checked
   in both before it lands. Components use tokens only — never a raw hex value.
5. **Plain language over jargon.** Students meet "Compare" before they meet "crosstab";
   filter chips read as sentences, not tokens.

## Design tokens

All tokens live in `static/css/tokens.css`. Components reference tokens exclusively.
Themes switch by setting `data-theme="light|dark"` on `<html>`.

### Color — light theme (default)

| Token | Value | Use |
|---|---|---|
| `--color-bg` | `#F6F7F9` | App background |
| `--color-surface` | `#FFFFFF` | Cards, panels, main area |
| `--color-sidebar` | `#FBFBFC` | Workbench sidebar |
| `--color-border` | `#E4E7EC` | Default borders, dividers |
| `--color-border-strong` | `#CDD3DC` | Input borders, emphasized dividers |
| `--color-text` | `#17202B` | Primary text |
| `--color-text-muted` | `#5B6675` | Secondary text, labels |
| `--color-text-faint` | `#8B95A3` | Placeholders, disabled text |
| `--color-accent` | `#4F46E5` | Primary actions, links, active states |
| `--color-accent-hover` | `#4338CA` | Hover on accent |
| `--color-accent-subtle` | `#EEF0FE` | Selected rows, chip backgrounds |
| `--color-on-accent` | `#FFFFFF` | Text on accent backgrounds |
| `--color-success` / `-subtle` | `#15803D` / `#E8F5EE` | Correct answers, completion |
| `--color-danger` / `-subtle` | `#DC2626` / `#FDEBEB` | Errors, destructive actions |
| `--color-warning` / `-subtle` | `#B45309` / `#FCF3E3` | Warnings, excluded columns |
| `--color-focus` | `#4F46E5` | Focus rings |
| `--overlay` | `rgba(16,19,24,.45)` | Drawer + dialog backdrops |

### Color — dark theme

| Token | Value |
|---|---|
| `--color-bg` | `#101318` |
| `--color-surface` | `#171B22` |
| `--color-sidebar` | `#14181E` |
| `--color-border` | `#262C36` |
| `--color-border-strong` | `#38404D` |
| `--color-text` | `#E7EAEF` |
| `--color-text-muted` | `#A0A9B8` |
| `--color-text-faint` | `#6E7787` |
| `--color-accent` | `#818CF8` |
| `--color-accent-hover` | `#99A2FA` |
| `--color-accent-subtle` | `#23263B` |
| `--color-on-accent` | `#10121A` |
| `--color-success` / `-subtle` | `#3FB966` / `#16281E` |
| `--color-danger` / `-subtle` | `#F87171` / `#2C1A1A` |
| `--color-warning` / `-subtle` | `#E5A54B` / `#2A2118` |
| `--color-focus` | `#818CF8` |
| `--overlay` | `rgba(0,0,0,.55)` |

Dark theme uses **borders, not shadows**, for elevation (shadows are near-invisible on dark).

### Chart palette (both themes)

`--chart-1` `#6366F1` · `--chart-2` `#0EA5E9` · `--chart-3` `#10B981` · `--chart-4` `#F59E0B`
· `--chart-5` `#EF4444` · `--chart-6` `#8B5CF6` · `--chart-7` `#14B8A6` · `--chart-8` `#F472B6`

Heatmap shading (crosstab): a single-hue ramp from `--color-accent-subtle` → `--color-accent`.
The number is **always rendered in the cell** — color is never the only signal.
Implementation (Phase 3): a discrete 8-step ramp (`.heat-1`–`.heat-8` in `components.css`,
`color-mix` of the two tokens), scaled linearly 0→max on the active stat; step 0 is unshaded.
Cell text flips to `--color-on-accent` from step 7; the mix percentages skew away from the
mid-ramp (and dark's step 6 uses a lighter mix) so both text colors keep AA contrast.

### Typography

Font: **Inter variable**, self-hosted at `static/fonts/InterVariable.woff2` (OFL license).
Stack: `"Inter", system-ui, "Segoe UI", Roboto, sans-serif` (`--font-base`).
Mono (column codes, history tokens): `ui-monospace, "Cascadia Mono", Consolas, monospace`
(`--font-mono`).

| Token | Size | Use |
|---|---|---|
| `--fs-xs` | 0.75rem (12) | Chips, badges, chart axis labels |
| `--fs-sm` | 0.8125rem (13) | Dense table cells, sidebar metadata |
| `--fs-base` | 0.875rem (14) | UI default — controls, tables, sidebar |
| `--fs-md` | 1rem (16) | Prose: lesson bodies, landing copy |
| `--fs-lg` | 1.125rem (18) | Section headings |
| `--fs-xl` | 1.375rem (22) | View/page titles |
| `--fs-2xl` | 1.75rem (28) | Landing hero only |

Line height 1.45 for UI, 1.65 for prose. Weights: 400 body, 500 emphasis/buttons, 600
headings/values. **All numeric table cells and stat values use
`font-variant-numeric: tabular-nums` and right alignment.**

### Spacing, radius, shadow, motion

- Spacing scale (`--space-1..8`): 4, 8, 12, 16, 24, 32, 48, 64 px. No off-scale margins.
- Radius: `--radius-sm` 6px (controls), `--radius-md` 8px (cards, tables),
  `--radius-lg` 12px (dialogs, drawers), `--radius-full` 999px (chips, badges).
- Shadow (light theme only): `--shadow-1` `0 1px 2px rgba(16,19,24,.06), 0 1px 3px rgba(16,19,24,.08)`;
  `--shadow-2` `0 4px 12px rgba(16,19,24,.10), 0 2px 4px rgba(16,19,24,.06)`.
- Motion: `--ease: cubic-bezier(.2,.8,.4,1)`; 120ms hovers, 200ms panels/drawers. Everything
  animated is disabled under `prefers-reduced-motion: reduce`.
- Focus: `:focus-visible { outline: 2px solid var(--color-focus); outline-offset: 2px; }`
  on every interactive element. Never `outline: none` without a replacement.

## Theming mechanics

- `<html data-theme="light|dark">`; default follows `prefers-color-scheme`.
- User choice persists in `localStorage` key `theme`; a tiny **inline** script in `<head>`
  applies it before first paint (FOUC guard). Toggle button lives in the top bar.
- Charts read their colors from CSS variables via `getComputedStyle` at render time and
  re-render on theme change (listen for the toggle's custom `themechange` event).

## Layout — the workbench shell

```
┌──────────────────────────────────────────────────────────┐
│ Top bar: brand · Lessons · Authoring* · theme · user      │
├────────────┬─────────────────────────────────┬───────────┤
│ Sidebar    │ Main area                       │ Lesson    │
│ • Data     │ (Statistics / Compare / Filter  │ dock      │
│   state    │  views, swapped via htmx)       │ (lesson   │
│ • Column   │                                 │  mode     │
│   browser  │                                 │  only)    │
└────────────┴─────────────────────────────────┴───────────┘
```

- **Sidebar** (280px): the data-state module (case-count badge, filter chips, clear-data
  with confirm) above the searchable, grouped column browser.
- **Main area**: one view at a time; htmx swaps the fragment, `hx-push-url` keeps URLs
  shareable/bookmarkable.
- **Lesson dock** (380px, lesson mode only): step content, progress, questions. The main
  area shows the live data the step describes.

### Breakpoints

| Range | Sidebar | Lesson dock | Nav |
|---|---|---|---|
| ≥ 1024px | Persistent | Right dock | Top bar |
| 768–1023px | Slide-over drawer (toggle in top bar) | Bottom sheet | Top bar |
| < 768px | Hidden; data state collapses to a bar under the top bar | Bottom sheet | Bottom nav: Explore · Compare · Filter · Lessons |

Touch targets ≥ 44×44px below 1024px.

## Components

- **Buttons.** Variants: primary (accent bg), secondary (surface bg + border), ghost
  (borderless, muted text), danger (danger bg — destructive only). Radius `--radius-sm`,
  weight 500, padding `--space-2 --space-4`. Disabled = real `disabled` attr or
  `aria-disabled`, faint text, no pointer events — **never a live link styled as disabled**.
- **Inputs & selects.** Surface bg, `--color-border-strong` border, radius `--radius-sm`,
  visible `<label>` bound with `for`. Inline validation message in `--color-danger` below the
  field. Radio/checkbox groups wrapped in `fieldset`+`legend`.
- **Searchable picker.** Progressive enhancement over a native `<select>` / checkbox list:
  a text input filters the option list client-side. Keyboard: arrows + Enter, Esc closes.
  Used for column selection (161 options) and categorical filter values.
- **Filter chips** (the data-state module). Radius-full, accent-subtle bg, accent text,
  `--fs-xs`. Text is the human-readable `desc` ("Sentence length > 14"). The chain renders
  in order; clicking a chip = "revert to this step" (confirm); only the **last** chip gets an
  `×` (history is a chain — middle steps can't be removed alone). A count badge above reads
  "12,431 of 294,467 cases". In lesson mode the module shows a distinct **"Lesson data"**
  badge and the student's own chips are hidden, not lost.
- **Badges.** Radius-full, `--fs-xs`, weight 500: count badge (accent-subtle), educator
  badge (warning-subtle), lesson status (success/accent/muted-subtle).
- **Stat cards.** Surface, radius `--radius-md`, `--shadow-1` (light) / border (dark). Value
  in `--fs-xl` weight 600 tabular-nums; label in `--fs-sm` muted above. Used for N, missing,
  mean, median, std.
- **Data tables.** Wrapped in `.table-wrapper` (radius, border, horizontal scroll). Sticky
  `thead` (surface bg, muted 600 text — not accent-filled). Numeric columns right-aligned
  tabular-nums. Row hover `--color-accent-subtle`. Sortable headers get `aria-sort` and a
  direction glyph. Long value lists get a search box + "show more" pagination. On phones:
  sticky first column + horizontal scroll.
- **Heatmap cells** (crosstab). Background from the accent ramp scaled to the active stat;
  number always visible; text flips to `--color-on-accent` past the ramp midpoint.
- **Toasts.** Top-right (top-center on phones), stacked, `role="status"`, auto-dismiss 5s,
  pause on hover. Success/info/danger variants. Flask flashes render into the toast
  container; htmx responses trigger toasts via the `HX-Trigger` header.
- **Confirm dialog.** Native `<dialog>`, radius `--radius-lg`, `--shadow-2`. Required for
  Clear Data and any revert that discards more than one step. Danger button on the right.
- **Segmented control.** Connected button row with exactly one segment active (sort orders;
  crosstab stat toggle N/mean/median/std). Two semantics: form-value state uses
  `aria-pressed`/checked radios; URL-backed state (e.g. sort orders) uses links, with the
  active segment rendered as a non-interactive element carrying `aria-current` (never a live
  link styled as selected).
- **Column browser** (explore sidebar, below the data-state module). All documented columns
  grouped by category — groups come from the `group` attribute on `codebook.xml` entries,
  ordered by `Data.GROUP_ORDER`. Each item: friendly description primary, mono column code
  secondary. Groups are native `<details open>`; a JS-only search box filters items and
  hides empty groups. Excluded columns render disabled (`aria-disabled`, faint) with a
  `title` tooltip saying why. The active column carries `aria-current="page"`.
- **Progress (lessons).** Slim bar + step dots; completed dots accent-filled, current
  outlined. "Step 3 of 7" text alongside — never the bar alone.
- **Empty states.** Icon-light: a short muted sentence + one CTA. Zero-case filter result:
  "Your filters match 0 cases" + "Undo last filter" button.
- **Loading.** Global 2px accent progress bar at the viewport top bound to htmx request
  events; local `.htmx-indicator` spinners on buttons/forms. Full-page navigations that may
  recompute the cache show a submit-spinner + "Computing statistics…" text.

## Charts (Chart.js)

- Vendored at `static/js/vendor/chart.umd.min.js`, pinned (record exact version in a comment
  at the top of the file and in `static/js/vendor/VERSIONS.md`).
- Bars for distributions (top ~20 values + "Other" bucket); horizontal bars when category
  labels are long. Grouped bars for small crosstabs. **No pies, no 3D.**
- Grid lines `--color-border`, labels `--color-text-muted`, font from `--font-base` at
  `--fs-xs`. Tooltips on; animations off (data tool, not a dashboard demo).
- Every chart is a *companion* to a table that carries the same numbers — the chart is never
  the only way to read a value.

## htmx conventions

- Vendored at `static/js/vendor/htmx.min.js`, pinned as above.
- **HTML over the wire — no JSON APIs.** Views are Jinja partials under
  `templates/partials/`; a route serves the full workbench page on normal requests and just
  the fragment when the `HX-Request` header is present (one shared helper in `app.py`).
- View navigation uses `hx-push-url="true"` — every workbench state has a real URL that
  works on hard refresh.
- Errors: `htmx:responseError` raises a danger toast; form validation errors re-render the
  form fragment with inline messages.
- Anything htmx does must have a non-JS fallback (real links, real form posts).

## Accessibility checklist (apply per view, both themes)

- WCAG AA contrast for text and controls in **both** themes.
- `:focus-visible` ring on every interactive element; logical tab order; drawer/dialog trap
  focus and close on Esc.
- Every input has a visible `<label>`; radio groups have `fieldset`/`legend`.
- Tables: `th scope="col|row"`, `caption` (visually hidden is fine), `aria-sort` on sortable
  headers.
- `aria-current="page"` on active nav; toasts `role="status"`; icons paired with text
  (correct/incorrect shows ✓/✗ **and** words **and** color).
- `prefers-reduced-motion` honored; 44px touch targets under 1024px.

## Voice & copy

- Sentence case everywhere (buttons, headings, labels). No ALL CAPS, no `!!!WARNING!!!`.
- Student-facing names: **Statistics** (descriptive stats), **Compare** (crosstab),
  **Filter**, **Lessons**. Technical terms appear in parentheses on first use in a view
  ("Compare (cross-tabulation)").
- Filter descriptions read as sentences: "Sentence length is greater than 14", not
  `f.time.gt.14`. Tokens appear only in mono, and only in educator/authoring contexts.
- Numbers get thousands separators ("294,467"). Stats round per the existing `data.py`
  idiom.
- Errors say what happened and what to do next: "That value isn't a number. Enter a number
  like 14 or 14.5."
- Spelling: **dependent** (the current UI's "Dependant" is a typo; internal route/variable
  names may keep the old spelling — display text must not).

## File organization

```
static/
  css/
    tokens.css        ← all tokens, both themes (this file's tables, in code)
    base.css          ← reset, typography, body, focus, reduced-motion
    components.css    ← everything under "Components"
    views.css         ← per-view layout (workbench shell, lesson dock, landing)
  js/
    vendor/htmx.min.js, chart.umd.min.js, VERSIONS.md   ← pinned, never hand-edited
    theme.js          ← toggle + FOUC guard partner
    app.js            ← pickers, toasts, dialogs, table search (vanilla, no build step)
  fonts/InterVariable.woff2
```

No build step, no Node tooling — files are served as written. `style.css` is retired once
its last consumer is rebuilt (see `UI_OVERHAUL_PROMPTS.md`).
