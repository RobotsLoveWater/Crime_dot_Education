# Educator Portal & Class-Code System — Implementation Prompts

Sequenced, self-contained prompts for building the **educator portal** and a real **class-code
system** on top of MAST / Minnesota Sentencing Explorer, plus the **authentication hardening**
that exposing student data requires. Feed **one phase at a time** to a fresh Claude instance (or
use as a dev checklist). Each phase should end green before the next starts.

Two documents govern this work; read both before starting:
- **`EDUCATOR_PORTAL.md`** — the **scope & design authority**: features (P0/P1/P2), the resolved
  class & identity model, privacy rules, and the open questions. This doc is the *build order*.
- **`STYLEGUIDE.md`** — the **visual authority**: tokens, components, layout/breakpoints, htmx
  conventions, a11y. Any template/CSS change follows it; deviations fold back into it in the
  same commit.

Also read **`CLAUDE.md`** first — the architecture, the history→cache substrate, and the
`is_logged_in()` route-guard pattern all still hold.

Scope of this plan: **auth hardening + all of P0 (features 1–6) + all of P1 (features 7–12)**.
P2 (fork-and-edit, standards tags, full authoring UI) stays out of scope.

## How to use this file

- Do the phases **in order** — later phases assume earlier ones exist.
- Each prompt names the files to read, what to build, how to know it's done, and what not to do.
  Keep the "Global constraints" below in scope for every phase.
- After each phase: run the app (`uv run flask --app app run`), click through the new flow **in
  both themes**, commit on the `educator-portal` branch, then move on.
- If a phase forces a deviation from `EDUCATOR_PORTAL.md` or `STYLEGUIDE.md`, update that
  document in the same commit — the docs and the code must never disagree.

## Complexity ratings (which model to reach for)

Each phase carries a **Complexity** line. Use it to pick a model:

| Rating | Meaning | Suggested model |
|--------|---------|-----------------|
| **Low** | Mechanical; closely follows an existing pattern; few files; low blast radius. | Haiku 4.5 or Sonnet 5 |
| **Medium** | Several files and some design judgment, but still pattern-guided. | Sonnet 5 |
| **High** | Cross-cutting, security-sensitive, or real design decisions with sharp failure modes. | Opus 4.8 |

These rate *inherent difficulty / risk*, not size. A High phase may be small but easy to get
subtly wrong (auth), a Low phase may touch many lines of boilerplate.

## Global constraints (apply to every phase)

- **File-based, no database.** Classes are JSON under a git-ignored `classes/`; attempt logs are
  JSONL under the git-ignored `user/` tree. No new datastore.
- **Route guards.** Match the existing pattern: `is_logged_in()` for any data route,
  `require_educator()` for authoring/portal, and the new `require_class_owner(class_id)` for
  per-class views. Never expose one educator's class to another.
- **Privacy / minimal PII** (`EDUCATOR_PORTAL.md` → Privacy). Dashboards show display
  names/usernames, **never emails**; emails appear only in roster management, only to the owning
  educator. Students see only their own class's assigned content. Assume minors.
- **The history→cache substrate does not change semantics.** The token encoding
  (`cache.history_item_to_text`) and cache directory keys stay compatible; lessons stay
  sandboxed (never mutate `user['history']`) — the one exception is the *shareable data state*
  feature (Phase 9), which deliberately applies to the student's own history.
- **Progressive enhancement.** Core flows work with JS off; htmx/JS enhance them.
- **No runtime CDN, no new Python dependencies.** Config reads from the environment via stdlib
  `os.environ`; `bcrypt` is already a dependency. Anything genuinely unavoidable goes through
  `uv add` and must be justified.
- **Both themes ship together; no new inline styles.** New component specs fold into
  `STYLEGUIDE.md` in the same phase.
- **Branch `educator-portal`; commit per phase.** No test suite exists — each phase's Acceptance
  list is the verification script (manual click-through).
- **Back-compat.** Read new keys defensively (`user.get('classes', [])`, `class.get(...)`), as
  `progress` already does. Pre-existing accounts and bare `user/<code>/` directories must keep
  working.

---

## Phase 0 — Authentication & config hardening

**Complexity: High — Opus 4.8.** Security-sensitive and easy to get subtly wrong: the
hash/escape interplay can silently lock out every existing account.

**Goal:** make login actually verify passwords and get the Flask `secret_key` out of source,
because every later phase exposes identifiable student data.

