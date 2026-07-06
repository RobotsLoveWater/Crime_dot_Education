# Educator Portal — Design Guidelines

Guidelines for building the **educator portal** for MAST / Minnesota Sentencing Explorer.
This document is the source of truth for scope, priorities, and design constraints. When
implementation details here conflict with the codebase, trust the codebase and update this file.

## Context (read first)

- Educators already exist in the model: a *classcode* beginning `edu-` grants educator rights.
  The portal is the UI that makes those rights useful.
- Architecture constraints that shape everything below:
  - **File-based, no database.** Accounts are pickles under `user/`; keep the portal's data in
    the same model (per-class or per-student files), not a new datastore.
  - **The data state is the substrate.** Every dataset view serializes to an ordered list of
    filter tokens (e.g. `f.moc1.eq.A`). Progress, answer-checking, and lesson states all reuse
    this. Portal features should exploit it, not work around it.
  - Lessons are JSON files in `lessons/` with `read` / `explore` / `question` / `checkpoint`
    steps; `question` answers are **computed live** against the data, never stored.
- Audience: high school teachers and college instructors. Assume the portal is opened
  **between classes, in under four minutes**. Exceptions surface first; tables come second.

## Class & identity model (resolved)

The resolved data model behind the portal. It supersedes the loose use of "classcode" in the
feature list below, which conflates three now-distinct concepts:

- **Educator account** — an account whose classcode begins `edu-`; grants authoring/portal
  rights (`is_educator = True`, set at signup). Unchanged from today. An educator **owns many
  classes** (sections).
