#!/usr/bin/env Rscript

source("slides/organize_slides.R")

assert <- function(condition, message) {
  if (!isTRUE(condition)) {
    stop(message, call. = FALSE)
  }
}

write_dummy_csv <- function(path) {
  writeLines(c("title", "example"), path, useBytes = TRUE)
}

test_csv_selection_by_filename_date <- function() {
  temp_dir <- tempfile("slides-dated-")
  dir_create(temp_dir)
  older <- path(temp_dir, "submissions_2026-05-20.csv")
  newer <- path(temp_dir, "submissions_2026-05-27.csv")
  undated <- path(temp_dir, "submissions.csv")
  write_dummy_csv(older)
  write_dummy_csv(newer)
  write_dummy_csv(undated)
  Sys.setFileTime(undated, Sys.time() + 3600)

  selected <- select_latest_slides_csv(temp_dir)
  assert(path_file(selected$path) == path_file(newer), "newest filename date should win")
  assert(identical(selected$filename_date, as.Date("2026-05-27")), "selected filename date should be parsed")
}

test_csv_selection_by_mtime_fallback <- function() {
  temp_dir <- tempfile("slides-undated-")
  dir_create(temp_dir)
  older <- path(temp_dir, "older.csv")
  newer <- path(temp_dir, "newer.csv")
  write_dummy_csv(older)
  write_dummy_csv(newer)
  Sys.setFileTime(older, as.POSIXct("2026-01-01 00:00:00", tz = "UTC"))
  Sys.setFileTime(newer, as.POSIXct("2026-01-02 00:00:00", tz = "UTC"))

  selected <- select_latest_slides_csv(temp_dir)
  assert(path_file(selected$path) == path_file(newer), "newest modified CSV should win without filename dates")
  assert(selected$selection_method == "newest_modified_csv", "mtime fallback should be reported")
}

test_normalization_and_sanitization <- function() {
  nbsp <- intToUtf8(0x00A0)
  en_dash <- intToUtf8(0x2013)
  o_umlaut <- intToUtf8(0x00F6)
  left <- normalize_title(paste0("  A", nbsp, "Title", en_dash, "With   Space  "))
  right <- normalize_title("A title: with space")
  assert(left == right, "title normalization should standardize whitespace, case, punctuation, and dash variants")
  assert(normalize_title(paste0("L", o_umlaut, "wer's \"Tax\"")) == normalize_title("LOWERS TAX"), "title normalization should transliterate accents and ignore quote marks")

  assert(sanitize_path_component("R2-01") == "R2-01", "room names should retain useful dashes")
  assert(sanitize_path_component(paste0("K", o_umlaut, "hler & Co")) == "Kohler-Co", "path components should transliterate and sanitize")
  assert(build_slide_filename(1, "Adrien Fabre") == "01_Fabre.pdf", "filename should use order and last name")

  folder <- build_slide_folder("exports/slides", "R2-01", 1, 1, "11h30-13h00")
  assert(
    folder == path("exports/slides", "R2-01", "day1", "session-01_11h30-13h00"),
    "folder structure should match the expected room/day/session layout"
  )
}

fixture_programme <- function(output_titles = c("Known Title", "Missing Title")) {
  o_umlaut <- intToUtf8(0x00F6)
  tibble(
    submission_id = c("A1", "B2"),
    title = output_titles,
    presenter_display = c("Adrien Fabre", paste0("Timothy K", o_umlaut, "hler")),
    room = c("R2-01", "P006"),
    day_num = c(1L, 1L),
    day_label = c("Day 1 (4th June)", "Day 1 (4th June)"),
    block_num = c(1L, 1L),
    block_label = c("SESSION 1", "SESSION 1"),
    session_title = c("Preferences", "Mobility"),
    time = c("11h30-13h00", "11h30-13h00"),
    talk_index = c(1L, 2L),
    title_norm = normalize_title(output_titles)
  )
}

fixture_slides <- function() {
  tibble(
    csv_submission_id = c("S1", "S2", "S3"),
    slide_submitted_at = as.POSIXct(
      c("2026-05-01 09:00:00", "2026-05-02 09:00:00", "2026-05-03 09:00:00"),
      tz = "UTC"
    ),
    submitter_name = c("Adrien Fabre", "Adrien Fabre", "No Match"),
    slides_csv_email = c("older@example.com", "a@example.com", "none@example.com"),
    submitted_title = c("Known Title", " Known   Title ", "Not In Programme"),
    slide_url = c("https://example.invalid/old.pdf", "https://example.invalid/new.pdf", "https://example.invalid/no.pdf"),
    title_norm = normalize_title(c("Known Title", " Known   Title ", "Not In Programme")),
    slide_row = 1:3
  )
}

