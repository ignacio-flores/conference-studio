# Public Static WWW Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current Streamlit-based public bundle with a static `www/` export that is programme-first, mobile-friendly, and upload-ready for any standard web server.

**Architecture:** Keep the existing public JSON/XLSX generation as the data source, but swap the public bundle assembly from copied Python runtime files to static HTML/CSS/JS assets. Build a small client-side renderer that loads `www/data/programme.json`, renders the programme homepage and papers directory, and supports hover-enhanced desktop interactions plus tap-first mobile expansion.

**Tech Stack:** Python, existing public JSON export pipeline, static HTML, CSS, vanilla JavaScript, `unittest`

---

## File Structure

### Existing files to modify

- `wic_app/bundle_public_app.py`
  - Replace Streamlit bundle assembly with static `www/` assembly.
- `wic_app/preview_public_bundle.py`
  - Preview the static bundle through a simple local static server instead of Streamlit.
- `wic_app/README.md`
  - Update public bundle workflow documentation for `www/`.
- `wic_app/tests/test_public_bundle.py`
  - Replace Streamlit-oriented bundle expectations with static bundle assertions.
- `wic_app/tests/test_public_preview.py`
  - Update preview expectations from Streamlit entrypoint to static `index.html`.
- `wic_app/ui/actions.py`
  - Keep menu wording aligned if the bundle shape or preview wording needs to change.

### Existing files to review, then likely leave untouched

- `wic_app/public_data.py`
  - Existing public payload IO helpers.
- `wic_app/exporters/publish.py`
  - Existing public JSON/XLSX generation.
- `docs/superpowers/specs/2026-04-17-public-static-www-design.md`
  - Approved design reference.

### New files to create

- `wic_app/public_www/index.html`
  - Static shell for the public site.
- `wic_app/public_www/assets/styles.css`
  - Editorial, mobile-first styling.
- `wic_app/public_www/assets/app.js`
  - Client-side rendering, filtering, expansion, and state management.
- `wic_app/tests/test_public_www_layout.py`
  - Static front-end structure assertions.

---

## Chunk 1: Replace Bundle Packaging

### Task 1: Lock the new static bundle shape with failing tests

**Files:**
- Modify: `wic_app/tests/test_public_bundle.py`
- Modify: `wic_app/tests/test_public_preview.py`
- Test: `wic_app/tests/test_public_bundle.py`
- Test: `wic_app/tests/test_public_preview.py`

- [ ] **Step 1: Write the failing tests**

Add assertions that the assembled bundle contains:
- `www/index.html`
- `www/assets/styles.css`
- `www/assets/app.js`
- `www/data/programme.json`
- `www/programme.xlsx`
- `README.md`

Add assertions that it does **not** contain:
- `wic_app/public_app.py`
- `wic_app/public_data.py`
- `requirements.txt`
- `public_data/`
- `source_data/`
- `exports/`

Update preview tests to require `www/index.html` instead of `wic_app/public_app.py`.

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
python3 -m unittest wic_app.tests.test_public_bundle wic_app.tests.test_public_preview
```

Expected:
- FAIL because the current bundle still produces the Streamlit layout and preview path.

- [ ] **Step 3: Write minimal implementation**

Implement static bundle assembly in `wic_app/bundle_public_app.py` and switch preview entrypoint detection in `wic_app/preview_public_bundle.py` to the static site.

- [ ] **Step 4: Run tests to verify they pass**

Run:
```bash
python3 -m unittest wic_app.tests.test_public_bundle wic_app.tests.test_public_preview
```

Expected:
- PASS

### Task 2: Implement static preview serving

**Files:**
- Modify: `wic_app/preview_public_bundle.py`
- Test: `wic_app/tests/test_public_preview.py`

- [ ] **Step 1: Write the failing test**

Add or refine preview assertions so the preview helper:
- requires `www/index.html`
- starts a simple static HTTP server from the bundle root
- returns the preview URL and started state

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python3 -m unittest wic_app.tests.test_public_preview.PublicPreviewTests
```