- **Class** — a first-class object an educator creates in the portal (not a bare `user/`
  directory). Fields:
  - `class_id` — immutable, URL/filename-safe (a slug of the name + short random suffix). The
    stable key for storage, rosters, and assignments; **never changes**.
  - `name` — display name ("Intro to Criminology — Fall 2026").
  - `owner` — the educator's `userid`.
  - `join_code` — short, human-typeable, **rotatable** code students enter to enroll. Resolved
    to a `class_id` by lookup, so rotating it (feature 7's "regenerate a classcode") **displaces
    no student** — storage keys off `class_id`, not the code.
  - `roster` — enrolled student `userid`s.
  - `assignments` — per-module state (required / optional / hidden / scheduled + dates); feature 4.
  - `email_policy` — optional allowed-domain rule enforced at join time; feature 3.
  - `created`, `archived`.
- **Student account** — joins with a class **join code**, never an `edu-` code → member,
  `is_educator = False`. A student account **belongs to one class**.

**Where it lives.** A new pure-stdlib module `classroom.py` (mirroring `account.py` /
`lessons.py`) over a **git-ignored `classes/` directory**, one `classes/<class_id>.json` per
class. JSON, like `lessons/` (classes hold no non-serializable data); private, like `user/`
(rosters tie to real students). This resolves open question 2.

**The signup code box is resolved by lookup** — one field, but this is where class codes finally
get *validated*:
- blank → public / `unmanaged` (unchanged);
- `edu-*` → educator account;
- matches a live `join_code` → enroll as a student in that class (namespaced under
  `user/<class_id>/`, added to the roster; enforce `email_policy` if set);
- anything else → an error ("no class with that code"), instead of silently creating a stray
  directory as today.

A logged-in student may also join from a "Join a class" action (same lookup).

**Login resolves the same code box.** `/login` runs the typed code through the identical
resolver so a student who enrolled with a join code signs in with that same code (it maps back
to their immutable `class_id` namespace). Legacy/bare-directory and `edu-`/blank accounts are
untouched — a code matching no live class falls through to being treated as the typed classcode,
exactly as before. (Because join codes are rotatable, a returning student uses the class's
*current* code; a rotated code invalidates the old one for fresh logins, not the enrollment.)

**Authorization.** A `require_class_owner(class_id)` guard beside `require_educator()` — an
educator may only view or edit classes they own (load-bearing once auth is real; see Privacy).

**Back-compat.** Read defensively (`user.get(...)`, as `progress` already does): existing
accounts and bare `user/<code>/` directories predate this model and stay valid as legacy/public.
No forced migration — classes are adopted lazily as educators create them.

**Resolved sub-decisions** (proposed defaults; revisit if needed):
- one class per student account; many classes per educator;
- the signup code field is overloaded by lookup (no separate join step);
- enrolled students see **only** their class's non-hidden assigned modules; public/`unmanaged`
  users keep seeing every module (backwards compatible);
- classes are stored as JSON under `classes/`.

## Design principles

1. **Landing view answers "who needs my attention today?" in one glance.** Triage before data.
2. **Diagnose, not just monitor.** Progress percentages say *who* is behind; the portal should
   also help answer *why* (item-level misses, the student's filter state at time of answer).
3. **The teacher is the interpretive guardrail of last resort.** Especially for sensitive
   material (the future disparity module), the portal must equip educators with framing and
   teaching notes — not just completion stats.
4. **Minimal PII by default.** Display names in dashboards, not emails. Assume minors.
5. **Every feature should degrade gracefully for a teacher with one section of 25 students and
   scale to an instructor with three sections of 80.**

## Features

### P0 — must ship with the portal

**1. Student progress dashboard** *(user requirement #1)*
- Per-student: modules started/completed, per-module question scores, last-active timestamp.
- Per-class rollup: completion rate per module, median score per module.
- Sort/filter by module, by completion, by last activity.

**2. Class activity overview** *(user requirement #2)*
- Recent-activity feed or summary (who worked, on what, when) at class granularity.
- A **"stuck" triage list at the top of the landing page**: students with repeated failed
  attempts on one question, or long inactivity mid-module. This is the exception-first view
  from principle 1.

**3. Email-domain policy** *(user requirement #3)*
- Per-class toggle: require usernames to be email addresses from an allowed domain
  (e.g. `@district.k12.mn.us`), or allow any username.
- Store the policy on the class, enforce at account creation for that classcode.
- Note: this is a **roster-hygiene and identity policy**, and it interacts with privacy
  (see Privacy section). Default to *not required*.

**4. Module assignment control** *(user requirement #4, extended)*
- Per-class, per-module state: **required / optional / hidden / scheduled**.
- *Scheduled* = required with an open date and/or due date. Pacing is how classroom teachers
  actually plan; a plain required/optional binary forces workarounds.
- Student UI reflects the state (required badges, due dates, hidden modules absent).

**5. Item-level analytics**
- Per-question miss/attempt rates across the class, per module.
- Cheap: every graded attempt is already computed server-side — log attempts (question id,
  correct/incorrect, timestamp, and the **filter-state token string at time of answer**).
- Dual purpose: teachers get "what do I reteach Tuesday"; the thesis gets item difficulty
  data for the evaluation chapter. Design the log format with both consumers in mind.

**6. Gradebook CSV export**
- One CSV per class: student, per-module completion, per-module score, timestamps.
- Must import cleanly into Canvas / Google Classroom / PowerSchool (simple flat columns,
  no merged headers). Reuse/finish the stubbed `/download` machinery.
- Highest-adoption feature on this list; do not let it slip to P1.

### P1 — fast follows

**7. Roster management**
- Remove a student from a class; reset a student's progress; **rotate the class join code**
  (storage keys off the immutable `class_id`, so no student is displaced); archive a section
  at semester end.
- **Multiple sections per educator** (each section is its own class object with its own join
  code) with a side-by-side comparison view.

**8. Shareable data states**
- Educator can copy a link encoding a filter-token chain; opening it drops any logged-in
  student into that exact view. Projector-led discussion, custom exercises.
- Cheapest killer feature given the architecture — the state string already exists; this is
  a route that applies it.

**9. Inspect a student's answer context**
- From an incorrect attempt, show the student's filter history / data state at the moment of
  the answer ("they filtered the wrong year" vs. "they can't read a median").
- Depends on logging the state token with each attempt (see feature 5).

**10. Preview-as-student + computed answer key**
- Educator view of any module showing each `question` step's **currently computed answer**.
- Because answers are computed live, the key must be generated on demand, never cached
  long-term: if the data changes, the key changes.

**11. Retake & feedback policy**
- Per-class toggles: attempts allowed per question; whether the correct answer is revealed
  after a miss; whether numeric tolerance is displayed.

**12. Per-module teaching notes**
- An educator-only pane per module: discussion prompts, common misconceptions, suggested
  framing. Author these as a field in the lesson JSON (e.g. `educator_notes` on the module
  and/or per step) so notes travel with the lesson.
- **Required before the disparity module ships.** That module's descriptive-vs-causal
  guardrails depend on the teacher having the framing in hand.

### P2 — later / grant scope

**13. Fork-and-edit modules**
- Duplicate an existing lesson JSON into the educator's class scope and allow editing of
  narration (`read`/`explore` bodies) without touching graded logic.
- Deliberately lighter than a full authoring UI — forking captures most of the value.

**14. Standards alignment tags**
- Tag modules with AP Statistics topics, Common Core math practices, C3 social studies
  standards. Surface tags in the educator's module list. High school adoption often turns
  on whether a teacher can justify the class period.

**15. Full authoring UI**
- Explicitly deferred. JSON authoring plus fork-and-edit covers current needs.

## Privacy & compliance (blocking for real deployment)

- **Real authentication is a prerequisite, not a nice-to-have**, once identifiable student
  progress is stored. "Full hardening" here is concretely:
  - **Verify passwords** — wire the existing `util.check_password` into `/login` (today login
    only checks that the username exists; the helper is never called). *Gotcha:* `/new` hashes
    `html.escape(password)`, so `/login` must escape identically before comparing, or every
    existing hash mismatches — pick escape-identically or a one-time migration, but don't
    silently drop the escaping.
  - **Move `secret_key` out of source** into environment/instance config (a hardcoded dev key
    sits in this public repo today).
  - The two "latent account bugs" the roadmap cites are **already fixed** (`/new` sets all three
    session keys; `account.create` returns `retrieve(userid)`) — scope is just the two above.
- Minimal-PII defaults: display names in all dashboards; emails visible only in roster
  management, only to the class's educator.
- Educator-initiated deletion: remove a student's account and progress records completely.
- Write and display a short data-retention statement (what is stored, for how long, who can
  see it). A grant reviewer will look for a FERPA sentence; the portal is where it lives.
- If email-domain policy (feature 3) is enabled, that email is PII — treat accordingly.

## Implementation phasing

Build order, following the project's phased-plan convention (`UI_OVERHAUL_PROMPTS.md`,
`LEARNING_MODULES_PROMPTS.md`). Auth comes first because the portal exposes cross-account data.
Phases 0–4 deliver the P0 set; Phase 5 is the P1 fast-follows; P2 stays grant scope.

- **Phase 0 — Auth & config hardening.** Password verification (with the escape caveat) and
  `secret_key` → config. Prerequisite for exposing student data. Update CLAUDE.md "Known issues."
- **Phase 1 — `classroom.py` + `classes/` store.** Pure module: create / get / list-by-owner /
  find-by-join-code / enroll / rotate-code / assign / roster-progress (plus forward-compatible
  hooks for the P1 remove / reset / archive ops). Git-ignore `classes/`; verify with a scratch
  script; no routes yet.
- **Phase 2 — Class-code wiring.** Overloaded signup lookup + optional logged-in join; student
  namespacing under `class_id`; enrollment recorded on the roster and the user pickle;
  email-domain policy (feature 3) enforced here, since it is a join-time check.
- **Phase 3 — Portal core (P0 triage + dashboard).** Restructure `/admin` into the portal:
  the "who needs my attention" landing with the stuck-triage list (features 1–2), per-student
  and per-class progress, class create/list, join-code display + rotate.
- **Phase 4 — Assignment, analytics, export (rest of P0).** Per-module assignment states incl.
  scheduled/due dates + student-facing badges (feature 4); attempt logging with the filter-state
  token hooked into `grade_and_store` (feature 5, format per open question 1); gradebook CSV
  export reusing the `/download` machinery (feature 6).
- **Phase 5 — P1 fast-follows**, scheduled separately: roster management, shareable data-state
  links, answer-context inspection, preview-as-student answer key, retake/feedback policy,
  per-module teaching notes.
- **Phase 6 — Responsive / a11y / dark QA + docs** (STYLEGUIDE additions, CLAUDE.md, ROADMAP,
  and a phased `EDUCATOR_PORTAL_PROMPTS.md`).

## Non-goals

- No real-time collaboration or chat.
- No LMS API integrations (LTI) yet — CSV export is the integration story for now.
- No new database. Stay file-based per project principles.
- No student-facing changes beyond: assignment states/badges/due dates, shared-state links,
  and whatever the retake/feedback policy requires.

## Open questions (resolve before or during implementation)

1. **Resolved** — attempt logging is **one append-only JSONL log per student**,
   `user/<class_id>/<username>.attempts.jsonl` (mirrors the account pickle's own path; avoids
   class-wide write contention; the class folder is the semester archive). A new pure-stdlib
   `analytics.py` provides `log_attempt`/`read_attempts`/`question_stats`; `grade_and_store`
   appends `{ts, module, step, type, correct, submitted, state}` (state = the resolved lesson
   state tokens at answer time) for every graded (non-`free`) attempt. See
   `EDUCATOR_PORTAL_PROMPTS.md` Appendix B.
2. **Resolved** — class-level config lives in a **git-ignored `classes/` directory** (mirroring
   `user/`), one `classes/<class_id>.json` per class, managed by a new pure-stdlib `classroom.py`.
   See "Class & identity model."
3. **Checkpoint vs. due dates** — `expect_state` checkpoint verification is now **already wired**
   (CLAUDE.md, learning-modules Phase 5), so the original worry (inert checkpoints under due
   dates) is largely moot; still decide whether "reached the final checkpoint" counts toward
   due-date completion (ties into #4). *Mostly resolved.*
4. **Definition of "complete"** for the gradebook — all questions attempted, all correct, or
   final checkpoint reached? Pick a default and expose it as a per-class setting. *Open.*
