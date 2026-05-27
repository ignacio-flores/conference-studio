#!/usr/bin/env Rscript

suppressPackageStartupMessages({
  library(dplyr)
  library(fs)
  library(httr)
  library(jsonlite)
  library(openxlsx)
  library(readr)
  library(readxl)
  library(stringr)
})

usage <- function() {
  cat(
    paste(
      "Usage:",
      "  Rscript slides/organize_slides.R [options]",
      "",
      "Options:",
      "  --slides-csv=PATH        Slide-submission CSV. Defaults to newest dated CSV in slides/.",
      "  --programme-source=MODE  Programme source: state or json. Default: state",
      "  --programme-json=PATH    Programme JSON path when using --programme-source=json.",
      "  --email-workbook=PATH    Reviewed submissions workbook. Default: source_data/WIC 2026 - Submissions (Reviewed).xlsx",
      "  --output-dir=PATH        Output directory. Default: exports/slides",
      "  --no-download=TRUE       Create folders and reports without downloading PDFs.",
      "  --overwrite-pdfs=BOOL    Overwrite existing PDFs. Default: TRUE",
      "  --help                   Print this help and exit.",
      "",
      "Examples:",
      "  Rscript slides/organize_slides.R",
      "  Rscript slides/organize_slides.R --no-download=TRUE",
      "  Rscript slides/organize_slides.R --overwrite-pdfs=FALSE",
      sep = "\n"
    )
  )
}

parse_bool <- function(value, option_name) {
  normalized <- str_to_lower(str_trim(as.character(value)))
  if (normalized %in% c("true", "t", "1", "yes", "y")) {
    return(TRUE)
  }
  if (normalized %in% c("false", "f", "0", "no", "n")) {
    return(FALSE)
  }
  stop(sprintf("%s must be TRUE or FALSE, got: %s", option_name, value), call. = FALSE)
}

parse_cli_args <- function(args) {
  options <- list(
    slides_csv = NULL,
    programme_source = "state",
    programme_json = "public_data/programme.json",
    email_workbook = "source_data/WIC 2026 - Submissions (Reviewed).xlsx",
    output_dir = "exports/slides",
    no_download = FALSE,
    overwrite_pdfs = TRUE,
    help = FALSE
  )

  for (arg in args) {
    if (identical(arg, "--help")) {
      options$help <- TRUE
    } else if (identical(arg, "--no-download")) {
      options$no_download <- TRUE
    } else if (startsWith(arg, "--slides-csv=")) {
      options$slides_csv <- sub("^--slides-csv=", "", arg)
    } else if (startsWith(arg, "--programme-source=")) {
      options$programme_source <- str_to_lower(sub("^--programme-source=", "", arg))
    } else if (startsWith(arg, "--programme-json=")) {
      options$programme_json <- sub("^--programme-json=", "", arg)
      options$programme_source <- "json"
    } else if (startsWith(arg, "--email-workbook=")) {
      options$email_workbook <- sub("^--email-workbook=", "", arg)
    } else if (startsWith(arg, "--output-dir=")) {
      options$output_dir <- sub("^--output-dir=", "", arg)
    } else if (startsWith(arg, "--no-download=")) {
      options$no_download <- parse_bool(sub("^--no-download=", "", arg), "--no-download")
    } else if (startsWith(arg, "--overwrite-pdfs=")) {
      options$overwrite_pdfs <- parse_bool(sub("^--overwrite-pdfs=", "", arg), "--overwrite-pdfs")
    } else {
      stop(sprintf("Unknown option: %s", arg), call. = FALSE)
    }
  }

  if (!options$programme_source %in% c("state", "json")) {
    stop("--programme-source must be state or json", call. = FALSE)
  }

  options
}

clean_text <- function(x) {
  x <- ifelse(is.na(x), "", as.character(x))
  str_squish(x)
}

ascii_transliterate <- function(x) {
  x <- clean_text(x)
  converted <- iconv(x, from = "", to = "ASCII//TRANSLIT", sub = "")
  ifelse(is.na(converted), x, converted)
}

