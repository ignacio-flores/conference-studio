# WIC Sessions Reclassification Studio

## Easiest way (double-click)

In Finder, double-click:

- `Launch_WIC_Studio.command`

On Linux, run:

- `./Launch_WIC_Studio_Linux.sh`

What it does automatically:

1. Creates `.venv` if needed
2. Installs dependencies when `wic_app/requirements.txt` changes
3. Starts the Streamlit app

Linux notes:

- Uses `.venv_linux` (separate from `.venv`) to avoid cross-OS virtualenv issues.
- If your distro disables `ensurepip`, the launcher auto-falls back to `--system-site-packages`.

## Folder layout

- `source_data/`: original input files used to build drafts
- `exports/`: generated draft/publish outputs
- `wic_app/`: app code, engine, exporters, and `state/`

## Setup

```bash
python3 -m pip install -r wic_app/requirements.txt
```

## Run the curation UI

```bash
streamlit run wic_app/app.py
```

## Workflow

1. Use **Programme** as the primary workspace:
2. Click a session header or slot in the grid to open the **Inspector** (right panel).
3. Edit paper classification, move/drop papers, or assign empty slots from the Inspector.
4. Edit session titles from the Inspector (or in **Session Names** for bulk edits).
5. Click any session/slot block to open the **Inspector** automatically; use `✕` to close it.
6. Every edit is auto-applied, auto-saved (`wic_app/state/*.csv`), and synced across tabs.
7. Use top action buttons for **Publish**, **Undo**, **Reload**, and **Export Draft**.

## CLI generation

Draft only:

```bash
python3 wic_app/generate_wic_programme_draft.py
```

Draft + publish outputs:

```bash
python3 wic_app/generate_wic_programme_draft.py --publish
```

Using a custom conference profile:

```bash
python3 wic_app/generate_wic_programme_draft.py --config /path/to/conference.json --publish
```

For the Streamlit app, set the same config path with:

```bash
export WIC_CONFERENCE_CONFIG=/path/to/conference.json
streamlit run wic_app/app.py
```

The default profile is stored at `wic_app/assets/conference.default.json`.

## Optional branding

Create `wic_app/assets/branding.json` (see `wic_app/assets/branding.example.json`) to override:

- `conference_title`
- `conference_subtitle`
- `primary_color`