Expected:
- FAIL on old Streamlit assumptions

- [ ] **Step 3: Write minimal implementation**

Use `python3 -m http.server` or equivalent from the bundle root, serving the static site without Python app runtime dependencies in the bundle itself.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
python3 -m unittest wic_app.tests.test_public_preview.PublicPreviewTests
```

Expected:
- PASS

---

## Chunk 2: Build the Static Front-End

### Task 3: Lock the static front-end structure with failing tests

**Files:**
- Create: `wic_app/tests/test_public_www_layout.py`
- Test: `wic_app/tests/test_public_www_layout.py`

- [ ] **Step 1: Write the failing test**

Add tests that assert:
- `index.html` references `assets/styles.css` and `assets/app.js`
- the page exposes programme-first navigation hooks
- the HTML contains containers for day switching, programme blocks, session expansion, papers directory, and download action
- the JavaScript contains hooks for tap/click expansion and abstract reveal

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python3 -m unittest wic_app.tests.test_public_www_layout
```

Expected:
- FAIL because the static front-end files do not exist yet

- [ ] **Step 3: Write minimal implementation**

Create the static front-end files with the required DOM structure and interaction hooks.

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
python3 -m unittest wic_app.tests.test_public_www_layout
```

Expected:
- PASS

### Task 4: Build the HTML shell

**Files:**
- Create: `wic_app/public_www/index.html`
- Modify: `wic_app/tests/test_public_www_layout.py`

- [ ] **Step 1: Write the failing test**

Extend coverage to require:
- programme as the default/home surface
- a day selector region
- a session detail region or inline expansion host
- a papers directory surface
- an Excel download action

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python3 -m unittest wic_app.tests.test_public_www_layout.PublicWwwLayoutTests
```

Expected:
- FAIL until the semantic HTML shell exists

- [ ] **Step 3: Write minimal implementation**

Implement a simple `index.html` with:
- header
- day selector container
- programme container
- papers container
- templates or placeholders for session cards and talk rows

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
python3 -m unittest wic_app.tests.test_public_www_layout.PublicWwwLayoutTests
```

Expected:
- PASS

### Task 5: Build editorial, responsive CSS

**Files:**
- Create: `wic_app/public_www/assets/styles.css`
- Modify: `wic_app/tests/test_public_www_layout.py`

- [ ] **Step 1: Write the failing test**

Add assertions that the stylesheet includes:
- mobile-first layout rules
- editorial typography variables or font stack declarations
- distinct day/block/session/talk styling hooks
- hover and expanded-state classes

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python3 -m unittest wic_app.tests.test_public_www_layout.PublicWwwLayoutTests
```

Expected:
- FAIL until the stylesheet is present with the expected hooks

- [ ] **Step 3: Write minimal implementation**

Implement CSS for:
- warm paper-like background
- elegant typography hierarchy
- spacious block rhythm
- large tap targets
- responsive shift from desktop grouping to stacked mobile cards

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
python3 -m unittest wic_app.tests.test_public_www_layout.PublicWwwLayoutTests
```

Expected:
- PASS

### Task 6: Build the client-side renderer

**Files:**
- Create: `wic_app/public_www/assets/app.js`
- Modify: `wic_app/tests/test_public_www_layout.py`

- [ ] **Step 1: Write the failing test**

Add assertions that `app.js` includes named logic or identifiable hooks for:
- loading `data/programme.json`
- defaulting to the programme homepage
- switching days
- rendering programme blocks and sessions
- expanding sessions
- revealing abstracts on click/tap
- optional desktop hover enhancement
- rendering papers directory and search/filter state

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python3 -m unittest wic_app.tests.test_public_www_layout.PublicWwwLayoutTests
```

Expected:
- FAIL until the client logic exists

- [ ] **Step 3: Write minimal implementation**