normalize_title <- function(x) {
  x <- ascii_transliterate(x)
  x <- str_replace_all(x, "\\u00A0", " ")
  x <- str_replace_all(x, "[\\u2018\\u2019\\u201B\\u2032]", "'")
  x <- str_replace_all(x, "[\\u201C\\u201D\\u201F\\u2033]", "\"")
  x <- str_replace_all(x, "[\\u2013\\u2014]", "-")
  x <- str_to_lower(x)
  x <- str_replace_all(x, "&", " and ")
  x <- str_replace_all(x, "'", "")
  x <- str_replace_all(x, "[^a-z0-9]+", "")
  x
}

sanitize_path_component <- function(x, fallback = "unnamed") {
  x <- ascii_transliterate(x)
  x <- str_replace_all(x, "[^A-Za-z0-9._-]+", "-")
  x <- str_replace_all(x, "-+", "-")
  x <- str_replace_all(x, "^[._-]+|[._-]+$", "")
  x <- ifelse(x == "", fallback, x)
  x
}

presenter_last_name <- function(presenter_display) {
  presenter_display <- clean_text(presenter_display)
  first_presenter <- str_split(
    presenter_display,
    "\\s+(?:&|and)\\s+|\\s*/\\s*|,",
    n = 2,
    simplify = TRUE
  )[, 1]
  tokens <- str_split(str_squish(first_presenter), "\\s+")
  last_names <- vapply(tokens, function(parts) {
    parts <- parts[parts != ""]
    if (length(parts) == 0) {
      return("Presenter")
    }
    tail(parts, 1)
  }, character(1))
  sanitize_path_component(last_names, fallback = "Presenter")
}

build_slide_filename <- function(talk_index, presenter_display) {
  talk_index <- suppressWarnings(as.integer(talk_index))
  prefix <- ifelse(is.na(talk_index), "00", sprintf("%02d", talk_index))
  paste0(prefix, "_", presenter_last_name(presenter_display), ".pdf")
}

build_slide_folder <- function(output_dir, room, day_num, block_num, time) {
  day_num <- suppressWarnings(as.integer(day_num))
  block_num <- suppressWarnings(as.integer(block_num))
  day_component <- ifelse(is.na(day_num), "day-unknown", paste0("day", day_num))
  session_component <- paste0(
    "session-",
    ifelse(is.na(block_num), "00", sprintf("%02d", block_num)),
    "_",
    sanitize_path_component(time, fallback = "time-unknown")
  )
  fs::path(
    output_dir,
    sanitize_path_component(room, fallback = "room-unknown"),
    day_component,
    session_component
  )
}

extract_filename_date <- function(paths) {
  matches <- str_extract(path_file(paths), "\\d{4}-\\d{2}-\\d{2}")
  as.Date(matches)
}

select_latest_slides_csv <- function(slides_dir = "slides") {
  csv_paths <- dir_ls(slides_dir, glob = "*.csv", recurse = FALSE, type = "file")
  if (length(csv_paths) == 0) {
    stop(sprintf("No CSV files found in %s", slides_dir), call. = FALSE)
  }

  info <- file_info(csv_paths)
  dates <- extract_filename_date(csv_paths)
  dated <- !is.na(dates)

  if (any(dated)) {
    candidates <- tibble(
      path = as.character(csv_paths[dated]),
      filename_date = dates[dated],
      modification_time = info$modification_time[dated]
    ) %>%
      arrange(desc(filename_date), desc(modification_time), desc(path))
    return(list(
      path = candidates$path[[1]],
      filename_date = candidates$filename_date[[1]],
      selection_method = "newest_filename_date"
    ))
  }

  candidates <- tibble(
    path = as.character(csv_paths),
    filename_date = as.Date(NA),
    modification_time = info$modification_time
  ) %>%
    arrange(desc(modification_time), desc(path))

  list(
    path = candidates$path[[1]],
    filename_date = as.Date(NA),
    selection_method = "newest_modified_csv"
  )
}