**Read first:** `app.py` (`/login`, `/new`, `logout`, `app.secret_key` at the top), `account.py`
(`create`, `retrieve`, `form_userid`), `util.py` (`get_hashed_password`, `check_password`),
`EDUCATOR_PORTAL.md` (Privacy & compliance), `CLAUDE.md` (Known issues).

**Build:**
- **Verify the password in `/login`.** After confirming the username exists, load the account and
  check `util.check_password(<normalized password>, user['password'])`. On mismatch, reject.
  - **The escape gotcha:** `/new` hashes `html.escape(request.form['password'])`, so login must
    normalize identically before comparing, or every stored hash mismatches. Introduce one
    `normalize_password()` helper used by **both** create and verify so they can never drift, and
    comment loudly that changing it invalidates existing hashes (needs a migration).
  - **No user enumeration on the password path:** unknown-username and wrong-password should
    produce the **same** generic "Username or password is incorrect" message on `/login`.
- **Move `secret_key` out of source.** Read `SECRET_KEY` from the environment; when unset, fall
  back to a clearly-marked dev key **and log a visible warning** (sessions won't be portable
  across machines/restarts without a stable key — document that). Keep it stdlib (`os.environ`),
  no new dependency. Remove the literal key from `app.py`.
- **Confirm the already-fixed account bugs still hold** (`/new` sets all three session keys;
  `account.create` returns `retrieve(userid)`) — no change, just verify.
- Update `CLAUDE.md` "Known issues": strike the two auth bullets once done.

**Acceptance:** an existing account logs in with the right password and is rejected with the
wrong one; unknown user and wrong password give the *same* message; the literal `secret_key` is
gone from `app.py` and the app reads it from the environment (with a dev-mode warning when
unset); `/new` still works end-to-end.

**Don't:** change the hashing scheme or drop the `html.escape` normalization without a migration
(it invalidates every stored hash); add a config dependency; reveal which of username/password
was wrong.

---

## Phase 1 — Class data model: `classroom.py` + `classes/` store

**Complexity: Medium — Sonnet 5.** A new pure module with real schema design, but it mirrors
`lessons.py`/`account.py` closely and has no UI.

**Goal:** a first-class Class object and the module that manages it — no routes yet.

**Read first:** `account.py` (the pickle pattern, `form_userid`, `clean_classcode`,
`is_educator_*`), `lessons.py` (the pure-module `validate`/`get`/`save` pattern, `ID_PATTERN`,
path-traversal guards), `EDUCATOR_PORTAL.md` ("Class & identity model"), Appendix A below,
`.gitignore`.

**Build:**
- New **`classroom.py`** (pure stdlib, no Flask), storing `classes/<class_id>.json`. Functions:
  - `create_class(owner_userid, name, email_policy=None)` → generate an **immutable** `class_id`
    (`slugify(name)` + short random suffix, made unique) and a `join_code` (short, from an
    unambiguous alphabet — no `0/O/1/I/L`); write and return the class dict.
  - `get_class(class_id)` — load + `validate`; `ClassError` on missing/invalid; `ID_PATTERN`
    guard (mirror `lessons.get_module`, blocks path traversal).
  - `list_classes(owner_userid)` — the educator's classes, sorted (name or created).
  - `find_by_join_code(code)` — **case-insensitive** scan for a non-archived class; returns the
    class or `None`. (Linear scan over `classes/` — fine at classroom scale.)
  - `enroll(class_id, student_userid)` / `remove_student(class_id, student_userid)` — roster ops.
  - `rotate_join_code(class_id)` → new unique code; **must not touch `class_id` or the roster**.
  - `set_assignments(class_id, assignments)` and getters — per-module state map.
  - `set_email_policy(class_id, policy)`; `archive(class_id)` / `unarchive`.
  - `validate(class_obj)` — structural checks (mirror `lessons.validate`): required fields,
    `class_id` matches filename stem, `join_code` format, roster is a list of strings, assignment
    shape, etc.
- **`.gitignore`:** add `classes/`.
- **Concurrency:** last-write-wins is acceptable at this scale; note it in the module header.

**Acceptance:** a scratch script can create a class; find it by join code case-insensitively;
enroll and remove a student; rotate the code (roster preserved, `class_id` unchanged); assign a
module; archive it. `classes/` is git-ignored; invalid ids raise; `validate` rejects malformed
files. No Flask, no pandas, no routes.

