# Learning Modules — Implementation Prompts

Sequenced, self-contained prompts for building the **learning modules** feature (guided
lessons that link the app's statistical-analysis tools). Feed **one phase at a time** to a
fresh Claude instance (or use as a dev checklist). Each phase should end green before the
next starts. The design rationale lives in `CLAUDE.md` → "Planned: Learning Modules
framework"; read that section first.

## How to use this file

- Do the phases **in order** — later phases assume the earlier ones exist.
- Each prompt is written to be pasted whole. It names the files to read, what to build, and
  how to know it's done. Keep the "Global constraints" below in scope for every phase.
- After each phase: run the app (`flask --app app run`), click through, commit, then move on.

## Global constraints (apply to every phase)

- **Read `CLAUDE.md` first.** Match existing conventions and the `is_logged_in()` route guard
  pattern (`if is_logged_in(): ... else: return not_logged_in()`).
- **No database.** Lessons are files under `lessons/`; progress lives on the user pickle.
  Follow the existing pickle/XML/JSON-on-disk philosophy.
- **Don't break existing routes or the history→cache model.** Reuse it, don't fork it.
- **Backwards-compatible account pickles.** Existing users have no `progress` key — read it
  with `user.get('progress', {})`, never assume it exists.
- **Never reach into `user/` or `cache/` as committable content** (git-ignored, private/large).
  `lessons/` *is* committable authored content.
- **No heavy new dependencies.** Prefer stdlib `json`; if markdown rendering is wanted, keep it
  optional/minimal. Add anything new to `requirements.txt`.
- **Data states are history tokens.** A step's `state` is a list of tokens in the exact
  `f.col.op.val` / `o.col.op.v1~v2` encoding from `cache.history_item_to_text`. Reuse that
  encoder/decoder — do not invent a parallel format.

---

## Phase 0 — Module schema + example fixtures (no code paths yet)

**Goal:** lock the on-disk lesson format and ship one real example so later phases have data
to render.

**Read first:** `CLAUDE.md`, `cache.py` (`history_item_to_text`, `_execute`, `get_data`),
`data.py` (`get_column_info`, `get_table`), `codebook.xml` (real column names).

**Build:**
- A `lessons/` directory with `lessons/intro-descriptive-stats.json` (a genuine 4–6 step
  lesson using real columns like `time`, `sentyear`, `moc1`, `race`).
- A short `lessons/README.md` documenting the schema (fields, step types, answer types).
- Follow the schema in the Appendix of this file exactly; if you deviate, update the Appendix
  and the `CLAUDE.md` data-model bullet to match.

**Acceptance:** `json.load` parses every file in `lessons/`; every `state` token round-trips
through the existing history encoder; every column referenced exists in `codebook.xml`.

**Don't:** wire any routes or loaders yet. This phase is data only.

---

## Phase 1 — Loader + progress field (`lessons.py`, account changes)

**Goal:** load/validate modules from disk and give accounts a place to store progress.

**Read first:** `account.py` (whole file — mirror its pickle read/write style), Phase 0 output.

**Build:**
- `lessons.py`: `list_modules()`, `get_module(module_id)`, `validate(module)` — parse the JSON,
  raise a clear error on malformed modules. No Flask imports here (keep it a pure module like
  `account.py`/`data.py`).
- Account helpers (in `account.py`): `get_progress(userid, module_id)`,
  `set_progress(userid, module_id, step, answers=None, completed=False)`. Read with
  `user.get('progress', {})`; create the key lazily on first write. Update `account.create`'s
  `user = {...}` to include `'progress': {}` for new accounts.

**Acceptance:** a scratch call lists the Phase-0 module, reads its steps, and round-trips a
progress write/read for an existing user without disturbing `history`/`saved`.

**Don't:** touch templates or routes yet.

---

## Phase 2 — Catalog + read-only step navigation (routes + templates)

**Goal:** a student can browse lessons and page through `read` steps. No data linkage yet.

**Read first:** `app.py` (`/info` and `/table` routes as the pattern), `templates/layout.html`,
`templates/guide.html`, `templates/info.html`.

**Build:**
- Replace the `/lesson` stub with a catalog route rendering `lesson_catalog.html` from
  `lessons.list_modules()`.
- `/lesson/<module_id>` → overview (`lesson.html`: title, description, objectives, "Start").
- `/lesson/<module_id>/<int:step>` → renders `lesson_step.html` for `read` steps (markdown/HTML
  body, Prev/Next nav, progress indicator). GET only for now.
- All three use the `is_logged_in()` guard. Fix the pre-existing `lesson_guide()` bug (its route
  has `<page>` but the function takes no arg) or remove that dead stub.
- Templates extend `layout.html`. Add a nav link to `/lesson`.

**Acceptance:** logged in, you can open the catalog, enter the Phase-0 lesson, and page through
its `read` steps with working Prev/Next. Logged out redirects to `/login`.

**Don't:** implement questions or apply data states yet — non-`read` steps can render their body
with a "interactive step — coming next phase" placeholder.

---

## Phase 3 — Data-linked `explore` steps (override history + deep-links)

**Goal:** an `explore` step reconstructs its `state` dataset **without clobbering the student's
own `history`**, and deep-links into the existing analysis views.

**Read first:** `cache.py` (`get_data`, `_execute`, note the no-op `history_override` at
cache.py:54), `data.py`.

**Build:**
- **Complete the `history_override` plumbing.** Make `get_data` actually use it
  (`full_history = full_history + history_override`) and add an equivalent override to
  `_execute` so a lesson state can be materialized/cached under its own history path. Keep the
  existing cache-keying scheme (tokens → directory).
- Render an `explore` step by: applying its `state` as an override, showing the resulting
  dataset summary inline, and linking to `/info/<column>` or `/table/...` per the step's
  `focus`. The student's persisted `history` is untouched.
- Store the active lesson state on `progress[module_id]['state']` (not on `history`).

**Acceptance:** opening an `explore` step shows the correct filtered N and a working deep-link;
after visiting, the student's own filter `history` (visible in the `layout.html` table) is
unchanged. Cache directories for lesson states appear under `cache/data/`.

**Don't:** mutate `user['history']` from a lesson under any circumstances.

---

## Phase 4 — Questions + auto-grading

**Goal:** `question` steps accept answers and grade them, with `numeric` graded against **live
computation** on the step's data state.

**Read first:** `data.py` (`get_column_info`, `get_table`), Phase 3 override code.

**Build:**
- `POST` handling on `/lesson/<module_id>/<int:step>` for answer submission.
- Answer types:
  - `choice` — compare to `correct` index.
  - `numeric` — compute the expected value from the step's `state` via `Data`
    (e.g. `{"compute": {"stat": "mean", "column": "time"}}`), grade within `tolerance`. Do **not**
    hardcode the answer in the JSON.
  - `free` — store the response, mark "submitted" (no auto-grade); optionally show a model answer.
- Persist answers + correctness via `account.set_progress`. Show feedback and gate Next on
  answered (configurable per step).

**Acceptance:** a numeric question grades correctly against the live-computed statistic and
stays correct if the lesson's `state` filters change; a wrong choice shows feedback; answers
survive a page reload (read back from progress).

**Don't:** trust client-submitted "correct" flags — always grade server-side.

---

## Phase 5 — Progress persistence, completion, homepage metric

**Goal:** durable progress, resumability, and a real lessons count in the UI.

**Read first:** `templates/index.html` (the hardcoded "Interactive Lessons: 0" and "0"
metric cards), Phase 1 progress helpers.

**Build:**
- Resume: entering a module jumps to the last incomplete step. Mark `completed` when the final
  step is done; show a completion state.
- Catalog shows per-module status (not started / in progress / done) from `progress`.
- Pass a real module count / completion count to `index.html` (replace hardcoded `0`s). While
  there, pass `current_year` and `hero_image_url` (the templates reference them but no route
  supplies them — see `CLAUDE.md` known issues).

**Acceptance:** finish a lesson, log out/in, and the catalog + homepage reflect completion.

**Don't:** recompute progress from scratch on every request if it's costly — it lives on the
pickle already.

---

## Phase 6 — Educator roles + authoring surface

**Goal:** let educators create/manage modules; introduce the missing role concept.

**Read first:** `account.py`, `app.py` `/admin` stub, `/new` and `/login`.

**Build:**
- Add an `is_educator` (or `role`) flag to the account pickle (default `False`; backwards-
  compatible read). Decide how it's granted (e.g., a classcode convention or an admin action).
- Replace the `/admin` stub with an authoring surface: list modules for the educator's
  `classcode`, create/edit a module (write validated JSON to `lessons/`, scoped `author`),
  and validate via `lessons.validate` before saving.
- Guard authoring routes on the educator flag, not just `is_logged_in()`.

**Acceptance:** a non-educator cannot reach authoring routes; an educator can create a module
that immediately appears in the catalog and is loadable end-to-end.

**Don't:** allow arbitrary filesystem paths from form input (sanitize `module_id` → filename).

---

## Appendix A — Module JSON schema (authoritative for Phase 0)

```json
{
  "id": "intro-descriptive-stats",
  "title": "Reading Descriptive Statistics",
  "description": "Interpret means, medians, and distributions of sentence length.",
  "author": "unmanaged",
  "objectives": [
    "Distinguish mean from median",
    "Read a filtered dataset summary"
  ],
  "steps": [
    {
      "type": "read",
      "title": "What is in this dataset?",
      "body": "Markdown/HTML. ~294k Minnesota felony sentences, 2001-2019."
    },
    {
      "type": "explore",
      "title": "Narrow to assault cases",
      "body": "We filter to offenses whose top-level code is Assault (moc1 = A).",
      "state": ["f.moc1.eq.A"],
      "focus": { "view": "info", "column": "time" }
    },
    {
      "type": "question",
      "title": "Average sentence",
      "body": "To the nearest 0.1, what is the mean of `time` for these cases?",
      "answer": {
        "type": "numeric",
        "compute": { "stat": "mean", "column": "time" },
        "tolerance": 0.1
      }
    },
    {
      "type": "question",
      "title": "Mean vs. median",
      "body": "If the mean far exceeds the median, the distribution is likely…",
      "answer": {
        "type": "choice",
        "options": ["Right-skewed", "Left-skewed", "Symmetric"],
        "correct": 0
      }
    },
    {
      "type": "checkpoint",
      "title": "Confirm your filter",
      "body": "Make sure your working data is filtered to assault before continuing.",
      "expect_state": ["f.moc1.eq.A"]
    }
  ]
}
```

**Field notes**
- `state` / `expect_state`: history tokens (`cache.history_item_to_text` encoding). `focus.view`
  ∈ `info | table`; for `table`, supply `dependant`/`x_axis`/`y_axis` instead of `column`.
- `answer.compute.stat` ∈ `mean | median | std | count`, resolved live via `data.py` on the
  step's `state`. Never store the expected numeric answer in the file.
- Keep `id` filename-safe (`[a-z0-9-]`); it is both the JSON key and the URL segment.

## Appendix B — Account `progress` shape

```python
user['progress'] = {
  'intro-descriptive-stats': {
    'step': 3,                       # last-viewed / current step index
    'completed': False,
    'answers': {                     # keyed by step index
      '2': {'value': 41.7, 'correct': True},
      '3': {'value': 0,    'correct': True}
    },
    'state': ['f.moc1.eq.A']         # active lesson data state (never merged into history)
  }
}
```

## Appendix C — Open questions to resolve with the author (Sid)

- **Sandbox vs. carry-over:** **DECIDED — strictly sandboxed.** Lesson `state` is never copied
  into or merged with the student's real `history`; there is no carry-over option. A lesson
  must never mutate `user['history']`.
- **Markdown:** render `body` as Markdown (adds a dep) or author raw HTML (no dep)? 
- **Grading tolerance:** per-question `tolerance`, or a global default? Rounding follows the
  `round(x * 10**p) / 10**p` idiom used across `data.py`.
- **Module discovery:** directory scan of `lessons/` vs. an explicit `lessons/manifest.json`
  ordering file.
- **Role granting:** how does an account become an educator (self-serve classcode convention,
  or manual)?
```