header_key <- function(x) {
  x <- str_to_lower(str_squish(as.character(x)))
  str_replace_all(x, "[^a-z0-9]+", "_") %>%
    str_replace_all("^_+|_+$", "")
}

find_column <- function(data, candidates, required = TRUE) {
  keys <- header_key(names(data))
  wanted <- header_key(candidates)
  idx <- match(wanted, keys, nomatch = 0)
  idx <- idx[idx > 0]
  if (length(idx) > 0) {
    return(names(data)[idx[[1]]])
  }
  if (required) {
    stop(
      sprintf(
        "Missing required column. Expected one of: %s",
        paste(candidates, collapse = ", ")
      ),
      call. = FALSE
    )
  }
  NA_character_
}

read_slide_submissions <- function(slides_csv) {
  raw <- read_csv(slides_csv, show_col_types = FALSE, trim_ws = TRUE)

  submission_id_col <- find_column(raw, "Submission ID", required = FALSE)
  submitted_at_col <- find_column(raw, "Submitted at", required = FALSE)
  full_name_col <- find_column(raw, c("Full name", "Full name "), required = FALSE)
  email_col <- find_column(
    raw,
    c(
      "Email address with which you registered to the conference",
      "Email address",
      "Email"
    ),
    required = FALSE
  )
  title_col <- find_column(raw, c("Type and select your paper's title", "Title"), required = TRUE)
  url_col <- find_column(
    raw,
    c("Presentation slides in PDF format", "Presentation slides", "Slides URL"),
    required = TRUE
  )

  optional_value <- function(col) {
    if (is.na(col)) {
      rep("", nrow(raw))
    } else {
      raw[[col]]
    }
  }

  submitted_at <- optional_value(submitted_at_col)
  if (!inherits(submitted_at, "POSIXct")) {
    submitted_at <- suppressWarnings(as.POSIXct(submitted_at, tz = "UTC"))
  }

  tibble(
    csv_submission_id = clean_text(optional_value(submission_id_col)),
    slide_submitted_at = submitted_at,
    submitter_name = clean_text(optional_value(full_name_col)),
    slides_csv_email = clean_text(optional_value(email_col)),
    submitted_title = clean_text(raw[[title_col]]),
    slide_url = clean_text(raw[[url_col]]),
    title_norm = normalize_title(raw[[title_col]]),
    slide_row = seq_len(nrow(raw))
  )
}

load_programme_from_state <- function() {
  temp_script <- tempfile(fileext = ".py")
  temp_json <- tempfile(fileext = ".json")
  on.exit({
    if (file_exists(temp_script)) {
      file_delete(temp_script)
    }
    if (file_exists(temp_json)) {
      file_delete(temp_json)
    }
  }, add = TRUE)

  script <- paste(
    "import json, sys",
    "from runtime_compat import install_hashlib_usedforsecurity_compat",
    "install_hashlib_usedforsecurity_compat()",
    "from reclassification_engine import build_programme_state",
    "from public_data import build_public_payload",
    "state = build_programme_state()",
    "payload = build_public_payload(state, show_rooms=True, show_moderators=True, show_links=True)",
    "with open(sys.argv[1], 'w', encoding='utf-8') as f:",
    "    json.dump(payload, f, ensure_ascii=False)",
    sep = "\n"
  )
  writeLines(script, temp_script, useBytes = TRUE)

  output <- system2(
    "python3",
    args = c(temp_script, temp_json),
    env = c("PYTHONPATH=wic_app"),
    stdout = TRUE,
    stderr = TRUE
  )
  status <- attr(output, "status")
  if (!is.null(status) && status != 0) {
    stop(
      sprintf("Unable to build programme from current app state:\n%s", paste(output, collapse = "\n")),
      call. = FALSE
    )
  }
  fromJSON(temp_json)
}