**Don't:** import Flask/pandas; store PII beyond userids in the class file (display names come
from the account at render time); let `rotate_join_code` change the id or drop the roster.

---

## Phase 2 — Class-code wiring & enrollment (+ email-domain policy)

**Complexity: High — Opus 4.8.** Touches account creation, sessions, and the auth path; the
overloaded code resolution and student namespacing are easy to break.

**Goal:** the signup "code" box becomes meaningful — it resolves to public / educator / class
enrollment / error — and students land in a real class.

**Read first:** `app.py` (`/new`, `/login`, session keys), `account.py` (`create`, `form_userid`,
`clean_classcode`, `is_educator_classcode`, `get_user_list`), `classroom.py` (Phase 1),
`templates/new.html`/`login.html`, `EDUCATOR_PORTAL.md` ("Class & identity model", feature 3),
Phase 0's auth changes.

**Build:**
- **Overloaded resolution in `/new`** (the single "code" field):
  - blank → public / `unmanaged` (unchanged);
  - starts with `edu-` → educator account (unchanged; `is_educator=True`);
  - matches a live `join_code` → **student enrollment**: create the account namespaced under the
    class (`classcode = class_id`, so storage is `user/<class_id>/<username>.pickle`),
    `is_educator=False`, then `classroom.enroll(class_id, userid)` and record `classes:[class_id]`
    on the pickle;
  - anything else → error ("No class found with that code"), creating nothing.
- **Email-domain policy (feature 3):** when the resolved class requires it, reject a username
  that isn't an allowed-domain email, with a clear message. (The educator *sets* the policy in
  Phase 3; enforcement lives here because it's a join-time check.)
- Give `account` a class-aware creation path so the `class_id` namespacing + `classes` key + role
  are set atomically (extend `create` or add a helper); keep `edu-`/blank behavior identical.
- **Optional logged-in "Join a class"** route (`/join`, GET form + POST) for an existing account:
  same lookup + `enroll` + append to `classes`.
- Update the `new.html`/`login.html` field hint: blank = public, `edu-` = educator, otherwise
  "enter your class join code."

**Acceptance:** signing up with a valid join code enrolls the student under `user/<class_id>/`,
adds them to the roster, sets `classes` on the pickle, and does **not** grant educator; an `edu-`
code still makes an educator; a bogus code is rejected with nothing created; an email-policy
class rejects a non-conforming username; existing accounts still log in (Phase 0 intact).

**Don't:** grant educator to a student who typed a join code; let the class roster and the user's
`classes` drift out of sync; break the `edu-`/blank/`unmanaged` paths.

---

## Phase 3 — Portal shell + class create / list / detail

**Complexity: Medium — Sonnet 5.** Several routes and templates, but standard CRUD over the
existing component system.

**Goal:** `/admin` becomes a real portal; an educator can create classes, see them, and read a
class's join code.

**Read first:** `app.py` (`/admin`, `/admin/edit`, `require_educator`, `slugify`),
`templates/admin.html`/`admin_edit.html`, `templates/layout.html` (shell, nav, `view-header`,
`data-table`, `empty-state`), `classroom.py`, `STYLEGUIDE.md`, `EDUCATOR_PORTAL.md`.

**Build:**
- Add **`require_class_owner(class_id)`** (educator *and* owns the class; else redirect/403).
- Restructure `/admin` into a **portal home** with **Classes** and **Lessons** (the existing
  authoring) areas. Keep `/admin/edit` lesson authoring unchanged.
- Routes:
  - `/admin/classes` — list the educator's classes (name, join code, roster size, links) + a
    "New class" affordance.
  - create a class (name; optional email policy) → `classroom.create_class`.
  - `/admin/classes/<class_id>` — class detail: name; the **join code shown prominently** (with a
    copy affordance; rotate lands in Phase 8); roster (usernames/display names); an email-policy
    toggle (setting persists; enforcement already wired in Phase 2); placeholder links for
    progress (Phase 5) and assignments (Phase 6).
- New templates (`admin_classes.html`, `admin_class.html`) on the component system — `.field`
  forms, `.data-table`, empty states — in both themes and responsive.
- Point the "Authoring" nav entry at the portal home (keep it educator-gated).

**Acceptance:** an educator creates a class, sees it listed, opens its detail, and reads the join
code; a non-owner educator cannot open another's class (guard); non-educators can't reach any
`/admin/*`; the lesson-authoring screens still work; both themes + phone render cleanly.

