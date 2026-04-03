I'm using the writing-plans skill to create the implementation plan.

# Archive Checks And Reasons Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make archived-paper accounting unambiguous in the Checks tab, replace hard-coded archive reasons with user-managed archive labels, and add a simple bulk reason editor in the Archived tab.

**Architecture:** Keep archived papers backed by `paper_archive_overrides.csv` and continue excluding them from the active planning pool, but add explicit derived counts that show which metrics are subsets of which totals. Store archive-reason labels in the existing label catalog CSV as a third label type managed only from the Archived tab, then feed the resolved archive-reason list into every archive dropdown and the new bulk update flow.

**Tech Stack:** Python, Streamlit, pandas, CSV-backed state files, unittest

---

## Constraints

- Keep archive reason management in the **Archived** tab. Do not add archive-reason controls to the existing **Labels** tab.
- Do not change the public/export pipeline, paper classification logic, or restore-from-archive behavior.
- Preserve `paper_archive_overrides.csv` as the source of truth for archive state; only update reason values in-place.
- Keep the bulk edit scope limited to **archive reason** only. Do not add bulk note editing in this pass.
- Preserve the current default archive reasons as seed values so existing workflows continue to work on upgrade.

## File Structure

- `wic_app/engine/validation.py`
  - Add explicit disjoint planning-count keys for the Checks hierarchy.
- `wic_app/reclassification_engine.py`
  - Extend the label catalog helpers with an archive-reason label type.
  - Add archive summary keys that the Checks tab can render directly.
- `wic_app/app.py`
  - Replace hard-coded archive reason options with resolved options from state/catalog.
  - Add helper callbacks for single-paper and bulk archived-reason updates.
  - Rework the Checks tab layout/copy so subset relationships are obvious.
- `wic_app/ui/papers.py`
  - Accept dynamic archive reason options in the paper details editor.
- `wic_app/ui/archived.py`
  - Add archive-reason management UI, filtered bulk reason update UI, and helper functions for reason option resolution/filter targeting.
- `wic_app/tests/test_engine.py`
  - Cover explicit active/archived totals and archive classification summaries.
- `wic_app/tests/test_label_catalog_engine.py`
  - Cover the new archive-reason label type in catalog load/write/merge paths.
- `wic_app/tests/test_papers_view.py`
  - Cover dynamic archive reason option plumbing instead of hard-coded constants.
- `wic_app/tests/test_app_layout_config.py`
  - Guard the new Checks/Archived wiring at the app-entrypoint level.
- `wic_app/tests/test_archived_view.py`
  - New focused tests for archive reason option resolution, filtering, and bulk-target selection.

## Chunk 1: Make Checks Hierarchy Explicit

### Task 1: Add disjoint planning counts and archived summary keys

**Files:**
- Modify: `wic_app/engine/validation.py`
- Modify: `wic_app/reclassification_engine.py`
- Test: `wic_app/tests/test_engine.py`

- [ ] **Step 1: Write failing tests for explicit active vs archived totals**

```python
def test_validation_exposes_disjoint_active_and_archived_counts(self) -> None:
    state = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
    sid = state.papers[0].submission_id
    write_paper_archive_overrides(
        [
            {
                "SubmissionID": sid,
                "ArchiveReason": "Duplicate submission",
                "ArchiveNote": "",
                "ArchivedAt": "2026-04-03T10:00:00",
                "PreviousPlacementStatus": "scheduled",
                "PreviousSessionId": state.papers[0].session_id,
                "PreviousTalkIndex": "1",
                "PreviousOverflowOrder": "",
            }
        ],
        paths["archive"],
    )
    state_after = self._build_state(paths, submissions=SUBMISSIONS_FILE, programme=PROGRAMME_FILE)
    self.assertEqual(
        int(state_after.validations["total_papers"]),
        int(state_after.validations["active_papers"]) + int(state_after.validations["archived_papers"]),
    )
    self.assertEqual(
        int(state_after.validations["active_papers"]),
        int(state_after.validations["scheduled_active_papers"])
        + int(state_after.validations["overflow_active_papers"])
        + int(state_after.validations["scheduled_in_inactive_sessions"])
        + int(state_after.validations["overflow_in_inactive_sessions"])
        + int(state_after.validations["unassigned_active_papers"]),
    )
```