load_programme_payload <- function(programme_source = "state", programme_json = "public_data/programme.json") {
  if (!programme_source %in% c("state", "json") && file_exists(programme_source)) {
    programme_json <- programme_source
    programme_source <- "json"
  }
  if (identical(programme_source, "state")) {
    return(load_programme_from_state())
  }
  if (!identical(programme_source, "json")) {
    stop("Programme source must be state or json.", call. = FALSE)
  }
  if (!file_exists(programme_json)) {
    stop(sprintf("Programme JSON does not exist: %s", programme_json), call. = FALSE)
  }
  fromJSON(programme_json)
}

read_programme_papers <- function(programme_source = "state", programme_json = "public_data/programme.json") {
  programme <- load_programme_payload(programme_source, programme_json)
  papers <- as_tibble(programme$papers)

  required <- c(
    "submission_id", "title", "presenter_display", "room", "day_num",
    "day_label", "block_num", "block_label", "session_title", "time",
    "talk_index"
  )
  missing <- setdiff(required, names(papers))
  if (length(missing) > 0) {
    stop(
      sprintf("Programme JSON is missing required field(s): %s", paste(missing, collapse = ", ")),
      call. = FALSE
    )
  }

  papers %>%
    transmute(
      submission_id = clean_text(submission_id),
      title = clean_text(title),
      presenter_display = clean_text(presenter_display),
      room = clean_text(room),
      session_id = clean_text(session_id),
      day_num = as.integer(day_num),
      day_label = clean_text(day_label),
      block_num = as.integer(block_num),
      block_label = clean_text(block_label),
      session_title = clean_text(session_title),
      time = clean_text(time),
      talk_index_raw = as.integer(talk_index),
      title_norm = normalize_title(title)
    ) %>%
    mutate(source_order = row_number()) %>%
    group_by(session_id) %>%
    arrange(source_order, .by_group = TRUE) %>%
    mutate(
      overflow_rank = cumsum(is.na(talk_index_raw) | talk_index_raw <= 0L),
      max_talk_index = max(talk_index_raw[talk_index_raw > 0L], na.rm = TRUE),
      max_talk_index = if_else(is.infinite(max_talk_index), 0L, max_talk_index),
      talk_index = if_else(
        is.na(talk_index_raw) | talk_index_raw <= 0L,
        max_talk_index + overflow_rank,
        talk_index_raw
      )
    ) %>%
    ungroup() %>%
    select(-talk_index_raw, -source_order, -overflow_rank, -max_talk_index) %>%
    arrange(day_num, block_num, room, talk_index, title)
}

read_email_lookup <- function(email_workbook) {
  sheets <- excel_sheets(email_workbook)
  records <- lapply(seq_along(sheets), function(i) {
    sheet <- sheets[[i]]
    raw <- read_excel(email_workbook, sheet = sheet)
    submission_id_col <- find_column(raw, c("SubmissionID", "Submission ID"), required = TRUE)
    email_col <- find_column(raw, c("EmailAddress", "Email Address", "Email"), required = TRUE)
    title_col <- find_column(raw, "Title", required = FALSE)
    full_name_col <- find_column(raw, c("FullName", "Full Name"), required = FALSE)

    optional_value <- function(col) {
      if (is.na(col)) {
        rep("", nrow(raw))
      } else {
        raw[[col]]
      }
    }

    tibble(
      workbook_sheet = sheet,
      workbook_sheet_order = i,
      submission_id = clean_text(raw[[submission_id_col]]),
      workbook_email = clean_text(raw[[email_col]]),
      workbook_title = clean_text(optional_value(title_col)),
      workbook_title_norm = normalize_title(optional_value(title_col)),
      workbook_full_name = clean_text(optional_value(full_name_col))
    )
  })

  bind_rows(records) %>%
    filter(submission_id != "") %>%
    arrange(workbook_sheet_order) %>%
    group_by(submission_id) %>%
    slice(1) %>%
    ungroup() %>%
    select(submission_id, workbook_email, workbook_title, workbook_title_norm, workbook_full_name, workbook_sheet)
}