**Don't:** show emails to anyone but the owning educator; build rotate/remove/reset (Phase 8) or
real progress (Phase 5) yet.

---

## Phase 4 — Attempt-logging foundation (feature 5 backend)

**Complexity: Medium — Sonnet 5.** A focused backend hook plus a format decision; minimal UI.

**Goal:** durably log every graded attempt (with the filter-state at answer time) so the
dashboard, item analytics, and answer-context inspection all read one source.

**Read first:** `app.py` (`grade_and_store`, `compute_expected`, `build_question`, `lesson_step`,
`resolve_lesson_state`), `account.py` (`get_progress`/`set_progress`), `EDUCATOR_PORTAL.md`
(feature 5, open question 1), Appendix B below, `CLAUDE.md` (Learning Modules).

**Build:**
- In `grade_and_store`, **append** an attempt record to a per-student append-only JSONL log:
  `{ts, module_id, step, type, correct, submitted, state}` where `state` is the resolved lesson
  state tokens at answer time (reuse `resolve_lesson_state`). See Appendix B.
  - **Recommended location** (resolves open question 1): `user/<class_id>/<username>.attempts.jsonl`
    — per-student files avoid class-wide write contention, and the class folder *is* the semester
    archive. Already git-ignored under `user/`.
- Add a small pure module **`analytics.py`** (stdlib): `log_attempt(userid, record)`,
  `read_attempts(userid)`, and `question_stats(class_obj, module_id)` (iterate the roster, read
  each log, aggregate per-question correct/attempt counts + last-active).
- Keep `progress['answers']` exactly as-is (it drives resume/feedback and stores only the latest
  answer) — the JSONL is the *history* of attempts.

**Acceptance:** answering a question appends a well-formed line including the state token; repeat
attempts accumulate while `progress['answers']` still holds only the latest; `question_stats`
returns correct per-question rates for a hand-checked class; logs are git-ignored.

**Don't:** replace `progress['answers']`; trust any client "correct" flag; log PII beyond
userids/answers.

---

## Phase 5 — Progress dashboard + "needs attention" triage (features 1 & 2)

**Complexity: High — Opus 4.8.** Cross-account aggregation, triage heuristics, and the portal's
largest UI — the analytical centerpiece.

**Goal:** answer "who needs my attention today?" at a glance, then let the teacher drill into
per-student and per-module detail.

**Read first:** `app.py` (`module_status`, `resume_step`, `lesson_catalog`),
`account.py` (`retrieve`, `get_progress`), `classroom.py`, `analytics.py` (Phase 4),
`lessons.py` (`list_modules`), `EDUCATOR_PORTAL.md` (principles 1–2; features 1, 2, 5),
`STYLEGUIDE.md`.

**Build:**
- On the class detail (or `/admin/classes/<id>/progress`):
  - **"Needs attention" list at the top** (feature 2 / principle 1): students with repeated
    failed attempts on one question, or long inactivity mid-module. Define the heuristics
    explicitly (e.g. ≥3 incorrect attempts on one question with no later correct; or last-active
    older than N days while a required module is incomplete). Reads the attempt log + progress.
  - **Per-student rows:** modules started/completed, per-module score, last-active timestamp.
    Sort/filter by module, completion, and last activity.
  - **Per-class rollup:** completion rate per module, median score per module, and **item-level
    miss/attempt rates** per question (from `analytics.question_stats`).
- **Minimal PII:** display names/usernames only — no emails.
- Templates/partials on the component system; both themes; tables scroll with a sticky first
  column per the phone shell.

**Acceptance:** the educator sees the triage list first, then a sortable per-student table and
per-module rollups with item-level miss rates; a spot-checked student's scores/timestamps match;
emails never appear; renders in both themes and on phone; stays responsive for a section of ~80.

**Don't:** read students outside the class; re-grade every cell live (read stored
progress/attempt logs — answers were already graded); bury the exception list below the tables.

---

## Phase 6 — Module assignment control + student badges (feature 4)

**Complexity: Medium — Sonnet 5.** A class field plus student-catalog changes and light date
handling.

**Goal:** teachers assign and pace modules; students see required/scheduled/hidden state.

