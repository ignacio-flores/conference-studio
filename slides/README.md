# Slide Programme Organizer

This folder contains an R workflow for matching submitted presentation decks to the published programme, downloading matched PDFs, and writing a multi-tab Excel report.

## Inputs

Default inputs are resolved from the repository root:

- Slide-submission CSV: newest dated `*.csv` in `slides/`
- Programme source: current app state from the main WIC programme engine
- Reviewed submissions workbook: `source_data/WIC 2026 - Submissions (Reviewed).xlsx`
- Output directory: `exports/slides`

CSV auto-discovery prefers filenames containing a `YYYY-MM-DD` date and selects the newest parsed date. If no CSV filename contains a date, it selects the newest modified CSV. Use `--slides-csv=PATH` to override this.

By default, the script asks the Python app to build the same public payload used by the publish workbook and public bundle. This avoids depending on a stale checked-in `public_data/programme.json`. Use `--programme-source=json` or `--programme-json=PATH` only when you intentionally want to read a saved JSON export.

## Usage

Run from the repository root:

```bash
Rscript slides/organize_slides.R
```

Useful dry run:

```bash
Rscript slides/organize_slides.R --no-download=TRUE
```

Preserve already downloaded PDFs:

```bash
Rscript slides/organize_slides.R --overwrite-pdfs=FALSE
```

Use a specific CSV:

```bash
Rscript slides/organize_slides.R --slides-csv="slides/Parallel Sessions - Slide Submission_Submissions_2026-05-27.csv"
```

All options:

```text
--slides-csv=PATH
--programme-source=state|json
--programme-json=PATH
--email-workbook=PATH
--output-dir=PATH
--no-download=TRUE
--overwrite-pdfs=TRUE|FALSE
--help
```

## Outputs

The workflow writes matched decks and the report under `exports/slides/`.

Folder structure:

```text
exports/slides/
  R2-01/
    day1/
      session-01_11h30-13h00/
        01_Fabre.pdf
```

PDF filenames use the programme `talk_index` and presenter last name, for example `01_Fabre.pdf`.

For overflow talks whose public payload has no positive `talk_index`, the script places them after the numbered talks in the same session and uses that effective order in the filename.

The Excel report is written to:

```text
exports/slides/slide_report.xlsx
```

Report tabs:

- `summary`: counts for programme presentations, matched decks, missing decks, unmatched submissions, downloads, email statuses, and selected CSV metadata.
- `slide_status`: one row per programme presentation, including scheduling fields, title, match method, deck URL, local file path, contact email fields, and download status.
- `missing_presentations`: programme presentations without a matched deck URL.
- `unmatched_submissions`: slide submissions whose normalized title cannot be connected to a programme row.
- `email_mismatches`: matched rows where the reviewed workbook email and slide CSV email differ after trimming and lowercasing.
- `download_failures`: matched rows whose PDF download failed.

## Matching Rules

Slide submissions are matched to programme presentations by deterministic normalized title keys. Normalization lowercases titles, transliterates accents, and ignores whitespace, casing, punctuation, common smart quotes, and dash variants. The script does not fuzzy-place unmatched submissions.

The primary match is slide CSV title to programme title. If that fails, the script tries slide CSV title to reviewed workbook title, then uses the workbook `SubmissionID` only when that submission ID exists in the programme.

If multiple slide submissions have the same normalized title, the newest submitted row is used for the programme match.

## Email Rules

For every programme row, the script looks up the workbook email using programme `submission_id`. For matched slide submissions, it also reads the slide CSV submitter email.

Email status values:

- `matched`: workbook and slide CSV emails both exist and match after trimming and lowercasing.
- `mismatch`: both exist but differ.
- `workbook_only`: only the workbook email is present.
- `slides_csv_only`: only the slide CSV email is present.
- `missing`: neither source has an email.

When both sources differ, `contact_email` uses the slide CSV email first, then falls back to the workbook email. Both original values remain in the report.

## Reruns

By default, existing downloaded PDFs are overwritten:

```bash
Rscript slides/organize_slides.R --overwrite-pdfs=TRUE
```

To keep existing PDFs and only report skipped files:

```bash
Rscript slides/organize_slides.R --overwrite-pdfs=FALSE
```

The report workbook is always regenerated.

## Troubleshooting

- If no CSV is found, put the slide-submission CSV in `slides/` or pass `--slides-csv=PATH`.
- If the wrong CSV is selected, use `--slides-csv=PATH`.
- If titles appear in `unmatched_submissions`, compare them with `slide_status$title`; the workflow only does normalized exact matching.
- If downloads fail, inspect `download_failures` for HTTP status and error detail, then rerun. Successful rows continue even when individual downloads fail.
- If you only want to inspect matching and reports, run with `--no-download=TRUE`.