latest_submission_per_title <- function(slides) {
  slides %>%
    filter(title_norm != "") %>%
    arrange(title_norm, desc(slide_submitted_at), desc(slide_row)) %>%
    group_by(title_norm) %>%
    slice(1) %>%
    ungroup()
}

resolve_slide_matches <- function(programme, slides, email_lookup) {
  slides_for_match <- latest_submission_per_title(slides)
  slide_columns <- c(
    "csv_submission_id",
    "slide_submitted_at",
    "submitter_name",
    "slides_csv_email",
    "submitted_title",
    "slide_url"
  )

  direct_matches <- programme %>%
    select(submission_id, title_norm) %>%
    inner_join(
      slides_for_match %>% select(title_norm, all_of(slide_columns)),
      by = "title_norm"
    ) %>%
    transmute(
      submission_id,
      csv_submission_id,
      slide_submitted_at,
      submitter_name,
      slides_csv_email,
      submitted_title,
      slide_url,
      match_method = "programme_title"
    )

  if (!"workbook_title" %in% names(email_lookup)) {
    email_lookup$workbook_title <- ""
  }
  if (!"workbook_title_norm" %in% names(email_lookup)) {
    email_lookup$workbook_title_norm <- normalize_title(email_lookup$workbook_title)
  }

  workbook_title_lookup <- email_lookup %>%
    filter(submission_id %in% programme$submission_id, workbook_title_norm != "") %>%
    select(submission_id, workbook_title_norm)

  workbook_matches <- workbook_title_lookup %>%
    inner_join(
      slides_for_match %>% select(workbook_title_norm = title_norm, all_of(slide_columns)),
      by = "workbook_title_norm"
    ) %>%
    anti_join(direct_matches %>% select(submission_id), by = "submission_id") %>%
    transmute(
      submission_id,
      csv_submission_id,
      slide_submitted_at,
      submitter_name,
      slides_csv_email,
      submitted_title,
      slide_url,
      match_method = "workbook_title_submission_id"
    )

  bind_rows(direct_matches, workbook_matches) %>%
    arrange(submission_id, match_method, desc(slide_submitted_at)) %>%
    group_by(submission_id) %>%
    slice(1) %>%
    ungroup()
}

reconcile_emails <- function(workbook_email, slides_csv_email) {
  workbook_email <- clean_text(workbook_email)
  slides_csv_email <- clean_text(slides_csv_email)
  workbook_norm <- str_to_lower(workbook_email)
  slides_norm <- str_to_lower(slides_csv_email)

  status <- case_when(
    workbook_norm != "" & slides_norm != "" & workbook_norm == slides_norm ~ "matched",
    workbook_norm != "" & slides_norm != "" & workbook_norm != slides_norm ~ "mismatch",
    workbook_norm != "" & slides_norm == "" ~ "workbook_only",
    workbook_norm == "" & slides_norm != "" ~ "slides_csv_only",
    TRUE ~ "missing"
  )

  contact_email <- case_when(
    slides_csv_email != "" ~ slides_csv_email,
    workbook_email != "" ~ workbook_email,
    TRUE ~ ""
  )

  tibble(
    contact_email = contact_email,
    workbook_email = workbook_email,
    slides_csv_email = slides_csv_email,
    email_status = status
  )
}