**Read first:** `classroom.py` (assignments), `app.py` (`lesson_catalog`, `render_landing`,
`in_progress_lesson`, `lesson_overview`), `lessons.py` (`list_modules`),
`templates/lesson_catalog.html`, `EDUCATOR_PORTAL.md` (feature 4), `STYLEGUIDE.md`.

**Build:**
- Educator: per-module **assignment control** on the class detail — state ∈ `required` /
  `optional` / `hidden` / `scheduled` (scheduled = required + open and/or due date). Persist to
  the class `assignments` (ISO dates).
- Student: the lesson catalog reflects the class's assignment states — required badges, due
  dates, hidden modules absent, scheduled modules locked until their open date.
- **Catalog filtering** (resolved sub-decision): an enrolled student sees only their class's
  **non-hidden assigned** modules; public/`unmanaged` users keep seeing every module. Update
  `lesson_catalog`, and the landing count (`render_landing`) + resume (`in_progress_lesson`) to
  use the assigned set for enrolled students.

**Acceptance:** setting a module required-with-due-date shows the badge + date on the enrolled
student's catalog; a hidden module disappears for students but stays visible/authorable to the
educator; a scheduled module is locked before its open date; public users are unaffected; a
class with no `assignments` degrades to "all modules optional."

**Don't:** hide a module from the educator's own views; change lesson URLs or the grading path.

---

## Phase 7 — Gradebook CSV export (feature 6)

**Complexity: Low — Sonnet 5.** Reuses the existing CSV/BOM/`Content-Disposition` pattern; mostly
plumbing. (P0 — do **not** let it slip.)

**Read first:** `app.py` (`crosstab_csv` and `/download` — the CSV idioms), `classroom.py`,
`account.get_progress`, `lessons.list_modules`, `EDUCATOR_PORTAL.md` (feature 6, open question 4).

**Build:**
- `/admin/classes/<id>/gradebook.csv` (owner-guarded) → one **flat** CSV: one row per student,
  columns per module (completion + score) + timestamps, so it imports cleanly into Canvas /
  Google Classroom / PowerSchool (no merged headers). UTF-8 BOM + `Content-Disposition` (reuse
  the `crosstab_csv` idioms).
- **Define "complete"** (open question 4): pick a default (e.g. the module `completed` flag) and,
  if cheap, expose it as a per-class setting; document the choice here and in `EDUCATOR_PORTAL.md`.
- A "Download gradebook" button on the class detail.

**Acceptance:** the CSV downloads, opens cleanly with flat columns, and matches the dashboard;
owner-guarded; BOM present.

**Don't:** reimplement CSV writing from scratch; include emails by default (display name +
username).

---

## Phase 8 — Roster management (feature 7)  · P1

**Complexity: Medium — Sonnet 5.** Destructive operations need confirmation and care, but the
CRUD pattern is clear.

**Read first:** `classroom.py` (roster/rotate/archive), `account.py` (`retrieve`, progress),
`app.py` (`require_class_owner`, class detail), `templates/layout.html` (`[data-confirm]`
dialog), `EDUCATOR_PORTAL.md` (feature 7; Privacy → educator-initiated deletion), `STYLEGUIDE.md`.

**Build:** on the class detail, owner actions (all `[data-confirm]`-guarded):
- **Remove a student** from the class (roster + the student's `classes` entry; keep the account).
- **Reset a student's progress** (clear `progress` for the class's assigned modules; define and
  document the scope).
- **Rotate the join code** (`classroom.rotate_join_code`; show the new code; no student displaced).
- **Archive a section** (drops off active lists; roster preserved for records).
- **Multiple sections side-by-side:** a comparison view across the educator's classes (completion
  rate per module per section).
- **Educator-initiated full deletion** (Privacy): removing a student *and* deleting their account
  + attempt log — guard hard, confirm twice, and keep it visually distinct from "remove."

**Acceptance:** removing a student updates both the roster and the student's `classes`; reset
clears the intended progress; rotate yields a new working code with existing students still
enrolled; archived sections leave the active list; the comparison view aligns sections; every
destructive action is confirm-gated.

**Don't:** delete a pickle on plain "remove from class"; let rotate change `class_id` or drop the
roster.

---

## Phase 9 — Shareable data states (feature 8)  · P1

**Complexity: Low — Sonnet 5.** One apply-state route + a copy-link affordance; the token
machinery already exists.

