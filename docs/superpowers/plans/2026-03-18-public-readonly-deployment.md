I'm using the writing-plans skill to create the implementation plan.

# Public Read-Only Deployment Plan

## Goal

Keep the existing Streamlit app as a local-only editor, and add a separate public Streamlit app that serves a sanitized, read-only conference programme plus a downloadable sanitized Excel workbook. Publication must be a manual local release step, and the public app must remain hidden until `PUBLIC_ENABLED` is explicitly turned on.

## Constraints

- Do not expose `source_data/` content, live `wic_app/state/` files, reviewer scores, email addresses, paper PDF links, or organizer-only notes in the public deployment.
- Public deployment must fail closed: if the public dataset is missing or the public flag is off, the app shows only a holding page.
- Local editing continues to use the current app and current state files.
- Public release artifacts are generated locally and committed intentionally.
- Use TDD for new behavior and keep tests focused on security boundaries and public-data correctness.

## File Structure

- `wic_app/app.py`
  - Remains the local editor entrypoint.
  - Gains no new public-read behavior beyond possible shared helpers pulled into new modules.
- `wic_app/public_app.py`
  - New read-only Streamlit entrypoint for deployment.
  - Enforces `PUBLIC_ENABLED`.
  - Loads only sanitized public artifacts.
- `wic_app/public_data.py`
  - New module for the public snapshot schema, sanitization helpers, serialization, and loading.
  - Central place to define which fields are allowed into public outputs.
- `wic_app/exporters/publish.py`
  - Extend publish/export pipeline to generate a sanitized public JSON snapshot alongside the sanitized Excel.
  - Reuse existing state traversal where possible.
- `wic_app/generate_wic_programme_draft.py`
  - Extend CLI so the manual release step can generate public artifacts in one command.
- `wic_app/tests/test_public_data.py`
  - New tests for sanitization, filtering of archived/inactive content, and JSON payload shape.
- `wic_app/tests/test_public_app_config.py`
  - New tests for `PUBLIC_ENABLED` gate and fail-closed behavior.
- `wic_app/tests/test_public_app_startup.py`
  - New smoke test for the public Streamlit entrypoint.
- `.gitignore`
  - Update to keep local/private working data out of a publish-oriented GitHub workflow.
- `wic_app/README.md`
  - Document local editing flow, manual publish flow, public deploy entrypoint, and security boundaries.
- `public_data/` or `exports/public/`
  - Checked-in deployable artifacts for the public app.
  - Final path should clearly separate publishable data from local working exports.

## Chunk 1: Public Data Contract And Export Pipeline

### Scope

Define the canonical public snapshot format and generate it from `ProgrammeState` without leaking private fields.

### Tasks

1. Add `wic_app/public_data.py`.
   - Define normalized public record builders for:
     - conference metadata
     - active sessions
     - public papers
     - filter indexes or derived lists needed by the read-only app
   - Explicitly whitelist public fields:
     - session code/title
     - day/block/time/room
     - theme/subtheme
     - title
     - author names
     - abstract
     - slot/ordering metadata needed for rendering
   - Explicitly exclude:
     - `email`
     - `reviewer_score`
     - `link_to_pdf`
     - archived papers
     - inactive sessions and papers assigned only to inactive sessions
     - organizer-only note fields unless a field is intentionally repurposed as public copy

2. Extend `wic_app/exporters/publish.py`.
   - Add a function to build and write the public JSON snapshot.
   - Ensure the sanitized Excel export is aligned with the same public dataset rather than separately re-deriving different logic.
   - Keep the JSON writer deterministic so diffs are reviewable.

3. Extend `wic_app/generate_wic_programme_draft.py`.
   - Add a publish/release path that generates:
     - sanitized public JSON
     - sanitized public Excel
     - optional PDF if still useful locally
   - Print concrete output paths so release steps are obvious.

### Tests

- Add `wic_app/tests/test_public_data.py`.
  - Assert archived papers are excluded.
  - Assert inactive sessions are excluded.
  - Assert no public record contains email, reviewer score, or PDF link fields.
  - Assert expected public records preserve authors, abstracts, and schedule metadata.
- Extend existing export smoke coverage if needed so public JSON is generated successfully.

### Verification

```bash
python3 -m unittest wic_app.tests.test_public_data wic_app.tests.test_engine
python3 wic_app/generate_wic_programme_draft.py --publish
```