build_slide_status <- function(programme, slides, email_lookup, output_dir) {
  slide_matches <- resolve_slide_matches(programme, slides, email_lookup)

  status <- programme %>%
    left_join(slide_matches, by = "submission_id") %>%
    left_join(email_lookup, by = "submission_id")

  email_columns <- reconcile_emails(status$workbook_email, status$slides_csv_email)
  status$contact_email <- email_columns$contact_email
  status$workbook_email <- email_columns$workbook_email
  status$slides_csv_email <- email_columns$slides_csv_email
  status$email_status <- email_columns$email_status

  status$folder_path <- build_slide_folder(
    output_dir,
    status$room,
    status$day_num,
    status$block_num,
    status$time
  )
  status$local_file_path <- fs::path(
    status$folder_path,
    build_slide_filename(status$talk_index, status$presenter_display)
  )
  status$status <- case_when(
    !is.na(status$csv_submission_id) & clean_text(status$slide_url) != "" ~ "matched",
    !is.na(status$csv_submission_id) ~ "matched_no_url",
    TRUE ~ "missing"
  )
  status$match_method <- ifelse(is.na(status$match_method), "missing", status$match_method)
  status$download_status <- ""
  status$download_detail <- ""
  status$http_status <- NA_integer_

  status %>%
    transmute(
      room,
      day = day_label,
      day_num,
      session = session_title,
      block = block_label,
      block_num,
      time,
      talk_order = talk_index,
      presenter = presenter_display,
      title,
      submission_id,
      status,
      match_method,
      deck_url = slide_url,
      local_file_path = as.character(local_file_path),
      folder_path = as.character(folder_path),
      csv_submission_id,
      submitter_name,
      contact_email,
      workbook_email,
      slides_csv_email,
      email_status,
      download_status,
      download_detail,
      http_status
    ) %>%
    arrange(day_num, block_num, room, talk_order, title)
}

unmatched_slide_submissions <- function(slides, programme, email_lookup = NULL) {
  matched_title_norms <- unique(programme$title_norm)
  if (!is.null(email_lookup)) {
    if (!"workbook_title" %in% names(email_lookup)) {
      email_lookup$workbook_title <- ""
    }
    if (!"workbook_title_norm" %in% names(email_lookup)) {
      email_lookup$workbook_title_norm <- normalize_title(email_lookup$workbook_title)
    }
    matched_title_norms <- unique(c(
      matched_title_norms,
      email_lookup %>%
        filter(submission_id %in% programme$submission_id) %>%
        pull(workbook_title_norm)
    ))
  }

  slides %>%
    filter(title_norm != "", !(title_norm %in% matched_title_norms)) %>%
    transmute(
      submitter_name,
      submitter_email = slides_csv_email,
      submitted_title,
      slide_url,
      csv_submission_id,
      slide_submitted_at
    ) %>%
    arrange(submitted_title, desc(slide_submitted_at))
}

download_pdf <- function(url, destination, overwrite = TRUE) {
  destination <- as.character(destination)

  if (clean_text(url) == "") {
    return(list(
      download_status = "not_available",
      download_detail = "No slide URL was provided.",
      http_status = NA_integer_
    ))
  }

  if (file_exists(destination) && !overwrite) {
    return(list(
      download_status = "skipped_existing",
      download_detail = "Existing PDF preserved.",
      http_status = NA_integer_
    ))
  }

  dir_create(path_dir(destination))
  temp_pdf <- tempfile(fileext = ".pdf")
  on.exit({
    if (file_exists(temp_pdf)) {
      file_delete(temp_pdf)
    }
  }, add = TRUE)

  tryCatch({
    response <- GET(
      url,
      write_disk(temp_pdf, overwrite = TRUE),
      user_agent("conference-studio slide organizer"),
      timeout(120)
    )
    status_code_value <- status_code(response)
    if (status_code_value >= 200 && status_code_value < 300) {
      file_copy(temp_pdf, destination, overwrite = TRUE)
      return(list(
        download_status = "success",
        download_detail = "Downloaded.",
        http_status = status_code_value
      ))
    }

    list(
      download_status = "failed",
      download_detail = sprintf("HTTP %s: %s", status_code_value, http_status(response)$message),
      http_status = status_code_value
    )
  }, error = function(error) {
    list(
      download_status = "failed",
      download_detail = conditionMessage(error),
      http_status = NA_integer_
    )
  })
}

