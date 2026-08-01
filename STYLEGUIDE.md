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

The categorical series colors. One hue family per slot, ordered so adjacent (and pie-wrap)
slots never share a family — validated visually distinct with the dataviz skill's checker
(worst-adjacent normal ΔE 73.5, CVD ΔE 23.0):

`--chart-1` `#2563EB` · `--chart-2` `#F97316` · `--chart-3` `#059669` · `--chart-4` `#DC2626`
· `--chart-5` `#0891B2` · `--chart-6` `#CA8A04` · `--chart-7` `#8B5CF6` · `--chart-8` `#DB2777`

A device-wide **"Chart colors"** control (top bar → Colors; `static/js/palette.js`) swaps these
tokens app-wide between **Default**, a **Colorblind-safe** set (`[data-palette="cb"]` in
`tokens.css`, theme-aware), and **Custom** (eight user hexes applied inline). It persists to
`localStorage` and, like the theme toggle, dispatches `themechange` so live charts redraw.

Heatmap shading (crosstab): a single-hue ramp from `--color-accent-subtle` → `--color-accent`.
The number is **always rendered in the cell** — color is never the only signal.
Implementation (Phase 3): a discrete 8-step ramp (`.heat-1`–`.heat-8` in `components.css`,
`color-mix` of the two tokens), scaled linearly 0→max on the active stat; step 0 is unshaded.
Cell text flips to `--color-on-accent` from step 7; the mix percentages skew away from the
mid-ramp (and dark's step 6 uses a lighter mix) so both text colors keep AA contrast.

Correlation-matrix variant (Visualize, Phase 13): the same `.heat-N` ramp, but shaded by
**`|r|` on the absolute 0→1 scale** (not the matrix peak) — correlation already has a fixed,
interpretable range, so a shade means the same thing in every matrix. A single-hue ramp can't
encode direction, so the **signed number is always rendered** (real `−` for negatives) and
negative cells carry a non-color cue (`.corr-neg`, dotted underline). Off-diagonal cells at
`|r| ≥ 0.90` are flagged as near-mechanical (`.corr-flag` `●` + tooltip + a text callout) — the
sentencing grid's arithmetic made visible, annotated rather than hidden.

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
| 768–1023px | Slide-over drawer (toggle in top bar) | Stacked panel below the data | Top bar |
| < 768px | Off-canvas drawer, opened by the data-state bar under the top bar | Bottom-sheet panel below the data | Bottom nav: Explore · Compare · Filter · Lessons (+ Author for educators) |

Touch targets ≥ 44×44px below 1024px.

**Phone shell (< 768px, Phase 7).** The top-bar section nav and the ☰ toggle give way
to a fixed **bottom nav** (the same sections, decorative icon + text label,
`aria-current` on the active one) and a full-width **data-state bar** directly under the
top bar. The bar is the drawer trigger: it shows the live case count (and filter/lesson
badge) and, on tap, opens the same off-canvas sidebar drawer used at tablet width — so the
full data state *and* column browser stay reachable (nothing is hidden without a path to
it). Both the tablet ☰ and the phone bar carry `aria-controls="sidebar"`; one drawer, one
focus trap, focus returns to whichever trigger opened it. Wide data tables keep a **sticky
first column** and scroll horizontally *inside* their `.table-wrapper` (never the page).
The lesson dock becomes a polished bottom-sheet-style panel (rounded top, grab handle)
below the read-only data. `env(safe-area-inset-bottom)` pads the bottom nav; the body
reserves its height so the footer is never covered.

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
  badge and the student's own chips are hidden, not lost. When more than the base entry is
  active, a **share-link row** appears below the count badge (Phase 9): the full URL as
  visible/selectable mono text (`--fs-xs`, accent-subtle bg, `text-overflow: ellipsis` so a
  long chain truncates in the narrow column — the untruncated URL is still the real text
  content and a `title` tooltip) plus a `.js-only` "Copy link" button, the same
  `[data-copy]` pattern as the join-code copy affordance below, just sized for a URL instead
  of a short code.
- **Badges.** Radius-full, `--fs-xs`, weight 500: count badge (accent-subtle), educator
  badge (warning-subtle), lesson status (success/accent/muted-subtle).
- **Stat cards.** Surface, radius `--radius-md`, `--shadow-1` (light) / border (dark). Value
  in `--fs-xl` weight 600 tabular-nums; label in `--fs-sm` muted above. Used for N, missing,
  mean, median, std, mode (mode's value carries a `.badge-muted` "+N more" beside it when
  multimodal).
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
- **Toggle switch** (`.switch`). A slider-style on/off control for a single boolean, built over
  a real, focusable `<input type="checkbox">` (visually hidden; still the accessible + form
  control, so it works without JS). CSS track (`--radius-full`, `--color-border-strong` →
  `--color-accent` when checked) + thumb (`--color-surface`, `--shadow-1`, translates on check);
  focus ring on `:focus-visible`. Use for a client-side view option, not for submitting state —
  e.g. the choropleth's "Hatch thin samples" override, `.js-only`, on by default.
- **Map input** (`.filter-map`, Filter view geography columns — Phase 11 of the visualization
  expansion). A canvas map that is an *input device for the form beside it*, never a token
  builder: clicking a shape toggles the same checkbox (county/region) or fills the same numeric
  value input (district) the hand path uses, then fires the form's `change` so the existing
  htmx preview refreshes. Colors are **selection state, not a value ramp**: selected =
  `--color-accent`, selectable (has cases) = `--color-accent-subtle`, no cases in the slice =
  `--color-border`; borders `--color-surface`. `.js-only`; the value list/input stays the
  complete no-JS + screen-reader path (same names and counts as text), and the canvas carries
  `role="img"` with an accessible name pointing at the list. Beside the categorical picker at
  ≥1024px (`.filter-geo-split`, two equal grid columns), stacked below it otherwise.
- **Visualize builder** (`/visualize`, visualization-expansion Phase 3 shell; chart-library-
  expansion Tier A rebuilt the picker onto the registry). A two-column `.visualize-layout` grid —
  `.visualize-form` (the chart **finder**, below, plus column/measure/aggregate/subset/cutoff/
  bins pickers, reusing the `[data-picker]` searchable combobox) on the left, `.visualize-canvas`
  on the right — stacking to one column under 768px. The canvas holds a single **empty state**
  ("pick a chart type", or a per-type placeholder) until a chart renders; a rendered chart fills
  it as `.viz-result` (chart + companion value table — the same "chart is never the only way to
  read a value" rule as Explore/Compare). Field show/hide is **registry-driven**
  (`VIZ_FIELD_CHARTS`, derived from each chart's `inputs`) rather than hard-coded per chart, so a
  new registry entry gets working field visibility for free; the same Column/Second-column
  pickers still re-purpose per chart client-side (e.g. treemap's parent/child, scatter's X/Y,
  line's series split) so one builder serves all 26 chart types with no page reload.
- **Chart finder** (chart-library-expansion Phase A1, replaces the old flat `<select>`). A
  searchable, purpose-grouped card gallery (`VIZ_CHART_GALLERY`) — radio cards (`.viz-chart-card`,
  the no-JS/keyboard-complete path) grouped under the six family headings (Comparison ·
  Composition · Distribution · Trend · Relationship · Geography), each showing the chart's label
  and one-line blurb. A `.js-only` search input filters cards by label + `synonyms` + `tags`
  (e.g. "proportion", "over time", "spread" all surface the right charts) and hides empty groups;
  clearing the search reopens the full grouped list — **searching never hides a chart that isn't
  also reachable by browsing.**
- **Chart info box** (`partials/viz_info_box.html`, chart-library-expansion Phase A1/A2). Renders
  a selected chart's `info{shows, best_for, watch_out}` — three short labeled paragraphs — live in
  the builder as the finder selection changes, and as a collapsible `<details>` "About this chart"
  on the results canvas. `watch_out` is where the honesty pedagogy lives (KDE/violin smoothing
  away round-number clustering, 100%-stacked/mosaic hiding absolute Ns, small-N maps misleading,
  animation dramatizing noise) — never trimmed for length.
- **Map-click filter** (Visualize choropleth). Shapes with data are clickable: pointer cursor
  on hover, a "Click to keep only this …" line in the tooltip, and a **"Keep only" button
  per row** of the companion table (`.viz-keep-cell` / `.viz-keep-form`, a `.btn-sm`
  mini-form) as the keyboard/no-JS twin. Both POST the *existing* filter-apply route
  (`comparison=eq` + the server-shipped dataset value + a server-validated local `next` back
  to the map) — the click is never a bespoke filter path, so the history entry, chip, and
  cache directory are byte-identical to typing the filter.
- **Column browser** (explore sidebar, below the data-state module). All documented columns
  grouped by category — groups come from the `group` attribute on `codebook.xml` entries,
  ordered by `Data.GROUP_ORDER`. Each item: friendly description primary, mono column code
  secondary. Groups are native `<details>` and **start collapsed**; a JS-only search box
  filters items, hides empty groups, and opens the groups with matches (clearing the search
  collapses them all again). Excluded columns render disabled (`aria-disabled`, faint) with a
  `title` tooltip saying why. The active column carries `aria-current="page"`.
- **Progress (lessons).** Step dots + "Step 3 of 7" text (Phase 5): completed dots
  accent-filled, current outlined with an accent-subtle ring; the text always accompanies the
  dots — never dots alone. (The originally-planned slim bar was dropped: a data-driven fill
  width needs an inline `style`, which this guide forbids; the discrete dots carry the same
  signal with tokens only.)
- **Empty states.** Icon-light: a short muted sentence + one CTA. Zero-case filter result:
  "Your filters match 0 cases" + "Undo last filter" button.
- **Landing** (logged-out home / `/landing`). Centered single column inside the main area:
  a hero (accent eyebrow, `--fs-2xl` title — the *only* use of that size — muted lede, one
  primary + one secondary CTA), a row of **honest metric cards** (reuse `.stat-card`,
  centered, value-first: fixed dataset facts "294,467 felony cases", "2001–2019", plus the
  real lesson count), then a **feature-card** grid (surface + border + `--shadow-1`) and a
  final CTA band. No hero background image, no inline styles. Signed-in visitors to
  `/landing` get workbench/lessons CTAs instead of sign-up.
- **Auth cards** (log in / create account). A single centered `.auth-card` (≤420px, surface +
  border + `--shadow-1`) holding a title, a switch link to the other form, an inline
  `.alert-danger` for validation, and `.field` inputs. **Password inputs never carry a
  `value`** — the submitted password is never echoed back into the page source. An **"I'm an
  educator" checkbox** (`.field-check` — an inline checkbox + label, hint on its own line) is the
  only educator signal; the `edu-` classcode is derived on the backend (`edu-<username>`) and
  never shown or typed. The class-code field below it is student-only (blank → public group, else
  a class join code) and, as progressive enhancement, is **hidden by JS when the educator box is
  checked** (`[data-educator-toggle]`/`[data-educator-hide]` in `app.js`; no-JS leaves it visible
  and the server ignores it for educators). The `<form>` is `.auth-form`, which resets the legacy
  `style.css` form box so the card is the only frame.
- **Loading.** Global 2px accent progress bar at the viewport top bound to htmx request
  events; local `.htmx-indicator` spinners on buttons/forms. Full-page navigations that may
  recompute the cache show a submit-spinner + "Computing statistics…" text.
- **Filter preview** (filter view). A single muted line under the filter controls reading
  how many cases a candidate filter would keep ("12,431 of 294,467 cases would match"),
  refreshed live via a debounced htmx `hx-get` as the value/selection changes. The count is
  computed on the server through the same history-override path the apply uses, so the
  preview always equals the post-apply count. A 0-case preview turns `--color-danger` and
  warns that applying would empty the data. No-JS: the line stays a static hint and the form
  still submits. **Categorical value multi-select:** a bordered, scrollable checkbox list —
  each row a value with its right-aligned tabular-nums count — above a JS-only search box and
  "Select shown" / "Clear" actions; eq/ne mode is a `fieldset`/`legend` radio group.
- **MOC stepper** (offense-code filter). A horizontal row of slots, one per editable code
  digit; each shows an uppercase muted label and the decoded value (or an italic faint
  "Any" for a wildcard). The active slot carries the accent border + `aria-current`; INC
  multi-digit sections render as **one** merged slot. Below it, an options table lists each
  choice for the active slot with the case count it would leave. The offense category is a
  leading fixed (dashed) slot.
- **Copy affordance** (e.g. a class join code). The value itself always renders as visible,
  selectable text (`<code>`, `--fs-2xl`, accent-subtle background) so it's readable/copyable
  with no JS. A `.js-only` "Copy" button (`[data-copy]` pointing at the value's selector) is a
  pure enhancement: `navigator.clipboard.writeText`, falling back to a `Range`/`execCommand('copy')`
  selection for older browsers; the button reads "Copied!" for 2s, and a failure raises the
  standard danger toast rather than silently doing nothing.
- **Educator portal** (`/admin*`). Portal home (`/admin`) has two `.portal-section` areas —
  Classes and Lessons — each a `view-header` + `.data-table` (or `.empty-state`) + a primary
  "New …" action, mirroring the existing lesson-authoring list. `/admin/classes` adds a
  `.filter-form`-width create form (name + an optional email-policy fieldset: a checkbox plus
  a comma-separated allowed-domains input) above the same list. `/admin/classes/<id>` shows the
  join code (copy affordance above, with a **rotate** action), a roster `.data-table` (username
  only — no email; minimal PII per `EDUCATOR_PORTAL.md`) with per-student roster actions
  (remove / reset / inspect attempts, and a distinct **danger** full-delete), the email-policy
  form and the **retake & feedback** fieldset (attempts-allowed number + two reveal/tolerance
  checkboxes, its own save), and a **"Class tools"** row linking the progress dashboard, module
  assignments, gradebook download, section comparison, and archive. All destructive actions are
  `[data-confirm]`-gated (full account deletion escalates to its own two-step confirm page).
- **Module assignments** (`/admin/classes/<id>/assignments`, Phase 6). A `.data-table`, one row
  per module: a state `<select>` (optional / required / scheduled / hidden) plus `type="date"`
  open/due inputs that only apply to the **scheduled** state ("scheduled" = required + dates;
  dates on other states are dropped on save). Each row also carries an "Answer key" detail link.
  Student-facing: the lesson catalog reflects the class's states — a `.badge`/`.badge-warning`
  **Required** badge, due-date text, scheduled modules **locked** until their open date, and
  hidden modules absent (public/`unmanaged` users are unaffected and see everything).
- **Progress dashboard** (`/admin/classes/<id>/progress`, Phase 5). Exception-first
  (principle 1): a **"Needs attention"** `.attention-list` at the top — warning-accented cards
  (`.attention-item`, left `--color-warning` border) naming each flagged student and their
  reasons (a `.attention-tag` "Stuck"/"Inactive" chip + a sentence), or a reassuring empty
  state. Below it a **per-student** `.data-table` (sticky first column; the student is a
  `th scope="row"`) with **URL-backed sortable headers** — `.col-sort` links carrying
  `aria-sort` and a direction glyph (`.col-sort-glyph`), the active header accent-colored — and
  score cells showing accuracy % (a `.muted-cell` "—" when not started, a `.cell-done` ✓ when
  the lesson is complete). Then a **per-lesson rollup** table (completion rate, median score)
  and per-lesson **item-level miss rates** in `<details>` (`.rollup-detail`). New badge
  `.badge-warning` (warning-subtle) flags at-risk rows. Numbers only ever come from stored
  progress/attempt logs — nothing is re-graded at render time.
- **Answer-context inspection** (`/admin/classes/<id>/roster/<userid>/attempts`, Phase 10). An
  "Attempts" link on each progress-dashboard row opens a student's full graded history as an
  `.attempt-list` of `.attempt-item` cards (newest first), each a status badge (`.badge-success`
  / new `.badge-danger` / `.badge-muted` for correct/incorrect/ungraded — a left `--color-danger`
  border on incorrect cards via `.attempt-item-incorrect`), the submitted value, and the data
  state **at answer time** as the same read-only `.chip-chain.chip-chain-static` used by the
  lesson dock — so a teacher can tell "filtered the wrong year" from "can't read a median"
  without reconstructing the student's session.
- **Computed answer key** (`/admin/modules/<id>/answers`, Phase 10). Any educator can open any
  module's key — an `.answer-key-list` of `.answer-key-item` cards, one per graded question,
  each showing the live-computed answer (numeric: value ± tolerance; choice: the correct
  option's label; free: the model answer or "no fixed answer") plus the same read-only state
  chips as above. Generated fresh every request — never cached — so it tracks the live dataset.
  Linked from the portal's Lessons list (`admin.html`) and from each row of the per-class
  assignments table (`.row-detail-link`, `--fs-xs` muted) so it's reachable for modules the
  viewing educator didn't author.

## Charts (Chart.js)

- Vendored at `static/js/vendor/chart.umd.min.js`, pinned (record exact version in a comment
  at the top of the file and in `static/js/vendor/VERSIONS.md`).
- Bars for distributions (top ~20 values + "Other" bucket); horizontal bars when category
  labels are long. Grouped bars for small crosstabs. **No 3D, no gratuitous animation.**
- **Pie** is allowed on the **Visualize** tab only, and strictly for **share of cases** across
  one categorical column — never mean/median/mode (a pie is a part-of-whole mark, so a summary
  statistic has no place on it). Hard-cap the slices (top ~12 + "Other"); slice colors cycle
  `--chart-1`…`--chart-8` and the "Other" catch-all uses `--color-text-faint`; separators use
  `--color-surface` so they read in both themes; legend beside the pie on wide canvases, below
  it when narrow.
- **"Other"-cutoff slider** (`templates/partials/other_cutoff_slider.html` +
  `static/js/otherbucket.js`): the reusable long-tail control shared by the Explore distribution
  bar and the Visualize pie **and treemap**. The server pre-buckets a sensible default (also the
  no-JS view) and ships the capped value head plus a residual tail, so dragging re-slices top-N +
  "Other" entirely client-side (no refetch) with "Other" exact at any cutoff. `.js-only`; renders
  nothing when there is nothing to slide.
- **Treemap** (Visualize tab). Two-column nested rectangles (`chartjs-chart-treemap`), sized by
  count **or** a numeric measure+aggregate (mean/median/mode) — the one area mark where an
  aggregate besides count is offered. Leaves color by parent group, cycling `--chart-1`…`--chart-8`;
  the "Other"-cutoff slider applies (a second slider instance, `slider_id` `viz-tree`). Box
  `.viz-treemap-box` (440px; 360px under 768px); companion table lists the same groups and values.
- **Waterfall** (Visualize tab). Year-over-year change in a measure+aggregate across `sentyear`,
  drawn as Chart.js **floating bars** (`[start, end]` data, no plugin) — rising deltas
  `--color-success`, falling `--color-danger` (`.wf-delta-up`/`.wf-delta-down` and
  `.wf-key-up`/`.wf-key-down` share that color language across the note key, the table's Change
  column, and the bars, so a student reads the direction the same way in all three places). An
  optional running-total line (`.wf-toggle`, `.js-only`) overlays the deltas. Box
  `.viz-waterfall-box` (420px; 340px under 768px); the companion is a full year-by-year table with
  a net-change `<tfoot>` row — no "Other"-cutoff slider, since nothing here is bucketed.
- **Choropleth** (Visualize tab, the visualization-expansion centerpiece). A county / judicial-
  district / region **grain toggle** (`.viz-grain`, reuses `.segmented`, htmx-swapped) sits above
  the map; district/region geometry is dissolved from the county TopoJSON at runtime
  (`static/js/geomap.js`), never a separate geometry file. Fill color is the same 8-step
  `.heat-1`–`.heat-8` ramp the crosstab heatmap uses, scaled to the active measure+aggregate; a
  `.viz-legend` below the map shows the ramp's low/high ends, a no-data swatch, and — only when a
  shape falls below the small-N threshold — a **low-N swatch** (`.viz-legend-lown-swatch`, a
  diagonal-stripe token gradient) beside the "Hatch thin samples" toggle (see Toggle switch). Box
  `.viz-map-box` (480px; 380px under 768px). The companion table carries a **"Keep only"** mini-form
  per row (see Map-click filter) and a "Low sample" tag (`.viz-lown-tag`) mirroring the map's hatch
  for the no-JS/screen-reader path.
- **Scatter / bubble** (Visualize tab). One view, not two: two numeric columns aggregate to a
  **lattice** of points (never raw rows — the cell count is capped) plotted as a Chart.js bubble
  chart, radius ∝ √count, so overplotting is impossible by construction. Box `.viz-scatter-box`
  (460px; 360px under 768px); companion table lists each lattice cell's x / y / count / share. No
  "Other"-cutoff slider (nothing here is bucketed).
- **Correlation matrix** (Visualize tab, one of two chart types with no canvas — the other is
  the mosaic, below). A searchable
  checkbox multiselect over 2–8 numeric columns (`.viz-corr-field`/`.corr-picker` — search box,
  live count, a soft 8-item cap, a Clear action) feeds a server-rendered `.corr-matrix` table:
  sticky row headers and a sticky corner cell inside the scroll wrapper (like the crosstab),
  centered tabular-nums cells. Negative values carry a dotted underline (`.corr-neg`) since a
  single-hue ramp can't encode sign; off-diagonal cells at `|r| ≥ 0.90` get a small `●` marker
  (`.corr-flag`) plus a `.corr-callout` box above the table spelling out which pairs are
  near-mechanical — the sentencing grid's own arithmetic, annotated rather than hidden. Computed
  fresh every request, never disk-cached. Color rule: see the correlation-matrix heat-ramp entry
  under "Chart palette" above.
- **Categorical-series family** (bar, lollipop, dot plot, donut, grouped bar, stacked bar, 100%
  stacked bar — chart-library-expansion Phase C1). One box (`.viz-catseries-box`, 480px; 380px
  under 768px) and **one renderer** for all seven variants, driven by each registry entry's
  `variant`. Bar/lollipop/dot are single-series marks over `Data.aggregate_by_group`
  (lollipop/dot draw the tip via an inline `afterDatasetsDraw` plugin — no extra dependency);
  donut is the pie with a cutout; grouped/stacked/100%-stacked read the two-group matrix
  (`Data.aggregate_by_two`, B1), with 100%-stacked normalizing to percent client-side (the
  companion table still carries the real Ns). The "Other"-cutoff slider applies only to
  single-series variants. Colors cycle `--chart-1`…`--chart-8`; companion table each.
- **Line family** (line, area, stacked area, slope, bump — Phase C2). One box (`.viz-line-box`,
  440px; 340px under 768px). Line/area read a single-series `aggregate_by_group` over
  `sentyear`; stacked-area/slope/bump read the two-group matrix (B1). **Bump's rank transform is
  computed server-side** (never in JS), plotted on an inverted y-axis with hand-rolled end labels
  (no datalabels dependency) and capped to the top 8 series so it doesn't spaghetti.
- **Animated time-series** (Phase D5). The same multi-line chart as the line family
  (`.viz-animated-box`, 440px; 340px under 768px) plus a `.viz-player` row below it: a play/pause
  button beside a keyboard-accessible year `<input type="range">` scrubber. **Never autoplays**;
  `prefers-reduced-motion` disables the tween and the play button, leaving the scrubber for
  manual stepping (`.viz-player-reduced` note); the static multi-line chart is the export/fallback
  truth. Companion table = the full per-year matrix, not just the current frame.
- **Histogram + ECDF** (Phase C3). One box (`.viz-distribution-box`, 420px; 320px under 768px).
  Histogram = native adjacent bars over a fine base binning, re-binned by a client-side
  bin-width slider that **merges bars with no refetch** (bars always sum to N at any width).
  ECDF = a stepped line, y-axis 0–1 — the share of cases at or below each value. Companion table
  each.
- **Density (KDE)** (Phase D2). One box (`.viz-kde-box`, 420px; 320px under 768px) with a
  bandwidth slider that **re-convolves the server's shared binned weights client-side** (no
  refetch), clamped to the reported physical bandwidth bounds. **The loudest honesty guardrail in
  the library:** when case mass concentrates on a handful of exact values, a `.viz-spiky-note`
  (`.alert-warning`) nudge toward the histogram is always shown, never suppressed. Companion
  table = the underlying histogram.
- **Box + violin** (Phase D1). One box (`.viz-boxviolin-box`, 440px; 340px under 768px), one per
  group when a second column is picked. Box uses the vendored `@sgratzl/chartjs-chart-boxplot`
  plugin fed the distribution engine's precomputed five-number summary (`whiskerMin`/`whiskerMax`
  explicit, `outliers: []` — counts only, never raw arrays). **Violin is not the plugin's
  `violin` type** (which wants raw arrays) — it's hand-rolled: a bar shell plus a mirrored
  KDE-area polygon per group, clipped to the chart area, sharing one global max width so groups'
  widths stay comparable. `BOXVIOLIN_MAX_GROUPS` caps how many groups render. Companion table
  each.
- **Mosaic** (Phase D3, the one chart type besides the correlation matrix with **no canvas**).
  Server-rendered proportional tiles (`.viz-mosaic-plot`): column width ∝ that column's marginal
  total (`.viz-mosaic-col`), stacked tile height ∝ within-column share (`.viz-mosaic-stack`/
  `.viz-mosaic-tile`), shaded by the same 0→peak `.heat-N` ramp as the crosstab/correlation
  matrix. Long tails fold into one muted "Other" column/tile (`.viz-mosaic-tile--other`) so
  widths and heights still sum to the whole. Inherently screen-reader- and keyboard-friendly (real
  HTML, not a canvas); the companion table is the unfolded crosstab.
- **Pair plot (SPLOM)** (Phase D4). Reuses the correlation matrix's numeric-subset picker,
  hard-capped at **5** columns (tighter than the matrix's 8, for the render-time budget). A k×k
  grid of small square panels (`.viz-pairplot`/`.viz-pair-grid`, one Chart.js instance per panel,
  horizontally scrollable on narrow screens via a `min-width` floor): off-diagonal panels are
  2D-binned scatter (never raw points), diagonal panels are histograms. Column/row headers show
  the mono column code. Companion table = the correlation matrix for the same subset.
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
    vendor/htmx.min.js, chart.umd.min.js, chartjs-chart-treemap.min.js,
           chartjs-chart-geo.min.js, chartjs-chart-boxplot.min.js,
           VERSIONS.md   ← pinned, never hand-edited
    theme.js          ← toggle + FOUC guard partner
    app.js            ← pickers, toasts, dialogs, table search (vanilla, no build step)
    otherbucket.js    ← reusable "Other"-cutoff slider (Explore bar + Visualize pie/treemap)
    geomap.js         ← shared TopoJSON/dissolve plumbing (Visualize choropleth + Filter map)
    visualize.js      ← Visualize-view chart rendering (loaded only by visualize.html)
  fonts/InterVariable.woff2
  geo/mn-counties-topo.json   ← vendored MN-counties TopoJSON (visualization expansion)
```

No build step, no Node tooling — files are served as written. The legacy `style.css` was
**removed in Phase 7**; its still-live base rules (`.container`, bare `h1`/`h2`/`h3`/`p`
sizing + margins) moved into `views.css` / `base.css`, and its last legacy consumer
(`load.html`) was rebuilt on the component system.
