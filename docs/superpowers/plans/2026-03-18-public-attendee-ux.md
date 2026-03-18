I'm using the writing-plans skill to create the implementation plan.

# Public Attendee UX Plan

## Goal

Redesign the public read-only app so it feels much closer to the editable app's core navigation and schedule views, while staying attendee-friendly and strictly read-only.

The public app should:

- default to `Structure`
- keep `Programme` and `Papers` as the other main tabs
- use read-only detail panels instead of admin inspectors
- show paper abstracts only when a paper is clicked
- behave like a conference navigation tool, not a generic filtered data browser

## Constraints

- No edit affordances, no inspector wording, no admin metrics, no inactive sessions.
- Keep the public app compatible with the generated `public_bundle/`.
- Reuse structure/programme mental models from the private app where useful, but avoid importing large admin-only UI modules directly.
- Preserve current public security boundaries and bundle generation.

## File Structure

- `wic_app/public_app.py`
  - Main implementation target for the redesigned attendee UX.
  - Add attendee-oriented state, navigation, filters, and detail panels.
- `wic_app/public_data.py`
  - Extend only if the public payload needs extra derived fields for the new views.
- `wic_app/tests/test_public_app_config.py`
  - Keep public gating coverage intact.
- `wic_app/tests/test_public_app_layout.py`
  - New tests for the new tab names, read-only detail panels, and public-attendee wording.
- `wic_app/tests/test_public_app_startup.py`
  - Keep smoke coverage for public app startup.
- `wic_app/README.md`
  - Update public app description if needed.

## Chunk 1: Lock The New Public UX Contract With Tests

### Tasks

1. Add `wic_app/tests/test_public_app_layout.py`.
   - Assert the public app uses `Structure`, `Programme`, and `Papers` tabs.
   - Assert the old `Schedule` tab is gone.
   - Assert the app exposes read-only session and paper detail panels.
   - Assert the app does not use admin wording like `Inspector` in the public UI.

2. Extend or adjust tests only where the old public UX assumptions are now stale.

### Verification

```bash
python3 -m unittest wic_app.tests.test_public_app_layout
```

## Chunk 2: Implement Structure-First Attendee UX

### Tasks

1. Redesign `Structure` as the default public landing tab.
   - Day selector and attendee-friendly filters.
   - Room/block matrix similar to the private app.
   - Click a session to open a read-only detail drawer on desktop.
   - Use a dialog/sheet equivalent on smaller screens if needed.

2. Redesign `Programme`.
   - Keep the schedule-style browsing feel.
   - Use the same read-only session detail behavior.

3. Redesign `Papers`.
   - Convert it into a searchable directory with one selected paper in a detail panel.
   - Abstract appears only in the selected paper detail view.

4. Replace admin language.
   - `Session details` and `Paper details`, not `inspector`.
   - Remove edit/planning/admin messaging from the public app.

### Verification

```bash
python3 -m unittest \
  wic_app.tests.test_public_app_layout \
  wic_app.tests.test_public_app_config \
  wic_app.tests.test_public_app_startup
```

## Chunk 3: Regression Coverage And Bundle Compatibility

### Tasks

1. Ensure the bundle and preview features still work with the redesigned public app.
2. Update docs only if public navigation descriptions are now materially different.

### Verification

```bash
python3 -m unittest \
  wic_app.tests.test_public_bundle \
  wic_app.tests.test_public_preview \
  wic_app.tests.test_public_app_startup
```

## Final Verification

```bash
python3 -m unittest \
  wic_app.tests.test_public_app_layout \
  wic_app.tests.test_public_app_config \
  wic_app.tests.test_public_app_startup \
  wic_app.tests.test_public_bundle \
  wic_app.tests.test_public_preview \
  wic_app.tests.test_public_data \
  wic_app.tests.test_public_release_cli \
  wic_app.tests.test_repo_rename_hygiene \
  wic_app.tests.test_engine \
  wic_app.tests.test_auth_gate_config \
  wic_app.tests.test_app_startup_smoke
```