**Read first:** `cache.py` (`history_text_to_item`, `history_item_to_text`), `lessons.py`
(`_validate_state` — token checks), `account.py` (`history_add`, `history_revert`), `app.py`
(filter apply path), `EDUCATOR_PORTAL.md` (feature 8), `CLAUDE.md` (history/cache substrate).

**Build:**
- A route (e.g. `/share/<chain>` or `?state=`) that, for a **logged-in** user, validates and
  applies an encoded filter-token chain to their **own** history — resetting to base, then
  applying the chain, so the shared state is reproduced exactly — and redirects into the view.
  Validate every token (reuse the `_validate_state`/`history_text_to_item` checks); reject bad or
  oversized chains gracefully with a toast.
- A **copy-link** affordance (e.g. on the sidebar data-state module) that builds the chain from
  the current `user['history']`.

**Acceptance:** opening a share link as a logged-in student reproduces the sharer's exact view
(case count matches); bad/oversized chains are rejected safely; the copy-link yields a working
link; a logged-out visitor is sent to login first.

**Don't:** skip token validation (untrusted URL input); touch lesson sandbox state. **Note:**
this feature *intentionally* mutates the student's own history (unlike lessons) — call it out.

---

## Phase 10 — Educator inspection: answer context + computed answer key (features 9 & 10)  · P1

**Complexity: Medium — Sonnet 5.** Reads the attempt log and live-computes answers across two
related educator views.

**Read first:** `analytics.py` (Phase 4 log), `app.py` (`compute_expected`, `resolve_lesson_state`,
`describe_token`, `build_lesson_data`), `lessons.py`, `EDUCATOR_PORTAL.md` (features 9, 10;
principle 2), `CLAUDE.md` (Learning Modules grading).

**Build:**
- **Answer-context inspection (feature 9):** from a student's incorrect attempt in the dashboard,
  show the student's **data state at answer time** (the logged tokens → `describe_token` phrases),
  so the teacher can tell "filtered the wrong year" from "can't read a median."
- **Preview-as-student + computed answer key (feature 10):** an educator view of any module
  showing each `question` step's **currently computed** answer (via `compute_expected` on the
  step's active state), generated **on demand** and never cached long-term (answers track the
  data). Optionally a read-only "preview as student" walk-through.
- Educator/owner-guarded.

**Acceptance:** an incorrect attempt reveals the student's state at that moment; the answer-key
view shows correct live-computed values and regenerates when the data changes; educator-only.

**Don't:** cache the answer key persistently; expose another class's students; compute from a
client-sent value.

---

## Phase 11 — Retake & feedback policy (feature 11)  · P1

**Complexity: Medium — Sonnet 5.** Per-class config threaded into the student question flow and
the grading render.

**Read first:** `classroom.py` (class settings), `app.py` (`grade_and_store`, `build_question`,
`lesson_step`, `next_locked`), `templates/lesson_step.html`, `EDUCATOR_PORTAL.md` (feature 11),
`CLAUDE.md` (grading).

**Build:**
- Per-class toggles (stored on the class): attempts allowed per question; whether the correct
  answer is revealed after a miss; whether the numeric tolerance is displayed.
- Thread them into the lesson-step flow **for enrolled students**: enforce the attempt cap (lock
  the question after N tries), the reveal-after-miss behavior, and tolerance display. Public/
  `unmanaged` users keep current defaults. Grading stays server-side; the policy changes only
  what's shown and how many tries are allowed.

**Acceptance:** "1 attempt, reveal after miss" locks a student's question after one try and shows
the answer; "unlimited, no reveal" preserves current behavior; the policy is per-class; public
users unaffected.

**Don't:** let the client override the policy; change how correctness is computed.

---

## Phase 12 — Per-module teaching notes (feature 12)  · P1

**Complexity: Low — Sonnet 5.** A lesson-JSON field + validator + an educator-only pane. (Required
before the future disparity module ships.)

**Read first:** `lessons.py` (`validate`, `_validate_step`), `lessons/README.md`, `app.py`
(`lesson_overview`, `lesson_step`, `require_educator`), `templates/lesson.html`/`lesson_step.html`,
`EDUCATOR_PORTAL.md` (feature 12).

**Build:**
- Add an optional `educator_notes` field to the module schema (module-level and/or per step):
  discussion prompts, misconceptions, framing. Extend `lessons.validate` (optional string/list)
  and update `lessons/README.md`.
- Render an **educator-only** notes pane on the lesson overview/step (gated by `is_educator`),
  never shown to students.