process_downloads <- function(slide_status, no_download = FALSE, overwrite_pdfs = TRUE, downloader = download_pdf) {
  dir_create(unique(slide_status$folder_path))

  if (no_download) {
    slide_status$download_status <- ifelse(slide_status$status == "matched", "not_downloaded", "")
    slide_status$download_detail <- ifelse(slide_status$status == "matched", "Download disabled by --no-download.", "")
    return(slide_status)
  }

  matched_rows <- which(slide_status$status == "matched")
  for (row_index in matched_rows) {
    if (file_exists(slide_status$local_file_path[[row_index]]) && !overwrite_pdfs) {
      slide_status$download_status[[row_index]] <- "skipped_existing"
      slide_status$download_detail[[row_index]] <- "Existing PDF preserved."
      slide_status$http_status[[row_index]] <- NA_integer_
      next
    }

    result <- downloader(
      slide_status$deck_url[[row_index]],
      slide_status$local_file_path[[row_index]],
      overwrite_pdfs
    )
    slide_status$download_status[[row_index]] <- result$download_status
    slide_status$download_detail[[row_index]] <- result$download_detail
    slide_status$http_status[[row_index]] <- result$http_status
  }

  slide_status
}

summary_table <- function(
  slide_status,
  unmatched_submissions,
  selected_csv,
  no_download,
  overwrite_pdfs,
  programme_source = "state",
  programme_json = "public_data/programme.json"
) {
  metric <- c(
    "total_programme_presentations",
    "matched_decks",
    "missing_decks",
    "unmatched_submissions",
    "download_successes",
    "download_failures",
    "download_skipped_existing",
    "email_matches",
    "email_mismatches",
    "selected_csv_filename",
    "selected_csv_date",
    "csv_selection_method",
    "programme_source",
    "programme_json",
    "no_download",
    "overwrite_pdfs"
  )
  value <- c(
    nrow(slide_status),
    sum(slide_status$status == "matched"),
    sum(slide_status$status != "matched"),
    nrow(unmatched_submissions),
    sum(slide_status$download_status == "success"),
    sum(slide_status$download_status == "failed"),
    sum(slide_status$download_status == "skipped_existing"),
    sum(slide_status$email_status == "matched"),
    sum(slide_status$email_status == "mismatch"),
    path_file(selected_csv$path),
    ifelse(is.na(selected_csv$filename_date), "", as.character(selected_csv$filename_date)),
    selected_csv$selection_method,
    programme_source,
    ifelse(identical(programme_source, "json"), programme_json, ""),
    as.character(no_download),
    as.character(overwrite_pdfs)
  )
  tibble(metric = metric, value = as.character(value))
}

missing_presentations_table <- function(slide_status) {
  slide_status %>%
    filter(status != "matched") %>%
    arrange(day, session, talk_order, title) %>%
    transmute(
      title,
      presenter,
      status,
      contact_email,
      workbook_email,
      room,
      day,
      session,
      time,
      submission_id
    )
}

email_mismatches_table <- function(slide_status) {
  slide_status %>%
    filter(email_status == "mismatch") %>%
    transmute(
      title,
      presenter,
      contact_email,
      workbook_email,
      slides_csv_email,
      csv_submission_id,
      submission_id,
      room,
      day,
      session,
      time
    )
}

download_failures_table <- function(slide_status) {
  slide_status %>%
    filter(download_status == "failed") %>%
    transmute(
      title,
      presenter,
      deck_url,
      local_file_path,
      http_status,
      download_detail,
      csv_submission_id,
      submission_id,
      room,
      day,
      session,
      time
    )
}

