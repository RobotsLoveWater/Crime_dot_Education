# UI/UX Overhaul — Implementation Prompts

Sequenced, self-contained prompts for rebuilding the app's presentation layer into a
**sidebar workbench**: persistent data-state sidebar, htmx-swapped analysis views, Chart.js
visuals, light+dark themes, docked lessons, full responsiveness. Feed **one phase at a time**
to a fresh Claude instance (or use as a dev checklist). Each phase should end green before
the next starts. The design decisions and every visual/behavioral spec live in
**`STYLEGUIDE.md`** — that file is the design authority; this one is the build order.

## How to use this file

- Do the phases **in order** — later phases assume the earlier ones exist.
- Each prompt names the files to read, what to build, and how to know it's done. Keep the
  "Global constraints" below in scope for every phase.
- After each phase: run the app (`uv run flask --app app run`), click through **in both
  themes**, commit on the `ui-overhaul` branch, then move on.
- If a phase forces a deviation from `STYLEGUIDE.md`, update the styleguide in the same
  commit — the two must never disagree.

## Global constraints (apply to every phase)

- **Read `CLAUDE.md` and `STYLEGUIDE.md` first.** Match the `is_logged_in()` route-guard
  pattern and all styleguide tokens/components/conventions.
- **This is a presentation-layer overhaul.** The history→cache substrate, its token encoding
  (`cache.history_item_to_text`), and the account pickles do not change semantics. Same
  filters must produce the same cache directories as before (cache compatibility).
- **Old URLs keep working at every phase boundary** via redirects — lesson deep links
  (`app.build_explore` emits `/info/...` and `/table/...` URLs) and bookmarks must never
  break mid-overhaul.
- **Progressive enhancement.** Core flows work with JS disabled; htmx/JS enhance them.
- **No runtime CDN.** htmx, Chart.js, and fonts are vendored into `static/` and pinned
  (school networks filter CDNs). Record exact versions in `static/js/vendor/VERSIONS.md`.
- **No new Python dependencies** unless truly unavoidable (htmx needs none — it's HTML over
  the wire). Anything new goes through `uv add`.
- **Both themes ship together.** Every component is built and checked light+dark in the same
  phase — dark is not a later pass (Phase 7 is QA, not construction).
- **No new inline styles, ever.** Each screen you rebuild sheds its existing inline styles;
  styles live in the `static/css/` files per the styleguide.
- **No test suite exists.** Verification is manual click-through; each phase's Acceptance
  list is the script.

---

## Phase 0 — Hygiene, tokens, vendored assets (foundations; no redesign yet)

**Goal:** fix the structural/template bugs that would poison every later phase, stand up the
token system and theme toggle, and vendor all assets — while the app still looks essentially
the same.

**Read first:** `STYLEGUIDE.md` (tokens, theming, file organization), `templates/layout.html`,
every child template, `static/css/style.css`.

**Build:**
- **Nested `<body>` fix:** every child template wraps its content in a second `<body>` inside
  `{% block body %}` (see `index.html:7`) — remove them all; validate one page's source by eye.
- **Flash bug:** `layout.html` only renders `get_flashed_messages()` inside `{% if error %}`
  — flashes are silently dropped otherwise. Move flash rendering outside that conditional.
- **Dead "disabled" links:** the active sort option in `info.html` / `filter_boolean.html`
  renders as an `.btn.disabled` that is still a live `<a>` (one with a `occurrencee` typo'd
  href). Make disabled states non-interactive per the styleguide.