**Acceptance:** a module with `educator_notes` shows them to an educator and never to a student;
validation accepts modules without the field (back-compat); README updated.

**Don't:** show notes to students; make the field required.

---

## Phase 13 — QA, docs (README + ROADMAP), and cleanup  · final

**Complexity: Medium — Sonnet 5.** Broad manual QA across roles/themes/breakpoints plus accurate
doc rewrites.

**Goal:** verify the whole feature end-to-end and bring every document in line with what shipped.

**Read first:** a skim of everything built this initiative; `README.md`, `ROADMAP.md`,
`CLAUDE.md`, `STYLEGUIDE.md`, `EDUCATOR_PORTAL.md`.

**Build:**
- **Full click-through QA** in both themes at 375 / 768 / 1280px, covering the whole arc:
  educator creates a class → shares the join code → student signs up and joins → student does
  assigned lessons → educator reads the dashboard/triage, inspects an attempt, exports the
  gradebook. No console errors, no external requests (assets vendored), keyboard/focus/contrast
  per the `STYLEGUIDE.md` a11y checklist.
- **Update `README.md`:** Features (educator portal, real class join codes, gradebook export,
  assignment/pacing); Project status (password verification + `secret_key` now done — fix the
  auth caveat; note the `checkpoint` line is already stale/functional; export now exists);
  reword "Accounts & classes" to the new model.
- **Update `ROADMAP.md`:** mark the educator-portal / class-code / auth-hardening items done or
  in-progress and re-frame the remaining threads.
- Fold any new component/token specs into `STYLEGUIDE.md`; update `CLAUDE.md` (module map:
  `classroom.py`, `analytics.py`, new templates, `classes/`; routes; an "Educator portal
  (implemented)" section; strike the resolved Known issues); update `EDUCATOR_PORTAL.md` (mark
  resolved decisions and open questions).

**Acceptance:** the whole flow works across roles/themes/breakpoints with no console/network
errors; `README.md` and `ROADMAP.md` accurately describe the shipped feature; the other docs
match the code.

**Don't:** leave any doc describing the pre-portal state; overstate the security posture — note
residual limitations honestly.

---

## Appendix A — Class object schema (`classes/<class_id>.json`)

```jsonc
{
  "class_id": "intro-crim-fall26-7f3k",   // immutable; slug(name) + random suffix; == filename stem
  "name": "Intro to Criminology — Fall 2026",
  "owner": "edu-smith/jsmith",            // educator userid (form_userid)
  "join_code": "K7F2QP",                  // rotatable; unambiguous alphabet (no 0/O/1/I/L)
  "email_policy": { "required": false, "domains": [] },   // feature 3
  "assignments": {                         // feature 4; module_id -> state
    "intro-explorer-basics":   { "state": "required",  "open": null,          "due": "2026-09-15" },
    "intro-descriptive-stats": { "state": "scheduled", "open": "2026-09-16",  "due": "2026-09-30" }
  },
  "policy": { "attempts": null, "reveal_after_miss": false, "show_tolerance": false }, // feature 11
  "roster": ["intro-crim-fall26-7f3k/astudent"],  // student userids
  "archived": false,
  "created": "2026-07-06T00:00:00Z"
}
```

`state` ∈ `required | optional | hidden | scheduled`. Read every field defensively — older class
files may predate `policy`/`assignments`.

## Appendix B — Attempt-log format (`user/<class_id>/<username>.attempts.jsonl`)

One JSON object per line, append-only (one line per graded attempt):

```json
{"ts":"2026-09-10T14:22:01Z","module":"intro-descriptive-stats","step":3,"type":"numeric","correct":true,"submitted":41.7,"state":["f.moc1.eq.A"]}
```

`state` is the resolved lesson-state token list at answer time (from `resolve_lesson_state`) —
this is what powers answer-context inspection (feature 9). `progress['answers']` still holds only
the latest answer per step; this log holds the full attempt history.

## Appendix C — Decisions & open questions

Resolved defaults carried from `EDUCATOR_PORTAL.md` ("Class & identity model"): one class per
student account (many per educator); the signup code box is overloaded by lookup; enrolled
students see only their class's non-hidden assigned modules; classes stored as JSON. Still open
(decide in the phase that hits them): attempt-log granularity (Phase 4 recommends per-student),
and the gradebook definition of "complete" (Phase 7). Both are noted at the point of use.