- [ ] **Step 2: Run the targeted engine test and confirm the new keys are missing**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest wic_app.tests.test_engine.EngineTests.test_validation_exposes_disjoint_active_and_archived_counts -v`

Expected: FAIL with missing validation keys such as `total_papers` or `scheduled_active_papers`

- [ ] **Step 3: Add the new validation keys with explicit names**

Implement these keys without removing existing ones yet:

```python
validations["active_papers"] = len(papers)
validations["scheduled_active_papers"] = len(scheduled_ids)
validations["overflow_active_papers"] = len(overflow_ids)
validations["scheduled_in_inactive_sessions"] = len(inactive_scheduled_ids)
validations["overflow_in_inactive_sessions"] = len(inactive_overflow_ids)
validations["unassigned_active_papers"] = len(unassigned_ids)
```

Then, after archived counts are known in `build_programme_state(...)`, add:

```python
state.validations["total_papers"] = len(active_papers) + len(archived_papers)
state.validations["archived_by_previous_status"] = {
    "scheduled": ...,
    "overflow": ...,
    "unassigned": ...,
}
```

- [ ] **Step 4: Re-run the engine tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest wic_app.tests.test_engine -v`

Expected: PASS for the new count semantics and the existing archive round-trip coverage

### Task 2: Rebuild the Checks tab around subset relationships

**Files:**
- Modify: `wic_app/app.py`
- Test: `wic_app/tests/test_app_layout_config.py`

- [ ] **Step 1: Add a failing text-based app-layout test for the new hierarchy labels**

Assert that `app.py` contains copy/keys for:

- `Total accepted papers`
- `Active papers`
- `Archived papers`
- `Active papers = Scheduled(active) + Overflow(active) + Scheduled(inactive) + Overflow(inactive) + Unassigned`

- [ ] **Step 2: Run the app-layout test**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest wic_app.tests.test_app_layout_config -v`

Expected: FAIL because the existing Checks tab still uses the old flat metric labels

- [ ] **Step 3: Update `_quality_panel(...)` to show the hierarchy explicitly**

Render the Checks tab in two grouped sections:

1. Inventory summary

```python
metric("Total accepted papers", v["total_papers"])
metric("Active papers", v["active_papers"])
metric("Archived papers", v["archived_papers"])
caption("Total accepted papers = Active papers + Archived papers")
```

2. Active paper breakdown

```python
metric("Scheduled in active sessions", v["scheduled_active_papers"])
metric("Overflow in active sessions", v["overflow_active_papers"])
metric("Scheduled in inactive sessions", v["scheduled_in_inactive_sessions"])
metric("Overflow in inactive sessions", v["overflow_in_inactive_sessions"])
metric("Unassigned", v["unassigned_active_papers"])
caption(
    "Active papers = Scheduled(active) + Overflow(active) + Scheduled(inactive) + Overflow(inactive) + Unassigned"
)
```

Keep the existing issue-details expander, but add the new summary keys there too.

- [ ] **Step 4: Add archived classification captions**

Below `Archived papers`, render compact captions for:

- `Archived by reason: ...`
- `Archived from: scheduled X, overflow Y, unassigned Z`

This satisfies the “better classification” requirement without introducing a new tab or export format.

- [ ] **Step 5: Re-run the app-layout test**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest wic_app.tests.test_app_layout_config -v`

Expected: PASS with the new hierarchy labels present in `app.py`

## Chunk 2: Replace Hard-Coded Archive Reasons With User-Managed Labels

### Task 3: Add archive-reason catalog support in the existing label catalog backend

**Files:**
- Modify: `wic_app/reclassification_engine.py`
- Test: `wic_app/tests/test_label_catalog_engine.py`

- [ ] **Step 1: Write failing catalog-engine tests for archive-reason labels**

Add coverage that:

- writes archive-reason labels
- reads them back sorted/deduplicated
- merges new archive-reason labels without disturbing primary/secondary labels