test_matching_and_email_reconciliation <- function() {
  temp_dir <- tempfile("slides-output-")
  programme <- fixture_programme()
  slides <- fixture_slides()
  email_lookup <- tibble(
    submission_id = c("A1", "B2"),
    workbook_email = c("A@Example.com", "b@example.com"),
    workbook_title = c("Known Title", "Missing Title"),
    workbook_title_norm = normalize_title(c("Known Title", "Missing Title"))
  )

  status <- build_slide_status(programme, slides, email_lookup, temp_dir)
  known <- status[status$submission_id == "A1", ]
  missing <- status[status$submission_id == "B2", ]
  unmatched <- unmatched_slide_submissions(slides, programme, email_lookup)

  assert(known$status == "matched", "known programme title should match a slide submission")
  assert(known$csv_submission_id == "S2", "newest duplicate slide submission should be selected")
  assert(known$email_status == "matched", "email comparison should ignore case and surrounding whitespace")
  assert(known$match_method == "programme_title", "direct programme title matches should be marked")
  assert(missing$status == "missing", "programme row without a slide should be marked missing")
  assert(missing$email_status == "workbook_only", "missing slide email should produce workbook_only")
  assert(nrow(unmatched) == 1 && unmatched$csv_submission_id == "S3", "unmatched submissions should be quarantined")

  emails <- reconcile_emails(
    c("a@example.com", "a@example.com", "", ""),
    c("a@example.com", "b@example.com", "c@example.com", "")
  )
  assert(
    identical(emails$email_status, c("matched", "mismatch", "slides_csv_only", "missing")),
    "email reconciliation should cover all expected statuses"
  )
  assert(emails$contact_email[[2]] == "b@example.com", "mismatched emails should use the slide CSV email as contact_email")
}

test_workbook_title_fallback_matching <- function() {
  temp_dir <- tempfile("slides-workbook-fallback-")
  programme <- tibble(
    submission_id = c("C3"),
    title = c("Edited Programme Title"),
    presenter_display = c("Casey Presenter"),
    room = c("R2-01"),
    day_num = c(1L),
    day_label = c("Day 1 (4th June)"),
    block_num = c(1L),
    block_label = c("SESSION 1"),
    session_title = c("Fallback Session"),
    time = c("11h30-13h00"),
    talk_index = c(1L),
    title_norm = normalize_title("Edited Programme Title")
  )
  slides <- tibble(
    csv_submission_id = c("S4", "S5"),
    slide_submitted_at = as.POSIXct(c("2026-05-04 09:00:00", "2026-05-04 10:00:00"), tz = "UTC"),
    submitter_name = c("Casey Presenter", "Unscheduled Presenter"),
    slides_csv_email = c("slides@example.com", "unscheduled@example.com"),
    submitted_title = c("Original: Workbook Title!", "Unscheduled Workbook Title"),
    slide_url = c("https://example.invalid/fallback.pdf", "https://example.invalid/unscheduled.pdf"),
    title_norm = normalize_title(c("Original Workbook Title", "Unscheduled Workbook Title")),
    slide_row = 1:2
  )
  email_lookup <- tibble(
    submission_id = c("C3", "D4"),
    workbook_email = c("workbook@example.com", "other@example.com"),
    workbook_title = c("Original Workbook Title", "Unscheduled Workbook Title"),
    workbook_title_norm = normalize_title(c("Original Workbook Title", "Unscheduled Workbook Title"))
  )

  status <- build_slide_status(programme, slides, email_lookup, temp_dir)
  unmatched <- unmatched_slide_submissions(slides, programme, email_lookup)

  assert(status$status == "matched", "workbook title fallback should match by programme submission_id")
  assert(status$match_method == "workbook_title_submission_id", "workbook fallback matches should be marked")
  assert(status$contact_email == "slides@example.com", "fallback matches should still prioritize slide CSV email")
  assert(nrow(unmatched) == 1 && unmatched$csv_submission_id == "S5", "workbook rows absent from programme should remain unmatched")
}

