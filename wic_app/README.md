# Conference Studio

## Easiest way (double-click)

In Finder, double-click:

- `Conference_Studio.command`

On Windows, double-click:

- `Conference_Studio_Windows.cmd`

On Linux, run:

- `./Conference_Studio_Linux.sh`

What it does automatically:

1. Creates `.venv` if needed
2. Installs dependencies when `wic_app/requirements.txt` changes
3. Starts the Streamlit app

Linux notes:

- Uses `.venv_linux` (separate from `.venv`) to avoid cross-OS virtualenv issues.
- If your distro disables `ensurepip`, the launcher auto-falls back to `--system-site-packages`.

Windows notes:

- Uses `.venv_windows` (separate from `.venv` and `.venv_linux`) to avoid cross-OS virtualenv issues.
- Prefers `py -3` and falls back to `python` if the Python launcher is unavailable.

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

### Phone access on the same network (LAN)

Run Streamlit bound to all interfaces:

```bash
streamlit run wic_app/app.py --server.address 0.0.0.0 --server.port 8501
```

Then open `http://<host-machine-ip>:8501` from your phone on the same Wi-Fi/LAN.

### Hosted deployment baseline

Password gating is dormant by default. It is enabled only when
`APP_REQUIRE_AUTH=true`.

For internet-hosted usage, enable app-level password gating with env vars:

```bash
export APP_PASSWORD='change-this-password'
export APP_REQUIRE_AUTH=true
streamlit run wic_app/app.py --server.address 0.0.0.0 --server.port 8501
```

When auth is enabled, the app reads `APP_PASSWORD` from environment first, then
falls back to Streamlit secrets.

Optional `secrets.toml` example:

```toml
# .streamlit/secrets.toml
APP_PASSWORD = "change-this-password"
```

You still need `APP_REQUIRE_AUTH=true` in the environment to activate the gate.

## Workflow

1. Use **Programme** as the primary workspace:
2. Click a session header or slot in the grid to open the **Inspector** (right panel).
3. Edit paper classification, move/drop papers, or assign empty slots from the Inspector.
4. Edit session titles from the Inspector.
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