- **Copy fixes:** user-facing "Dependant" → "Dependent" (`perm.html`, `perm_menu.html` —
  display text only; the `dependant` route arg stays). Unify every `<title>` to
  "Minnesota Sentencing Explorer — <Page>" (most still say the old "Minnesota Analysis of
  Sentencing Trends" name). Add a favicon.
- **Vendor assets:** `static/js/vendor/htmx.min.js` (2.x) and `chart.umd.min.js` (4.x) with
  `VERSIONS.md`; `static/fonts/InterVariable.woff2` with `@font-face` in `base.css`.
- **Token system:** create `static/css/tokens.css` (both themes, exactly the styleguide
  tables) and `base.css` (reset, typography, focus ring, reduced-motion). Add the
  `data-theme` FOUC-guard inline script to `layout.html`'s `<head>` and `static/js/theme.js`
  with a temporary toggle (it moves into the top bar in Phase 1). Re-point the existing
  `style.css` variables at the new tokens so current pages pick up the new palette/font with
  minimal breakage — component rebuilds come later.

**Acceptance:** app runs; view-source shows one `<body>` per page; a `flash()` message
appears without `error` being set; theme toggle flips every page live and persists across
reloads; devtools Network shows zero external requests; titles/favicons consistent.

**Don't:** redesign any screen, add htmx behavior, or remove `style.css` yet.

---

## Phase 1 — App shell: top bar, sidebar, data-state module, feedback systems

**Goal:** the workbench shell exists; the history table that squats on every page becomes the
sidebar's data-state module; the app gets toasts, loading feedback, and styled errors.

**Read first:** `templates/layout.html` (history table + nav), `app.py` (`/load`,
`/revert/<n>`, session keys), `account.py` (`history_revert`), `STYLEGUIDE.md` (layout,
chips, badges, toasts, dialogs, breakpoints).

**Build:**
- New `layout.html`: top bar (brand, Lessons, Authoring for educators, theme toggle, user
  identity + educator badge, logout) and the sidebar region. Persistent sidebar ≥1024px,
  slide-over drawer 768–1023px, hidden below 768px (phone treatment lands in Phase 7).
- **Data-state module** replaces the history table: live case-count badge
  ("N of 294,467 cases" — the base entry's count is the total), filter chips from
  `user['history']` `desc` fields. Chip semantics per styleguide: clicking a chip reverts to
  that step (confirm via `<dialog>` when it discards >1 step; maps to `/revert/<n>`); only
  the last chip gets an `×`. "Clear data" button here (confirmed) — **remove it from primary
  nav**, where it currently sits in slot #1 unlabeled as destructive.
- Nav renames per styleguide copy: Statistics · Compare · Filter · Lessons, with
  `aria-current="page"`.
- **Toast system** (styleguide spec): Flask flashes render into it; wire the
  `HX-Trigger`-header path for later phases.
- **Loading:** global top progress bar bound to htmx events (htmx is now loaded/initialized
  even though views still full-page-navigate); submit-spinner + "Computing statistics…"
  pattern for form posts that can hit a cold cache.
- Styled 404/500 error handlers and the empty-state component.

**Acceptance:** every existing page renders inside the new shell in both themes; chips match
history exactly and revert/clear work with confirmation; a filter apply shows a toast; the
drawer opens/closes with focus trapped at tablet width; keyboard-only navigation of the
whole shell works.

**Don't:** rebuild view content yet (existing pages render as-is in the main area); no
column browser yet.

---

## Phase 2 — Explore workbench: `/explore`, column browser, Statistics view

**Goal:** the first real workbench views — a searchable, grouped column browser in the
sidebar and a rebuilt column-statistics view with a chart, swapped via htmx.

**Read first:** `app.py` (`/info` routes), `data.py` (`get_column_info`,
`format_column_info`, `VALID_SORTING`), `codebook.xml`, `cache.py` (`get_data`),
`STYLEGUIDE.md` (tables, stat cards, charts, htmx conventions).

**Build:**
- Routes `/explore` and `/explore/column/<column>[/<sorting>]`. One shared helper renders
  the full workbench page normally and just the view fragment when `HX-Request` is present;
  fragments live in `templates/partials/`. Navigation uses `hx-push-url="true"`.
- **Column browser** (sidebar): all 161 columns grouped by category — add a `group`
  attribute to `codebook.xml` entries (or a mapping in `data.py`; pick one, document it) with
  sensible taxonomy (offense, sentence, demographics, criminal history, court/process…).
  Friendly description is the primary label, mono column code secondary. Client-side search
  box filters the server-rendered list. Excluded columns render disabled with a tooltip
  (retiring the `-> !!!WARNING!!!` marker).
- **Statistics view:** stat-card row (N, missing; mean/median/std when numeric), Chart.js
  distribution bar chart (top ~20 values + "Other"; theme-aware per styleguide), segmented
  control for the four sort orders, value table with sticky header + search + "show more",
  and a "Filter this column" CTA (links to the existing filter route until Phase 4 rebuilds
  it).
- **Legacy redirects:** `/info/` → `/explore`, `/info/<col>[/<sorting>]` →
  `/explore/column/...`. Lesson deep links ride these redirects unchanged.

**Acceptance:** browse/search/group all 161 columns; view swaps via htmx with the URL
updating and hard-refresh reproducing the same view; chart matches the table numbers and
re-themes live; `/info/time/occurrence` redirects correctly; both shipped lessons' explore
deep links still land; JS-disabled browsing still works via plain links.

**Don't:** touch crosstab or filter views; don't alter `build_explore`'s emitted URLs yet.

---

## Phase 3 — Compare (crosstab): picker + readable results + CSV export

**Goal:** replace the 161-row × 3-radio-column builder with three searchable selects, and
make results readable at a glance.

**Read first:** `app.py` (`/table` routes and the **intentional X/Y flip** comments),
`templates/perm_menu.html`, `templates/perm.html`, `data.py` (`get_table`), the CLAUDE.md
gotcha on axis flipping.

**Build:**
- `/explore/table` builder: three labeled pickers (Measure: "Count of cases" or
  "Mean of <numeric column>"; Rows; Columns) as progressive enhancement over native selects.
  Labels are honest — the internal X/Y flip is contained and commented in the POST handler,
  not exposed to users.
- Results view: segmented stat toggle (N / mean / median / std — client-side show/hide,
  since all four are already in the payload), heatmap shading on the active stat with
  numbers always visible, row/column totals, sticky headers, and a small Chart.js grouped-bar
  companion for tables up to ~8×8.
- **CSV export:** implement the `/download` stub for the current crosstab (proper
  `Content-Disposition` filename; numbers match the on-screen table).
- Legacy redirects: `/table` → `/explore/table`, `/table/<d>/<x>/<y>` → equivalent.

**Acceptance:** build a crosstab end-to-end from the pickers; **verify orientation with a
known pair** (e.g., rows=race, columns=sentyear) — on-screen layout matches the labels
chosen; stat toggle is instant (no refetch); CSV opens in Excel with matching numbers; old
`/table/...` URLs redirect; lesson `table` deep links still work.

**Don't:** "fix" the internal flip by renaming route args or reordering `get_table` — contain
it in the handler with a comment.

---

## Phase 4 — Filter views: live previews, searchable values, MOC stepper

**Goal:** filtering becomes discoverable and consequence-visible — you see what a filter
will do before you apply it.

**Read first:** `app.py` (`/filter/...` routes, `filter_moc`), `make_history.py`,
`templates/filter_boolean.html`, `templates/moc.html` + `moc1.html`, `data.py`
(`get_moc_options`), `cache.py` (`history_override` — reuse it for previews).

**Build:**
- `/explore/filter/<column>`: **numeric** — comparison select + value input with inline
  validation and a live "~N cases would match" preview (small htmx GET endpoint that
  computes the count via `history_override` with the candidate token — no history mutation);
  **categorical** — searchable multi-select with per-value counts, select-all-visible,
  eq/ne mode (multi-select emits the same `o.` OR-token history entries as today).
- **MOC drill-down:** 5-slot code stepper (each slot shows its digit + decoded meaning;
  wildcard visually distinct; `INC` multi-digit sections render as one merged slot), keeping
  the remaining-counts table below. Replaces the `<h5>` wall in `moc.html`.
- Applying any filter: toast "Filter applied — N cases remain", chips update, land back on
  the view you came from (not a bare redirect home).
- Zero-case guard: a filter that yields 0 rows shows the empty state with an
  "Undo last filter" CTA.
- Legacy redirects for `/filter/...` routes.

**Acceptance:** numeric preview count equals the post-apply chip count; a multi-value
categorical filter produces the **same cache directory** as the old UI would (encoding
unchanged); MOC stepper round-trips including an `INC` section (e.g., codes under `J`);
zero-case state recovers cleanly; JS-off filtering still works (no preview, plain submit).

**Don't:** invent new history token encodings or touch `make_history` semantics — cache
compatibility is the contract.

---

## Phase 5 — Docked lessons + checkpoint wiring

**Goal:** lessons run *beside* live data instead of describing it from another page — and
the broken `checkpoint` step type finally works.

**Read first:** `app.py` (lesson routes, `build_explore`, `compute_expected`,
`grade_and_store`), `lessons.py`, `account.py` (progress/state helpers), lesson templates,
CLAUDE.md "Learning Modules" section (sandbox rules), `STYLEGUIDE.md` (lesson dock,
progress).

**Build:**
- **Lesson mode:** `/lesson/<module_id>/<int:step>` renders the workbench with the lesson
  dock (right dock ≥1024px; bottom sheet below): step body, progress dots, prev/next,
  question forms (POST via htmx with full-page fallback; grading stays server-side,
  unchanged). The **main area** shows the step's data via the Phase-2/3 fragment endpoints
  driven by the step's `focus`; the sidebar data-state module switches to the "Lesson data"
  badge showing the lesson state's chips. The student's real `history` is never shown as
  editable in lesson mode and **never mutated** — the existing `history_override` sandbox
  path does all data work.
- Update `build_explore` deep links to target `/explore/...` directly (redirects made this
  safe to defer until now).
- **Wire `checkpoint`:** compare the student's active lesson state
  (`progress[module_id]['state']`) against the step's `expect_state` as an exact token
  multiset match. Render pass ("✓ Your data matches") or fail with a helpful diff ("Still
  needed: filter Offense to Assault"); gate Next on pass like `require_answer`. Both shipped
  lessons end on a checkpoint — they become completable for real.
- Restyle `lesson_catalog.html` and `lesson.html` per styleguide (status badges, objectives,
  resume button); `/lesson` catalog shows per-module status.
- Restyle `/admin` + `/admin/edit` to the new components (functional parity; no new
  authoring features).

**Acceptance:** play both shipped lessons end-to-end in the dock — explore data live,
answer questions, pass the final checkpoints, see completion in the catalog; after a full
lesson, the user's own chips/history are byte-identical to before it started; checkpoint
fails informatively when the state is wrong; bottom-sheet mode works at tablet width.

**Don't:** merge lesson state into `user['history']` under any circumstances; don't trust a
client-submitted correctness flag; don't change the lesson JSON schema.

---

## Phase 6 — Auth pages, landing, and the logged-in home

**Goal:** the first five minutes — landing, account creation, arrival — match the quality of
the workbench.

**Read first:** `templates/index.html`, `login.html`, `new.html`, `app.py` (`/`, `/new`,
`/login`), CLAUDE.md known issues (session keys, password echo).

**Build:**
- Logged-out landing: hero, honest metric cards (real lesson count, 294,467 cases, 2001–2019),
  feature cards, CTA — all styleguide components, zero inline styles.
- `/login` and `/new` as centered cards: explain the classcode (blank joins the public
  "unmanaged" group; an `edu-` prefix grants authoring), inline validation, and **stop
  echoing the submitted password back into the form** (`login.html` does today).
- Fix the known issue while in here: `/new` sets `session['userid']` but not
  `session['username']`/`session['classcode']` — set all three, matching `/login`.
- Logged-in `/` redirects to `/explore`, with a "Continue <lesson title>" banner/toast when
  an in-progress lesson exists.

**Acceptance:** fresh-eyes run: land logged-out → create an account → arrive in the
workbench with the resume banner absent (new user) → complete a lesson → `/` shows no stale
data; page source of a failed login contains no password value; `/landing` still renders.

**Don't:** implement real password verification (`util.check_password` is wired to nothing —
that's a known issue for its own branch; note it, don't fix it here).

---

## Phase 7 — Responsive deep pass, accessibility, dark QA

**Goal:** the phone experience, the a11y checklist, and a full two-theme sweep — the
"fully responsive, both themes, AA" promises become verified facts.

**Read first:** `STYLEGUIDE.md` (breakpoints, a11y checklist), every view built in Phases 1–6.

**Build:**
- **Phone (<768px):** bottom nav (Explore · Compare · Filter · Lessons), data-state module
  as a collapsible bar under the top bar, data tables with sticky first column + horizontal
  scroll (card-ified rows where a table is narrow enough to convert), lesson dock as a
  polished bottom sheet, 44px touch targets.
- **A11y sweep** per the styleguide checklist on every view: focus-visible, labels,
  `fieldset`/`legend`, `th scope`/`caption`/`aria-sort`, `aria-current`, dialog/drawer focus
  traps + Esc, reduced-motion, color-never-alone (heatmap numbers, ✓/✗ + words).
- **Dark QA:** walk every view in dark — charts, heatmap ramp, chips, dialogs, toasts,
  disabled states; fix any illegible or unstyled spot; verify AA contrast for both themes'
  token pairs.
- Cleanup: delete `static/css/style.css` once nothing references it; grep templates for any
  surviving inline `style=` and remove; confirm `VERSIONS.md` matches vendored files.

**Acceptance:** core flows (filter → statistics → compare → lesson) completed on a 375px
viewport; a11y checklist passes per view; both themes clean end-to-end; zero inline styles
and zero external requests repo-wide; `style.css` gone.

**Don't:** ship phone layouts that hide data with no path to it — horizontal scroll beats
omission.

---

## Appendix A — Locked design decisions (author-approved, 2026-07)

| Decision | Choice |
|---|---|
| CSS | Hand-rolled modern CSS; token system in `STYLEGUIDE.md`; no build step |
| Interactivity | htmx (vendored) + vanilla JS sprinkles; progressive enhancement |
| Charts | Chart.js (vendored) |
| IA | Sidebar workbench (`/explore`), htmx fragment swaps |
| Visual identity | Modern data-tool neutral: slate surfaces, indigo accent |
| Theming | Light + dark from day one; `data-theme` + localStorage |
| Lessons | Docked lesson panel inside the workbench |
| Devices | Fully responsive including phones (bottom nav) |
| Assets | Everything vendored/pinned; no runtime CDN |

## Appendix B — Route surface: old → new

| Old | New | Disposition |
|---|---|---|
| `/info/` | `/explore` | Redirect |
| `/info/<col>[/<sort>]` | `/explore/column/<col>[/<sort>]` | Redirect |
| `/table[...]` | `/explore/table[...]` | Redirect |
| `/filter/boolean/<col>[...]` | `/explore/filter/<col>[...]` | Redirect |
| `/filter/moc/...` | `/explore/moc/...` | Redirect |
| `/load`, `/revert/<n>` | unchanged | Reused by chips/clear |
| `/lesson...`, `/admin...` | unchanged | Re-rendered in workbench/dock |
| `/download` | unchanged | Implemented (crosstab CSV, Phase 3) |
| `/`, `/landing` | `/` redirects to `/explore` when logged in | Phase 6 |
| `/save`, `/other`, `/settings` | unchanged | Still stubs — out of scope |

## Appendix C — Open questions to resolve with the author (Sid)

- **Codebook grouping taxonomy** (Phase 2): the category each of the 161 columns belongs to
  needs domain judgment — draft it, then have Sid review the groupings.
- **Nav copy**: "Statistics" vs "Explore" for the descriptive-stats entry point (styleguide
  currently says Statistics).
- **Heatmap scaling**: linear vs per-row normalization for crosstab shading (start linear).
- **Landing hero image**: `index.html` takes `hero_image_url` — source a real, licensed
  image or drop the photo hero for a typographic one.
- **Out of scope but adjacent**: real password verification and the hardcoded `secret_key`
  — a polished UI makes the app look trustworthy, which makes the auth gap worse. Recommend
  a separate branch immediately after Phase 6.