test_programme_json_loading_and_overflow_order <- function() {
  temp_json <- tempfile(fileext = ".json")
  payload <- list(
    papers = list(
      list(
        submission_id = "OVER",
        title = "Overflow Talk",
        presenter_display = "Overflow Presenter",
        room = "P006",
        session_id = "session-1",
        day_num = 1L,
        day_label = "Day 1 (4th June)",
        block_num = 3L,
        block_label = "SESSION 3",
        session_title = "Distributional National Accounts",
        time = "16h00-18h00",
        talk_index = 0L
      ),
      list(
        submission_id = "ONE",
        title = "First Talk",
        presenter_display = "First Presenter",
        room = "P006",
        session_id = "session-1",
        day_num = 1L,
        day_label = "Day 1 (4th June)",
        block_num = 3L,
        block_label = "SESSION 3",
        session_title = "Distributional National Accounts",
        time = "16h00-18h00",
        talk_index = 1L
      ),
      list(
        submission_id = "TWO",
        title = "Second Talk",
        presenter_display = "Second Presenter",
        room = "P006",
        session_id = "session-1",
        day_num = 1L,
        day_label = "Day 1 (4th June)",
        block_num = 3L,
        block_label = "SESSION 3",
        session_title = "Distributional National Accounts",
        time = "16h00-18h00",
        talk_index = 2L
      )
    )
  )
  writeLines(jsonlite::toJSON(payload, auto_unbox = TRUE), temp_json)

  programme <- read_programme_papers("json", temp_json)
  overflow <- programme[programme$submission_id == "OVER", ]
  parsed <- parse_cli_args(c(paste0("--programme-json=", temp_json)))

  assert(overflow$talk_index == 3L, "zero-index overflow talks should be ordered after numbered talks")
  assert(parsed$programme_source == "json", "--programme-json should switch the source to json")
}

test_report_tabs <- function() {
  temp_dir <- tempfile("slides-report-")
  programme <- fixture_programme()
  slides <- fixture_slides()
  email_lookup <- tibble(
    submission_id = c("A1", "B2"),
    workbook_email = c("a@example.com", "b@example.com"),
    workbook_title = c("Known Title", "Missing Title"),
    workbook_title_norm = normalize_title(c("Known Title", "Missing Title"))
  )
  status <- build_slide_status(programme, slides, email_lookup, temp_dir)
  unmatched <- unmatched_slide_submissions(slides, programme, email_lookup)
  selected_csv <- list(
    path = "slides/submissions_2026-05-27.csv",
    filename_date = as.Date("2026-05-27"),
    selection_method = "newest_filename_date"
  )
  summary <- summary_table(status, unmatched, selected_csv, no_download = TRUE, overwrite_pdfs = TRUE)
  report_path <- path(temp_dir, "slide_report.xlsx")

  write_report(report_path, summary, status, unmatched)
  expected <- c(
    "summary",
    "slide_status",
    "missing_presentations",
    "unmatched_submissions",
    "email_mismatches",
    "download_failures"
  )
  assert(file_exists(report_path), "report workbook should be written")
  assert(identical(getSheetNames(report_path), expected), "report workbook should contain the expected tabs")
  assert(nrow(read.xlsx(report_path, sheet = "download_failures")) == 0, "empty report tabs should not contain blank rows")
}

test_overwrite_pdf_behavior <- function() {
  temp_dir <- tempfile("slides-downloads-")
  dir_create(temp_dir)
  status <- build_slide_status(
    fixture_programme("Known Title")[1, ],
    fixture_slides()[2, ],
    tibble(
      submission_id = "A1",
      workbook_email = "a@example.com",
      workbook_title = "Known Title",
      workbook_title_norm = normalize_title("Known Title")
    ),
    temp_dir
  )
  dir_create(status$folder_path)
  writeLines("old", status$local_file_path)

  fake_downloader <- function(url, destination, overwrite) {
    writeLines("new", destination)
    list(download_status = "success", download_detail = "fake", http_status = 200L)
  }

  preserved <- process_downloads(
    status,
    no_download = FALSE,
    overwrite_pdfs = FALSE,
    downloader = fake_downloader
  )
  assert(preserved$download_status == "skipped_existing", "existing PDF should be skipped when overwrite is FALSE")
  assert(readLines(status$local_file_path) == "old", "existing PDF contents should be preserved")

  replaced <- process_downloads(
    status,
    no_download = FALSE,
    overwrite_pdfs = TRUE,
    downloader = fake_downloader
  )
  assert(replaced$download_status == "success", "overwrite TRUE should call the downloader")
  assert(readLines(status$local_file_path) == "new", "overwrite TRUE should replace existing contents")
}

tests <- list(
  test_csv_selection_by_filename_date,
  test_csv_selection_by_mtime_fallback,
  test_normalization_and_sanitization,
  test_matching_and_email_reconciliation,
  test_workbook_title_fallback_matching,
  test_programme_json_loading_and_overflow_order,
  test_report_tabs,
  test_overwrite_pdf_behavior
)

for (test in tests) {
  test()
}

cat(sprintf("Passed %d slide organizer tests.\n", length(tests)))