write_report <- function(report_path, summary, slide_status, unmatched_submissions) {
  dir_create(path_dir(report_path))
  workbook <- createWorkbook()

  sheets <- list(
    summary = summary,
    slide_status = slide_status %>%
      select(
        room, day, session, time, talk_order, presenter, title, status,
        match_method, deck_url, local_file_path, contact_email, workbook_email,
        slides_csv_email, email_status, submission_id, csv_submission_id,
        download_status, download_detail, http_status
      ),
    missing_presentations = missing_presentations_table(slide_status),
    unmatched_submissions = unmatched_submissions,
    email_mismatches = email_mismatches_table(slide_status),
    download_failures = download_failures_table(slide_status)
  )

  for (sheet_name in names(sheets)) {
    addWorksheet(workbook, sheet_name)
    if (nrow(sheets[[sheet_name]]) == 0) {
      writeData(workbook, sheet_name, sheets[[sheet_name]], colNames = TRUE)
    } else {
      writeDataTable(workbook, sheet_name, sheets[[sheet_name]], tableStyle = "TableStyleLight9")
    }
    setColWidths(workbook, sheet_name, cols = seq_along(sheets[[sheet_name]]), widths = "auto")
    freezePane(workbook, sheet_name, firstRow = TRUE)
  }

  saveWorkbook(workbook, report_path, overwrite = TRUE)
  invisible(report_path)
}

run_workflow <- function(options) {
  if (!is.null(options$slides_csv)) {
    selected_csv <- list(
      path = options$slides_csv,
      filename_date = extract_filename_date(options$slides_csv),
      selection_method = "cli_override"
    )
  } else {
    selected_csv <- select_latest_slides_csv("slides")
  }

  if (!file_exists(selected_csv$path)) {
    stop(sprintf("Slide CSV does not exist: %s", selected_csv$path), call. = FALSE)
  }
  if (identical(options$programme_source, "json") && !file_exists(options$programme_json)) {
    stop(sprintf("Programme JSON does not exist: %s", options$programme_json), call. = FALSE)
  }
  if (!file_exists(options$email_workbook)) {
    stop(sprintf("Email workbook does not exist: %s", options$email_workbook), call. = FALSE)
  }

  message(sprintf("Using slide CSV: %s", selected_csv$path))
  if (identical(options$programme_source, "json")) {
    message(sprintf("Using programme JSON: %s", options$programme_json))
  } else {
    message("Using programme source: current app state")
  }
  message(sprintf("Using email workbook: %s", options$email_workbook))
  message(sprintf("Writing slide outputs under: %s", options$output_dir))

  programme <- read_programme_papers(options$programme_source, options$programme_json)
  slides <- read_slide_submissions(selected_csv$path)
  email_lookup <- read_email_lookup(options$email_workbook)
  slide_status <- build_slide_status(programme, slides, email_lookup, options$output_dir)
  unmatched <- unmatched_slide_submissions(slides, programme, email_lookup)

  slide_status <- process_downloads(
    slide_status,
    no_download = options$no_download,
    overwrite_pdfs = options$overwrite_pdfs
  )

  summary <- summary_table(
    slide_status,
    unmatched,
    selected_csv,
    no_download = options$no_download,
    overwrite_pdfs = options$overwrite_pdfs,
    programme_source = options$programme_source,
    programme_json = options$programme_json
  )

  report_path <- fs::path(options$output_dir, "slide_report.xlsx")
  write_report(report_path, summary, slide_status, unmatched)

  message(sprintf("Wrote report: %s", report_path))
  message(sprintf(
    "Matched decks: %s / %s; missing decks: %s; unmatched submissions: %s; download failures: %s",
    sum(slide_status$status == "matched"),
    nrow(slide_status),
    sum(slide_status$status != "matched"),
    nrow(unmatched),
    sum(slide_status$download_status == "failed")
  ))

  invisible(list(
    selected_csv = selected_csv,
    programme = programme,
    slides = slides,
    slide_status = slide_status,
    unmatched_submissions = unmatched,
    summary = summary,
    report_path = report_path
  ))
}

main <- function(args = commandArgs(trailingOnly = TRUE)) {
  options <- parse_cli_args(args)
  if (options$help) {
    usage()
    return(invisible(0))
  }

  run_workflow(options)
  invisible(0)
}

if (sys.nframe() == 0) {
  main()
}