- [ ] **Step 2: Run the targeted label catalog test**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest wic_app.tests.test_label_catalog_engine -v`

Expected: FAIL because `archive_reason` is not yet recognized as a supported label type

- [ ] **Step 3: Extend the catalog constants and helpers**

Add a new label type constant and support it in load/write/merge logic:

```python
LABEL_TYPE_ARCHIVE_REASON = "archive_reason"
```

Normalize catalog dictionaries to include:

```python
{
    LABEL_TYPE_PRIMARY: ...,
    LABEL_TYPE_SECONDARY: ...,
    LABEL_TYPE_ARCHIVE_REASON: ...,
}
```

Seed defaults should remain:

```python
DEFAULT_ARCHIVE_REASON_OPTIONS = [
    "Duplicate submission",
    "Author cancelled attendance",
    "Other",
]
```

- [ ] **Step 4: Re-run the label catalog engine tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest wic_app.tests.test_label_catalog_engine -v`

Expected: PASS with archive-reason catalog coverage added

### Task 4: Resolve archive reason options dynamically everywhere a paper can be archived

**Files:**
- Modify: `wic_app/app.py`
- Modify: `wic_app/ui/papers.py`
- Modify: `wic_app/ui/archived.py`
- Test: `wic_app/tests/test_papers_view.py`
- Test: `wic_app/tests/test_archived_view.py`

- [ ] **Step 1: Add failing view tests for dynamic archive reason options**

Add tests for helper functions that:

- merge seeded defaults + archive-reason catalog + already-used archive reasons
- preserve historic reasons already attached to archived papers
- keep `"Other"` available even if the catalog is empty

- [ ] **Step 2: Run the targeted view tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest wic_app.tests.test_papers_view wic_app.tests.test_archived_view -v`

Expected: FAIL because the UI still depends on `ARCHIVE_REASON_OPTIONS`

- [ ] **Step 3: Add a single source of truth for archive reason options**

Implement a helper (in `app.py` or `ui/archived.py`) with behavior like:

```python
def resolve_archive_reason_options(
    catalog_reasons: Sequence[str],
    archive_overrides: Dict[str, Dict[str, str]],
) -> List[str]:
    return deduped(
        DEFAULT_ARCHIVE_REASON_OPTIONS
        + list(catalog_reasons)
        + [row["ArchiveReason"] for row in archive_overrides.values() if row["ArchiveReason"].strip()]
    )
```

Use this helper in:

- `_render_archive_controls(...)` in `wic_app/app.py`
- the paper details editor in `wic_app/ui/papers.py`
- the reason filter and bulk-update controls in `wic_app/ui/archived.py`

- [ ] **Step 4: Relax archive-reason normalization**

Replace the whitelist behavior:

```python
return reason if reason in ARCHIVE_REASON_OPTIONS else "Other"
```

with a simpler rule:

```python
return _normalize_text(value) or "Other"
```

That lets user-managed labels round-trip cleanly without reclassifying them as `"Other"`.

- [ ] **Step 5: Re-run the paper/archive view tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest wic_app.tests.test_papers_view wic_app.tests.test_archived_view -v`

Expected: PASS with dynamic reason options available in all archive entry points

## Chunk 3: Add Archived-Tab Reason Management And Bulk Editing

### Task 5: Add archive-reason management UI in the Archived tab

**Files:**
- Modify: `wic_app/ui/archived.py`
- Modify: `wic_app/app.py`
- Test: `wic_app/tests/test_app_layout_config.py`
- Test: `wic_app/tests/test_archived_view.py`

- [ ] **Step 1: Add failing tests for archived-tab reason management hooks**

Assert the Archived tab wiring includes:

- a reason-label creation area
- callbacks for loading/writing archive-reason labels
- the resolved archive reason options

- [ ] **Step 2: Run the archived/app wiring tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest wic_app.tests.test_archived_view wic_app.tests.test_app_layout_config -v`

Expected: FAIL because `render_archived_tab(...)` currently only supports filtering and restore

- [ ] **Step 3: Expand `render_archived_tab(...)` to manage archive reason labels**

Add a compact expander or bordered section above the archived list:

- `New archive reason labels`
- comma/semicolon/newline parsing
- `Add archive labels` submit button

Implementation notes:

- Reuse the existing `label_catalog.csv`
- Only read/write the `archive_reason` label type from this screen
- Do not expose primary/secondary label management here
- After save, rerun so the new labels appear immediately in dropdowns

- [ ] **Step 4: Pass the needed callbacks from `app.py`**

Extend the `render_archived_tab(...)` call site so it receives:

- resolved archive-reason options
- `load_label_catalog` / `write_label_catalog` or a narrower wrapper
- a bulk update callback for archived reasons

- [ ] **Step 5: Re-run the archived/app wiring tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest wic_app.tests.test_archived_view wic_app.tests.test_app_layout_config -v`

