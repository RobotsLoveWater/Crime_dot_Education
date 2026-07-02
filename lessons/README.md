# Learning Modules — lesson file schema

This directory holds **guided lessons** ("learning modules") for the Minnesota Sentencing
Explorer. Each `<module_id>.json` file is one self-contained module. Unlike `user/` and
`cache/`, this directory is **authored content and safe to commit**.

Lessons reuse the app's existing history→cache substrate: a lesson step can express a
**data state** as history tokens (the same `f.col.op.val` encoding
`cache.history_item_to_text` produces), so the exact filtered dataset is reconstructed by the
existing `_execute`/`get_data` path and numeric answers can be **graded live** rather than
hardcoded. See `CLAUDE.md` → "Planned: Learning Modules framework" and
`LEARNING_MODULES_PROMPTS.md` (Appendix A is the authoritative schema; this README expands it).

> **Status:** Phase 0 is data only. No loader or routes read these files yet — that is Phase 1+.

## File & id rules

- One module per file: `lessons/<id>.json`.
- `id` must be **filename- and URL-safe**: `[a-z0-9-]` only. It is simultaneously the JSON
  `id` field, the filename stem, and the `/lesson/<id>` URL segment. They must all match.

## Top-level fields

| Field | Type | Required | Meaning |
|-------|------|----------|---------|
| `id` | string | yes | Stable identifier; `[a-z0-9-]`, matches the filename stem. |
| `title` | string | yes | Human-readable module title. |
| `description` | string | yes | One-to-two sentence summary for the catalog. |
| `author` | string | yes | Owning **classcode** (`unmanaged` is the default classcode). |
| `objectives` | string[] | yes | Learning objectives shown on the overview page. |
| `steps` | Step[] | yes | Ordered list; step index (0-based) is the `/lesson/<id>/<step>` segment. |

## Steps

Every step has a `type` and a `title`. Most also have a `body` (Markdown/HTML — see
"Markdown" below). Steps are addressed by their **0-based index** in the `steps` array.

### `read`
Static content only. Fields: `title`, `body`.

### `explore`
Sets/deep-links a data state so the student can inspect a filtered dataset.

| Field | Type | Meaning |
|-------|------|---------|
| `body` | string | Explanatory text. |
| `state` | token[] | *(optional)* History tokens that define this step's dataset. Sets the module's **active state** (see "Active state" below). Omit to keep the current active state. |
| `focus` | object | *(optional)* Deep-link target into an existing analysis view. |

`focus.view` ∈ `info | table`:
- `info` → deep-links to `/info/<column>`. Requires `column`.
- `table` → deep-links to the cross-tab view. Requires `dependant`, `x_axis`, `y_axis`
  (semantic roles; the wiring phase maps them to the route respecting the app's documented
  x/y axis flip). Use `"#"` for `dependant` to mean count-only.

### `question`
Poses a question with a gradeable `answer`. Fields: `title`, `body`, `answer`.
Optionally `state` (defaults to the active state — see below). See "Answer types".

### `checkpoint`
Asserts the student's current active state matches an expected one. Fields: `title`, `body`,
`expect_state` (token[]).

## Answer types (`question.answer`)

| `type` | Fields | Grading |
|--------|--------|---------|
| `numeric` | `compute` `{ "stat": ..., "column": ... }`, `tolerance` (number) | Expected value is **computed live** from the step's active state; correct if `abs(submitted - expected) <= tolerance`. **Never** store the expected value in the file. |
| `choice` | `options` (string[]), `correct` (0-based index) | Correct if the submitted index equals `correct`. Graded server-side. |
| `free` | `model_answer` (string, optional) | Not auto-graded; the response is stored and marked "submitted". `model_answer` may be shown afterward. |

`compute.stat` ∈ `mean | median | std | count`, resolved live via `data.py`:

| `stat` | Source (on the active state) |
|--------|------------------------------|
| `mean` | `Data.get_column_info(column)['mean']` |
| `median` | `Data.get_column_info(column)['mdn']` |
| `std` | `Data.get_column_info(column)['std']` |
| `count` | `Data.get_column_info(column)['entries']` (row count; `column` may be any present column) |

`mean`/`median`/`std` are only defined for **numeric** (`float64`, >1 unique value) columns.

## Data state tokens (`state` / `expect_state`)

Tokens use the **exact** encoding from `cache.history_item_to_text` — do not invent a parallel
format:

| Action | Token form | Example | Decodes to (history `action`) |
|--------|-----------|---------|-------------------------------|
| single filter (`f`) | `f.<col>.<op>.<val>` | `f.moc1.eq.A` | `['f','moc1','eq','A']` |
| OR, same column (`o`) | `o.<col>.<op>.<v1>~<v2>~...` | `o.moc1.eq.A~H` | `['o','moc1','eq',['A','H']]` |

- `<op>` ∈ `eq, ne, gt, ge, lt, le`.
- `<col>` must be a real dataset column (present in `codebook.xml`).
- Keep `<val>` free of `.` and `~` (those are the token delimiters). Integer-valued numeric
  filters (e.g. `f.time.gt.14`) round-trip cleanly; the analysis layer coerces the value to
  `float` for `float64` columns, so `14` matches `14.0`.

### Active state (how state carries within a lesson)

A module tracks **one evolving active state**, stored at `progress[<module_id>]['state']`
(see Appendix B of `LEARNING_MODULES_PROMPTS.md`), **never merged into the student's real
`history`** (lessons are strictly sandboxed). An `explore` step with a `state` **sets** the
active state; later `question`/`checkpoint`/`explore` steps operate on it unless they carry
their own `state`. In `intro-descriptive-stats.json`, the `explore` step sets
`f.moc1.eq.A`, and the following numeric question grades the mean of `time` against that same
filtered set.

## Validity checklist (Phase 0 acceptance)

- Every file in `lessons/` parses with `json.load`.
- Every `state` / `expect_state` token round-trips through `cache.history_item_to_text`.
- Every column referenced (`state`/`expect_state` tokens, `focus.column`,
  `focus.dependant/x_axis/y_axis`, `answer.compute.column`) exists in `codebook.xml`.