Expected result:
- tests pass
- CLI prints paths for sanitized public artifacts
- generated JSON contains only public fields

## Chunk 2: Read-Only Public Streamlit App

### Scope

Create a separate Streamlit app for browsing the sanitized programme and downloading the sanitized Excel workbook.

### Tasks

1. Add `wic_app/public_app.py`.
   - New `st.set_page_config(...)`.
   - Enforce `PUBLIC_ENABLED` using environment-first config resolution.
   - If disabled, show a simple holding page and stop.
   - If enabled but public artifacts are missing, show a generic unavailable message and stop.

2. Implement public data loading through `wic_app/public_data.py`.
   - Do not import or load `build_programme_state()` for the public app path.
   - Avoid any dependency on `source_data/` or `wic_app/state/`.

3. Build the read-only UX.
   - Programme browse view by day/block/session.
   - Search across paper title, author, session title, theme, subtheme.
   - Filters for day, theme, subtheme, room.
   - Expandable or dialog-style paper details showing title, authors, abstract, session placement.
   - Download button for sanitized Excel.
   - No inspector, no edit controls, no archive/inactive tabs, no paper-link buttons.

4. Reuse presentation helpers selectively.
   - Extract or reuse safe layout helpers from current UI modules only where they do not drag in edit behavior.
   - Prefer smaller read-only helpers over trying to conditionally disable large editable views.

### Tests

- Add `wic_app/tests/test_public_app_config.py`.
  - Assert public app checks `PUBLIC_ENABLED`.
  - Assert it does not fall back to loading private state when disabled or missing public data.
- Add `wic_app/tests/test_public_app_startup.py`.
  - Streamlit smoke test mirroring the current startup smoke test for `public_app.py`.
- Add focused text-based tests if needed to guard against edit affordances appearing in the public app.

### Verification

```bash
python3 -m unittest wic_app.tests.test_public_app_config wic_app.tests.test_public_app_startup
python3 -m streamlit run wic_app/public_app.py --server.headless=true --browser.gatherUsageStats=false
```

Expected result:
- tests pass
- public app starts without traceback
- disabled mode renders holding page only

## Chunk 3: Repo Hardening, Release Flow, And Documentation

### Scope

Make the repository safe for a GitHub + public Streamlit deployment workflow and document the manual release process.

### Tasks

1. Update `.gitignore`.
   - Ignore local-only/private working data as appropriate for the new workflow.
   - Keep deployable public artifacts in a clearly intentional location that remains tracked.
   - Ignore local secrets and transient export/debug files.

2. Review tracked private data.
   - Identify whether `source_data/` and live `wic_app/state/` should be untracked, relocated, or replaced with safe templates/example files.
   - If existing tracked files are sensitive, plan a follow-up history cleanup outside this implementation if needed.

3. Update `wic_app/README.md`.
   - Document:
     - local editing workflow
     - Dropbox single-writer guidance
     - manual publish command
     - public app entrypoint
     - `PUBLIC_ENABLED` deployment control
     - which files/data must never be deployed publicly

4. Ensure the public app deploy target is explicit.
   - README should specify the deployed entrypoint path for Streamlit Community Cloud.
   - Document that the public app reads only generated public artifacts committed to the repo.

### Tests

- Add or update lightweight tests that assert the new public app entrypoint is referenced in docs/config if this is already part of the test style.
- Run existing auth/config smoke tests to ensure local app gating behavior is unchanged.

### Verification

```bash
python3 -m unittest \
  wic_app.tests.test_auth_gate_config \
  wic_app.tests.test_public_data \
  wic_app.tests.test_public_app_config \
  wic_app.tests.test_public_app_startup \
  wic_app.tests.test_app_startup_smoke
git status --short
```

Expected result:
- tests pass
- public/private boundaries are covered by tests
- tracked changes are limited to intended app/docs/test files plus public artifacts

## Execution Notes

- Follow `@test-driven-development` before implementation changes.
- Use `@verification-before-completion` before claiming the deployment split is done.
- Request `@requesting-code-review` once implementation and verification pass.
- If execution work is split into independent streams, use `@subagent-driven-development`.

## Suggested Commit Sequence

1. `test: add coverage for public data contract and public app gate`
2. `feat: generate sanitized public publish snapshot`
3. `feat: add read-only public streamlit app`
4. `chore: harden repo for public deployment workflow`
5. `docs: document local edit and public release flow`