Expected: PASS with the Archived tab owning archive-reason management

### Task 6: Add simple filtered bulk edit for archived reasons

**Files:**
- Modify: `wic_app/app.py`
- Modify: `wic_app/ui/archived.py`
- Test: `wic_app/tests/test_archived_view.py`
- Test: `wic_app/tests/test_engine.py`

- [ ] **Step 1: Add failing tests for filtered bulk target selection and reason updates**

Cover:

- the filtered submission IDs returned for a given search + reason filter
- bulk updates rewriting only `ArchiveReason`
- unchanged `ArchiveNote`, `ArchivedAt`, and previous placement fields

- [ ] **Step 2: Run the targeted tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest wic_app.tests.test_archived_view wic_app.tests.test_engine -v`

Expected: FAIL because there is no bulk-reason update helper yet

- [ ] **Step 3: Add an app-level bulk update callback**

Implement a helper in `wic_app/app.py` similar to:

```python
def _bulk_update_archived_reason(submission_ids: List[str], archive_reason: str) -> bool:
    archive_rows = load_paper_archive_overrides(PAPER_ARCHIVE_OVERRIDES_FILE)
    changed = False
    for sid in submission_ids:
        row = archive_rows.get(sid)
        if row is None:
            continue
        normalized_reason = _normalized_archive_reason(archive_reason)
        if row.get("ArchiveReason", "").strip() == normalized_reason:
            continue
        row["ArchiveReason"] = normalized_reason
        row["UpdatedAt"] = datetime.utcnow().isoformat(timespec="seconds")
        changed = True
    if not changed:
        return False
    write_paper_archive_overrides(archive_rows.values(), PAPER_ARCHIVE_OVERRIDES_FILE)
    _refresh_state(f"Updated archive reason for {len(updated_ids)} archived paper(s).")
    return True
```

- [ ] **Step 4: Add the Archived tab bulk action UI**

Use the existing search + reason filter as the selection mechanism.

Render:

- `New archive reason`
- `Apply to N filtered archived paper(s)`

Behavior:

- apply to the currently filtered rows only
- disable the button when the filtered result set is empty
- rerun after success so the filter summary and reason counts update

- [ ] **Step 5: Re-run the targeted tests**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest wic_app.tests.test_archived_view wic_app.tests.test_engine -v`

Expected: PASS with filtered bulk reason editing covered

## Final Verification

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  wic_app.tests.test_engine \
  wic_app.tests.test_label_catalog_engine \
  wic_app.tests.test_papers_view \
  wic_app.tests.test_archived_view \
  wic_app.tests.test_app_layout_config -v
```

Expected:

- all archive/count/catalog tests pass
- no remaining references to hard-coded `ARCHIVE_REASON_OPTIONS` in live code paths

- [ ] **Step 2: Run an app startup smoke test**

Run: `PYTHONDONTWRITEBYTECODE=1 python3 -m unittest wic_app.tests.test_app_startup_smoke -v`

Expected: PASS with the app still importing and starting cleanly

- [ ] **Step 3: Manual UI verification**

Run: `python3 -m streamlit run wic_app/app.py`

Verify manually:

- Checks shows `Total accepted papers = Active papers + Archived papers`
- Checks shows active-paper breakdown with explicit subset captions
- archive-reason labels created in Archived appear immediately in archive dropdowns elsewhere
- bulk reason update applies to the current filtered archived result set only
- restore from archive still works unchanged

## Execution Notes

- Follow `@test-driven-development` during implementation.
- Follow `@verification-before-completion` before declaring the work done.
- Keep the worktree scoped to:
  - Checks hierarchy
  - archive-reason catalog support
  - Archived tab bulk reason editing
- Do not pull in unrelated label-tab, export, or public-app changes while executing this plan.
