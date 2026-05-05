# Conference Studio

## Easiest way (double-click)

In Finder, double-click:

- `Conference_Studio_mac.command`

On Windows, double-click:

- `Conference_Studio_Windows.cmd`

On Linux, run:

- `./Conference_Studio_Linux.sh`

What it does automatically:

1. Creates the platform virtual environment if needed
2. Installs dependencies when `wic_app/requirements.txt` changes
3. Starts the Streamlit app

macOS notes:

- Uses `~/Library/Application Support/Conference Studio/.venv` to avoid syncing machine-specific virtualenv files through Dropbox.
- If an old repo-local `.venv` is unusable, the launcher moves it aside to `.venv.broken.<timestamp>` and creates a fresh mac environment outside the repo.

Linux notes:

- Uses `.venv_linux` (separate from the mac and Windows environments) to avoid cross-OS virtualenv issues.
- If your distro disables `ensurepip`, the launcher auto-falls back to `--system-site-packages`.

Windows notes:

- Uses `.venv_windows` (separate from the mac and Linux environments) to avoid cross-OS virtualenv issues.
- Prefers `py -3` and falls back to `python` if the Python launcher is unavailable.

## Folder layout

- `source_data/`: local-only input files used to build drafts. Do not publish this folder.
- `exports/`: local-only draft/publish outputs from the editor workflow.
- `public_data/`: generated public JSON/XLSX artifacts intended for the read-only deployed app.
- `public_bundle/`: generated self-contained folder to copy into the separate public repo.
- `wic_app/`: app code, engine, exporters, and local `state/`

## Setup

```bash
python3 -m pip install -r wic_app/requirements.txt
```

## Run the local editor

```bash
streamlit run wic_app/app.py
```

### Phone access on the same network (LAN)

Run Streamlit bound to all interfaces:

```bash
streamlit run wic_app/app.py --server.address 0.0.0.0 --server.port 8501
```

Then open `http://<host-machine-ip>:8501` from your phone on the same Wi-Fi/LAN.

### Local-only working data

The editor auto-saves working changes into `wic_app/state/*.csv`. That state is
private working data and should stay local.

If you sync the project with Dropbox, treat it as single-writer storage:

- one machine editing at a time
- let Dropbox finish syncing before opening the app elsewhere
- do not rely on Dropbox for concurrent editing

## Workflow

1. Use **Programme** as the primary workspace:
2. Click a session header or slot in the grid to open the **Inspector** (right panel).
3. Edit paper classification, move/drop papers, or assign empty slots from the Inspector.
4. Edit session titles from the Inspector.
5. Click any session/slot block to open the **Inspector** automatically; use `✕` to close it.
6. Every edit is auto-applied, auto-saved (`wic_app/state/*.csv`), and synced across tabs.
7. Use top action buttons for **Publish**, **Prepare Public Bundle**, **Preview Public Bundle**, **Undo**, and **Reload**.

## CLI generation

Draft only:

```bash
python3 wic_app/generate_wic_programme_draft.py
```

Draft + publish outputs:

```bash
python3 wic_app/generate_wic_programme_draft.py --publish
```

`--publish` now generates:

- local publish workbook/PDF/Word outputs
- `public_data/programme.json` for the deployed read-only Streamlit app
- `public_data/programme.xlsx` for public download

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

## Public deployment

The public deployment uses a separate read-only entrypoint:

```bash
streamlit run wic_app/public_app.py
```

The public app reads only `public_data/programme.json` by default. It does not
load `source_data/` or `wic_app/state/`.

Keep the public site hidden until you are ready:

```bash
export PUBLIC_ENABLED=false
streamlit run wic_app/public_app.py
```

When you want to publish it:

```bash
python3 wic_app/generate_wic_programme_draft.py --publish
export PUBLIC_ENABLED=true
streamlit run wic_app/public_app.py
```

Optional overrides for deployed environments:

```bash
export PUBLIC_JSON_PATH=/path/to/programme.json
export PUBLIC_XLSX_PATH=/path/to/programme.xlsx
```

## Public bundle workflow

If you want a separate public repository, use **Prepare Public Bundle** in the
editor Actions menu. That generates a local `public_bundle/` folder with:

- `www/index.html`
- `www/assets/styles.css`
- `www/assets/app.js`
- `www/data/programme.json`
- `www/programme.xlsx`
- `README.md`

`public_bundle/` is now a static site bundle. Upload the contents of `www/` to
any standard static host, or preview it locally with:

```bash
cd public_bundle/www
python3 -m http.server 8000
```

Copy the bundle into the separate public repo, commit there, and deploy that
repo independently.

## Security notes

- Do not publish `source_data/`, `exports/`, or `wic_app/state/`.
- Do not publish this private repo directly; use `public_bundle/` or a cleaned public repo.
- Do not store Streamlit secrets in git; keep `.streamlit/secrets.toml` local.
- The public bundle is read-only by construction and should only be deployed with generated artifacts from `public_bundle/www/`.
- If this repository already contains sensitive tracked files from earlier local-only use, remove them from git before making the repository public.

## Optional branding

Create `wic_app/assets/branding.json` (see `wic_app/assets/branding.example.json`) to override:

- `conference_title`
- `conference_subtitle`
- `primary_color`