Implement a small client-side state model:
- fetch JSON once
- track selected day
- render block-grouped sessions
- render expandable talks
- reveal abstracts inline
- render papers list with lightweight filtering

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
python3 -m unittest wic_app.tests.test_public_www_layout.PublicWwwLayoutTests
```

Expected:
- PASS

---

## Chunk 3: Integrate Data and Docs

### Task 7: Connect the static assets to bundle generation

**Files:**
- Modify: `wic_app/bundle_public_app.py`
- Modify: `wic_app/tests/test_public_bundle.py`

- [ ] **Step 1: Write the failing test**

Add assertions that bundle generation copies static assets from `wic_app/public_www/` into `www/` and writes public artifacts to the correct static paths.

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python3 -m unittest wic_app.tests.test_public_bundle.PublicBundleTests
```

Expected:
- FAIL until asset copying and output placement are implemented

- [ ] **Step 3: Write minimal implementation**

Copy:
- `wic_app/public_www/index.html` -> `www/index.html`
- `wic_app/public_www/assets/*` -> `www/assets/*`

Write:
- `programme.json` -> `www/data/programme.json`
- `programme.xlsx` -> `www/programme.xlsx`

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
python3 -m unittest wic_app.tests.test_public_bundle.PublicBundleTests
```

Expected:
- PASS

### Task 8: Update public bundle documentation

**Files:**
- Modify: `wic_app/README.md`

- [ ] **Step 1: Write the failing test**

If there is no existing documentation test for the public bundle workflow, add or extend one to require:
- `www/` references
- static hosting language
- no Streamlit deployment instructions for the bundle

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
python3 -m unittest wic_app.tests.test_repo_rename_hygiene
```

Expected:
- FAIL if old public bundle wording is still required there, or update/add a more focused doc assertion test first

- [ ] **Step 3: Write minimal implementation**

Update the README public bundle section to describe:
- generated `www/`
- upload to static host
- preview behavior
- security notes for publishing only the static bundle

- [ ] **Step 4: Run test to verify it passes**

Run the relevant doc test(s), for example:
```bash
python3 -m unittest wic_app.tests.test_repo_rename_hygiene
```

Expected:
- PASS

---

## Chunk 4: Final Verification

### Task 9: Run the focused public-site verification suite

**Files:**
- Modify: `wic_app/bundle_public_app.py`
- Modify: `wic_app/preview_public_bundle.py`
- Modify: `wic_app/README.md`
- Create/Modify: `wic_app/public_www/index.html`
- Create/Modify: `wic_app/public_www/assets/styles.css`
- Create/Modify: `wic_app/public_www/assets/app.js`
- Test: `wic_app/tests/test_public_bundle.py`
- Test: `wic_app/tests/test_public_preview.py`
- Test: `wic_app/tests/test_public_www_layout.py`

- [ ] **Step 1: Run the focused public tests**

Run:
```bash
python3 -m unittest \
  wic_app.tests.test_public_bundle \
  wic_app.tests.test_public_preview \
  wic_app.tests.test_public_www_layout
```

Expected:
- PASS

- [ ] **Step 2: Run a syntax check**

Run:
```bash
python3 -m py_compile \
  wic_app/bundle_public_app.py \
  wic_app/preview_public_bundle.py
```

Expected:
- PASS

- [ ] **Step 3: Review the final diff**

Run:
```bash
git diff -- \
  wic_app/bundle_public_app.py \
  wic_app/preview_public_bundle.py \
  wic_app/README.md \
  wic_app/public_www/index.html \
  wic_app/public_www/assets/styles.css \
  wic_app/public_www/assets/app.js \
  wic_app/tests/test_public_bundle.py \
  wic_app/tests/test_public_preview.py \
  wic_app/tests/test_public_www_layout.py \
  docs/superpowers/specs/2026-04-17-public-static-www-design.md \
  docs/superpowers/plans/2026-04-17-public-static-www-implementation.md
```

Expected:
- Only the approved static `www/` bundle rewrite and its tests/docs are included
