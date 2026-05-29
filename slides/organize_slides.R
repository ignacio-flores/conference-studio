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
      "  --review-suggested-matches=BOOL",
      "                           Review likely fuzzy title matches in the terminal. Default: TRUE",
      "  --match-rules=PATH       Persistent manual match rules CSV. Default: slides/slide_match_rules.csv",
      "  --review-existing-rules=BOOL",
      "                           Review saved match rules before applying suggestions. Default: FALSE",
      "  --unmatched-decisions=PATH",
      "                           Persistent decisions for unmatched submissions. Default: slides/unmatched_submission_decisions.csv",
      "  --review-unmatched-submissions=BOOL",
      "                           Review leftover unmatched submissions in the terminal. Default: TRUE",
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
    review_suggested_matches = TRUE,
    match_rules = "slides/slide_match_rules.csv",
    review_existing_rules = FALSE,
    unmatched_decisions = "slides/unmatched_submission_decisions.csv",
    review_unmatched_submissions = TRUE,
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
    } else if (startsWith(arg, "--review-suggested-matches=")) {
      options$review_suggested_matches <- parse_bool(
        sub("^--review-suggested-matches=", "", arg),
        "--review-suggested-matches"
      )
    } else if (startsWith(arg, "--match-rules=")) {
      options$match_rules <- sub("^--match-rules=", "", arg)
    } else if (startsWith(arg, "--review-existing-rules=")) {
      options$review_existing_rules <- parse_bool(
        sub("^--review-existing-rules=", "", arg),
        "--review-existing-rules"
      )
    } else if (startsWith(arg, "--unmatched-decisions=")) {
      options$unmatched_decisions <- sub("^--unmatched-decisions=", "", arg)
    } else if (startsWith(arg, "--review-unmatched-submissions=")) {
      options$review_unmatched_submissions <- parse_bool(
        sub("^--review-unmatched-submissions=", "", arg),
        "--review-unmatched-submissions"
      )
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

normalize_name <- function(x) {
  x <- ascii_transliterate(x)
  x <- str_to_lower(x)
  x <- str_replace_all(x, "[^a-z0-9]+", " ")
  str_squish(x)
}

normalize_name_variants <- function(x) {
  x <- clean_text(x)
  parts <- str_split(x, "\\s+(?:&|and)\\s+|\\s*/\\s*|,")
  lapply(parts, function(values) {
    values <- values[clean_text(values) != ""]
    unique(normalize_name(values))
  })
}

normalized_name_matches <- function(left_norm, right_values) {
  left_norm <- clean_text(left_norm)
  right_values <- clean_text(right_values)
  if (length(right_values) == 1 && length(left_norm) > 1) {
    right_values <- rep(right_values, length(left_norm))
  }
  right_variants <- normalize_name_variants(right_values)
  vapply(seq_along(left_norm), function(i) {
    left_norm[[i]] != "" && left_norm[[i]] %in% right_variants[[i]]
  }, logical(1))
}

normalize_email <- function(x) {
  str_to_lower(clean_text(x))
}

edit_distance_ratio <- function(left, right) {
  left <- clean_text(left)
  right <- clean_text(right)
  vapply(seq_along(left), function(i) {
    left_value <- left[[i]]
    right_value <- right[[i]]
    max_len <- max(nchar(left_value), nchar(right_value))
    if (max_len == 0) {
      return(1)
    }
    distance <- utils::adist(left_value, right_value)[[1]]
    max(0, 1 - (distance / max_len))
  }, numeric(1))
}

match_rule_columns <- function() {
  c(
    "programme_submission_id",
    "submitted_title_norm",
    "decision",
    "active",
    "submitted_title",
    "programme_title",
    "submitter_name",
    "programme_presenter",
    "notes",
    "updated_at"
  )
}

empty_match_rules <- function() {
  tibble(
    programme_submission_id = character(),
    submitted_title_norm = character(),
    decision = character(),
    active = logical(),
    submitted_title = character(),
    programme_title = character(),
    submitter_name = character(),
    programme_presenter = character(),
    notes = character(),
    updated_at = character()
  )
}

parse_rule_active <- function(value) {
  normalized <- str_to_lower(str_trim(as.character(value)))
  case_when(
    is.na(value) | normalized == "" ~ TRUE,
    normalized %in% c("true", "t", "1", "yes", "y") ~ TRUE,
    normalized %in% c("false", "f", "0", "no", "n") ~ FALSE,
    TRUE ~ FALSE
  )
}

coerce_match_rules <- function(rules) {
  if (is.null(rules)) {
    return(empty_match_rules())
  }

  rules <- as_tibble(rules)
  for (column in match_rule_columns()) {
    if (!column %in% names(rules)) {
      rules[[column]] <- if (identical(column, "active")) TRUE else ""
    }
  }

  rules <- rules %>%
    transmute(
      programme_submission_id = clean_text(programme_submission_id),
      submitted_title_norm = ifelse(
        clean_text(submitted_title_norm) == "" & clean_text(submitted_title) != "",
        normalize_title(submitted_title),
        clean_text(submitted_title_norm)
      ),
      decision = str_to_lower(clean_text(decision)),
      active = parse_rule_active(active),
      submitted_title = clean_text(submitted_title),
      programme_title = clean_text(programme_title),
      submitter_name = clean_text(submitter_name),
      programme_presenter = clean_text(programme_presenter),
      notes = clean_text(notes),
      updated_at = clean_text(updated_at)
    ) %>%
    filter(
      programme_submission_id != "",
      submitted_title_norm != "",
      decision %in% c("accept", "reject")
    )

  if (nrow(rules) == 0) {
    return(empty_match_rules())
  }

  rules
}

read_match_rules <- function(path) {
  if (is.null(path) || clean_text(path) == "" || !file_exists(path)) {
    return(empty_match_rules())
  }

  rules <- read_csv(path, show_col_types = FALSE, col_types = cols(.default = col_character()))
  coerce_match_rules(rules)
}

write_match_rules <- function(path, rules) {
  rules <- coerce_match_rules(rules)
  dir_create(path_dir(path))
  write_csv(rules, path, na = "")
  invisible(path)
}

current_timestamp <- function() {
  format(Sys.time(), "%Y-%m-%dT%H:%M:%SZ", tz = "UTC")
}

upsert_match_rule <- function(
  rules,
  programme_submission_id,
  submitted_title_norm,
  decision,
  submitted_title = "",
  programme_title = "",
  submitter_name = "",
  programme_presenter = "",
  notes = "",
  active = TRUE,
  updated_at = current_timestamp()
) {
  rules <- coerce_match_rules(rules)
  programme_submission_id <- clean_text(programme_submission_id)
  submitted_title_norm <- clean_text(submitted_title_norm)
  decision <- str_to_lower(clean_text(decision))

  if (!decision %in% c("accept", "reject")) {
    stop("Rule decision must be accept or reject.", call. = FALSE)
  }
  if (programme_submission_id == "" || submitted_title_norm == "") {
    stop("Rules require programme_submission_id and submitted_title_norm.", call. = FALSE)
  }

  replacement <- tibble(
    programme_submission_id = programme_submission_id,
    submitted_title_norm = submitted_title_norm,
    decision = decision,
    active = isTRUE(active),
    submitted_title = clean_text(submitted_title),
    programme_title = clean_text(programme_title),
    submitter_name = clean_text(submitter_name),
    programme_presenter = clean_text(programme_presenter),
    notes = clean_text(notes),
    updated_at = clean_text(updated_at)
  )

  rules %>%
    filter(
      !(
        programme_submission_id == replacement$programme_submission_id[[1]] &
          submitted_title_norm == replacement$submitted_title_norm[[1]]
      )
    ) %>%
    bind_rows(replacement)
}

unmatched_decision_columns <- function() {
  c(
    "submitted_title_norm",
    "decision",
    "active",
    "submitted_title",
    "submitter_name",
    "submitter_email",
    "csv_submission_id",
    "slide_url",
    "notes",
    "updated_at"
  )
}

empty_unmatched_decisions <- function() {
  tibble(
    submitted_title_norm = character(),
    decision = character(),
    active = logical(),
    submitted_title = character(),
    submitter_name = character(),
    submitter_email = character(),
    csv_submission_id = character(),
    slide_url = character(),
    notes = character(),
    updated_at = character()
  )
}

coerce_unmatched_decisions <- function(decisions) {
  if (is.null(decisions)) {
    return(empty_unmatched_decisions())
  }

  decisions <- as_tibble(decisions)
  for (column in unmatched_decision_columns()) {
    if (!column %in% names(decisions)) {
      decisions[[column]] <- if (identical(column, "active")) TRUE else ""
    }
  }

  decisions <- decisions %>%
    transmute(
      submitted_title_norm = ifelse(
        clean_text(submitted_title_norm) == "" & clean_text(submitted_title) != "",
        normalize_title(submitted_title),
        clean_text(submitted_title_norm)
      ),
      decision = str_to_lower(clean_text(decision)),
      active = parse_rule_active(active),
      submitted_title = clean_text(submitted_title),
      submitter_name = clean_text(submitter_name),
      submitter_email = clean_text(submitter_email),
      csv_submission_id = clean_text(csv_submission_id),
      slide_url = clean_text(slide_url),
      notes = clean_text(notes),
      updated_at = clean_text(updated_at)
    ) %>%
    filter(
      submitted_title_norm != "",
      decision %in% c("exclude", "keep")
    )

  if (nrow(decisions) == 0) {
    return(empty_unmatched_decisions())
  }

  decisions
}

read_unmatched_decisions <- function(path) {
  if (is.null(path) || clean_text(path) == "" || !file_exists(path)) {
    return(empty_unmatched_decisions())
  }

  decisions <- read_csv(path, show_col_types = FALSE, col_types = cols(.default = col_character()))
  coerce_unmatched_decisions(decisions)
}

write_unmatched_decisions <- function(path, decisions) {
  decisions <- coerce_unmatched_decisions(decisions)
  dir_create(path_dir(path))
  write_csv(decisions, path, na = "")
  invisible(path)
}

upsert_unmatched_decision <- function(
  decisions,
  submitted_title_norm,
  decision,
  submitted_title = "",
  submitter_name = "",
  submitter_email = "",
  csv_submission_id = "",
  slide_url = "",
  notes = "",
  active = TRUE,
  updated_at = current_timestamp()
) {
  decisions <- coerce_unmatched_decisions(decisions)
  submitted_title_norm <- clean_text(submitted_title_norm)
  decision <- str_to_lower(clean_text(decision))

  if (!decision %in% c("exclude", "keep")) {
    stop("Unmatched decision must be exclude or keep.", call. = FALSE)
  }
  if (submitted_title_norm == "") {
    stop("Unmatched decisions require submitted_title_norm.", call. = FALSE)
  }

  replacement <- tibble(
    submitted_title_norm = submitted_title_norm,
    decision = decision,
    active = isTRUE(active),
    submitted_title = clean_text(submitted_title),
    submitter_name = clean_text(submitter_name),
    submitter_email = clean_text(submitter_email),
    csv_submission_id = clean_text(csv_submission_id),
    slide_url = clean_text(slide_url),
    notes = clean_text(notes),
    updated_at = clean_text(updated_at)
  )

  decisions %>%
    filter(submitted_title_norm != replacement$submitted_title_norm[[1]]) %>%
    bind_rows(replacement)
}

latest_unmatched_decisions <- function(decisions) {
  coerce_unmatched_decisions(decisions) %>%
    arrange(submitted_title_norm, desc(updated_at)) %>%
    group_by(submitted_title_norm) %>%
    slice(1) %>%
    ungroup()
}

unmatched_decision_state <- function(decisions) {
  latest_unmatched_decisions(decisions) %>%
    filter(active) %>%
    transmute(
      submitted_title_norm,
      unmatched_decision = decision,
      unmatched_decision_notes = notes,
      unmatched_decision_updated_at = updated_at
    )
}

sanitize_path_component <- function(x, fallback = "unnamed") {
  x <- ascii_transliterate(x)
  x <- str_replace_all(x, "[\"']", "")
  x <- str_replace_all(x, "[^A-Za-z0-9._-]+", "-")
  x <- str_replace_all(x, "-+", "-")
  x <- str_replace_all(x, "^[._-]+|[._-]+$", "")
  x <- ifelse(x == "", fallback, x)
  x
}

strip_presenter_role_labels <- function(presenter_display) {
  presenter_display <- clean_text(presenter_display)
  presenter_display <- str_replace_all(
    presenter_display,
    regex("\\s*\\((?:chair|moderator|session chair)\\)\\s*$", ignore_case = TRUE),
    ""
  )
  presenter_display <- str_replace_all(
    presenter_display,
    regex("\\s*[-:\\u2013\\u2014]+\\s*(?:chair|moderator|session chair)\\s*$", ignore_case = TRUE),
    ""
  )
  presenter_display <- str_replace_all(
    presenter_display,
    regex("^\\s*(?:chair|moderator|session chair)\\s*[-:\\u2013\\u2014]+\\s*", ignore_case = TRUE),
    ""
  )
  str_squish(presenter_display)
}

is_role_only_presenter_label <- function(presenter_display) {
  normalize_name(presenter_display) %in% c("chair", "moderator", "session chair")
}

presenter_name_for_filename <- function(presenter_display, authors = "") {
  display_name <- strip_presenter_role_labels(presenter_display)
  author_name <- clean_text(authors)
  ifelse(
    is_role_only_presenter_label(display_name) & author_name != "",
    author_name,
    ifelse(
      display_name != "",
      display_name,
      ifelse(author_name != "", author_name, clean_text(presenter_display))
    )
  )
}

presenter_last_name <- function(presenter_display, authors = "") {
  presenter_display <- presenter_name_for_filename(presenter_display, authors)
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

build_slide_filename <- function(talk_index, presenter_display, authors = "") {
  talk_index <- suppressWarnings(as.integer(talk_index))
  prefix <- ifelse(is.na(talk_index), "00", sprintf("%02d", talk_index))
  paste0(prefix, "_", presenter_last_name(presenter_display, authors), ".pdf")
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
  if (!"authors" %in% names(papers)) {
    papers$authors <- ""
  }

  papers %>%
    transmute(
      submission_id = clean_text(submission_id),
      title = clean_text(title),
      authors = clean_text(authors),
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

latest_rule_per_key <- function(rules) {
  coerce_match_rules(rules) %>%
    arrange(programme_submission_id, submitted_title_norm, desc(updated_at)) %>%
    group_by(programme_submission_id, submitted_title_norm) %>%
    slice(1) %>%
    ungroup()
}

active_accepted_rules <- function(rules) {
  latest_rule_per_key(rules) %>%
    filter(active, decision == "accept") %>%
    arrange(submitted_title_norm, desc(updated_at)) %>%
    group_by(submitted_title_norm) %>%
    slice(1) %>%
    ungroup()
}

resolve_standard_slide_matches <- function(programme, slides, email_lookup) {
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
      submitted_title_norm = title_norm,
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
      submitted_title_norm = workbook_title_norm,
      slide_url,
      match_method = "workbook_title_submission_id"
    )

  bind_rows(direct_matches, workbook_matches) %>%
    arrange(submission_id, match_method, desc(slide_submitted_at)) %>%
    group_by(submission_id) %>%
    slice(1) %>%
    ungroup()
}

resolve_manual_rule_matches <- function(programme, slides, rules, existing_matches = NULL) {
  accepted_rules <- active_accepted_rules(rules)
  if (nrow(accepted_rules) == 0) {
    return(tibble(
      submission_id = character(),
      csv_submission_id = character(),
      slide_submitted_at = as.POSIXct(character()),
      submitter_name = character(),
      slides_csv_email = character(),
      submitted_title = character(),
      submitted_title_norm = character(),
      slide_url = character(),
      match_method = character()
    ))
  }

  if (is.null(existing_matches)) {
    existing_matches <- tibble(submission_id = character(), submitted_title_norm = character())
  }

  slides_for_match <- latest_submission_per_title(slides)
  matched_submission_ids <- clean_text(existing_matches$submission_id)
  matched_title_norms <- clean_text(existing_matches$submitted_title_norm)

  accepted_rules %>%
    select(programme_submission_id, submitted_title_norm, updated_at) %>%
    inner_join(
      slides_for_match %>%
        select(
          submitted_title_norm = title_norm,
          csv_submission_id,
          slide_submitted_at,
          submitter_name,
          slides_csv_email,
          submitted_title,
          slide_url
        ),
      by = "submitted_title_norm"
    ) %>%
    inner_join(
      programme %>% select(submission_id, programme_title = title),
      by = c("programme_submission_id" = "submission_id")
    ) %>%
    filter(
      !(programme_submission_id %in% matched_submission_ids),
      !(submitted_title_norm %in% matched_title_norms)
    ) %>%
    arrange(desc(updated_at), desc(slide_submitted_at)) %>%
    transmute(
      submission_id = programme_submission_id,
      csv_submission_id,
      slide_submitted_at,
      submitter_name,
      slides_csv_email,
      submitted_title,
      submitted_title_norm,
      slide_url,
      match_method = "manual_rule"
    ) %>%
    group_by(submission_id) %>%
    slice(1) %>%
    ungroup()
}

resolve_slide_matches <- function(programme, slides, email_lookup, match_rules = NULL) {
  standard_matches <- resolve_standard_slide_matches(programme, slides, email_lookup)
  manual_matches <- resolve_manual_rule_matches(programme, slides, match_rules, standard_matches)

  bind_rows(standard_matches, manual_matches) %>%
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

build_slide_status <- function(programme, slides, email_lookup, output_dir, match_rules = NULL) {
  if (!"authors" %in% names(programme)) {
    programme$authors <- ""
  }
  slide_matches <- resolve_slide_matches(programme, slides, email_lookup, match_rules)

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
    build_slide_filename(status$talk_index, status$presenter_display, status$authors)
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

unmatched_slide_submissions <- function(
  slides,
  programme,
  email_lookup = NULL,
  match_rules = NULL,
  slide_matches = NULL,
  unmatched_decisions = NULL
) {
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

  if (is.null(slide_matches) && !is.null(email_lookup)) {
    slide_matches <- resolve_slide_matches(programme, slides, email_lookup, match_rules)
  }
  if (!is.null(slide_matches) && "submitted_title_norm" %in% names(slide_matches)) {
    matched_title_norms <- unique(c(matched_title_norms, slide_matches$submitted_title_norm))
  }

  decision_state <- unmatched_decision_state(unmatched_decisions)

  slides %>%
    filter(title_norm != "", !(title_norm %in% matched_title_norms)) %>%
    transmute(
      submitter_name,
      submitter_email = slides_csv_email,
      submitted_title,
      submitted_title_norm = title_norm,
      slide_url,
      csv_submission_id,
      slide_submitted_at
    ) %>%
    left_join(decision_state, by = "submitted_title_norm") %>%
    mutate(
      unmatched_decision = ifelse(is.na(unmatched_decision), "", unmatched_decision),
      unmatched_decision_notes = ifelse(is.na(unmatched_decision_notes), "", unmatched_decision_notes),
      unmatched_decision_updated_at = ifelse(is.na(unmatched_decision_updated_at), "", unmatched_decision_updated_at)
    ) %>%
    filter(unmatched_decision != "exclude") %>%
    arrange(submitted_title, desc(slide_submitted_at))
}

ensure_email_lookup_columns <- function(email_lookup) {
  email_lookup <- as_tibble(email_lookup)
  defaults <- list(
    workbook_email = "",
    workbook_title = "",
    workbook_title_norm = normalize_title(""),
    workbook_full_name = "",
    workbook_sheet = ""
  )
  for (column in names(defaults)) {
    if (!column %in% names(email_lookup)) {
      email_lookup[[column]] <- defaults[[column]]
    }
  }
  email_lookup
}

empty_suggested_matches <- function() {
  tibble(
    submitter_name = character(),
    submitter_email = character(),
    submitted_title = character(),
    submitted_title_norm = character(),
    csv_submission_id = character(),
    slide_submitted_at = as.POSIXct(character()),
    slide_url = character(),
    programme_submission_id = character(),
    programme_title = character(),
    programme_presenter = character(),
    room = character(),
    day = character(),
    session = character(),
    time = character(),
    title_similarity = numeric(),
    email_match = logical(),
    name_match = logical(),
    name_match_source = character(),
    match_reason = character(),
    rule_decision = character(),
    rule_active = logical(),
    rule_notes = character(),
    rule_updated_at = character()
  )
}

rule_state_for_suggestions <- function(rules) {
  latest_rule_per_key(rules) %>%
    transmute(
      programme_submission_id,
      submitted_title_norm,
      rule_decision = decision,
      rule_active = active,
      rule_notes = notes,
      rule_updated_at = updated_at
    )
}

exact_or_workbook_title_norms <- function(programme, email_lookup) {
  email_lookup <- ensure_email_lookup_columns(email_lookup)
  unique(c(
    programme$title_norm,
    email_lookup %>%
      filter(submission_id %in% programme$submission_id) %>%
      pull(workbook_title_norm)
  ))
}

generate_suggested_matches <- function(
  programme,
  slides,
  email_lookup,
  match_rules = NULL,
  unmatched_decisions = NULL,
  existing_matches = NULL,
  max_suggestions = 3
) {
  if (!"authors" %in% names(programme)) {
    programme$authors <- ""
  }
  email_lookup <- ensure_email_lookup_columns(email_lookup)
  rules <- coerce_match_rules(match_rules)
  decision_state <- unmatched_decision_state(unmatched_decisions)
  if (is.null(existing_matches)) {
    existing_matches <- resolve_slide_matches(programme, slides, email_lookup, rules)
  }

  matched_title_norms <- exact_or_workbook_title_norms(programme, email_lookup)
  if ("submitted_title_norm" %in% names(existing_matches)) {
    matched_title_norms <- unique(c(matched_title_norms, existing_matches$submitted_title_norm))
  }
  decided_title_norms <- unique(decision_state$submitted_title_norm)

  unmatched_slides <- latest_submission_per_title(slides) %>%
    filter(
      title_norm != "",
      !(title_norm %in% matched_title_norms),
      !(title_norm %in% decided_title_norms)
    ) %>%
    transmute(
      join_key = 1L,
      submitter_name,
      submitter_name_norm = normalize_name(submitter_name),
      submitter_email = slides_csv_email,
      submitter_email_norm = normalize_email(slides_csv_email),
      submitted_title,
      submitted_title_norm = title_norm,
      csv_submission_id,
      slide_submitted_at,
      slide_url
    )

  candidate_programme <- programme %>%
    anti_join(existing_matches %>% select(submission_id), by = "submission_id") %>%
    left_join(email_lookup, by = "submission_id") %>%
    transmute(
      join_key = 1L,
      programme_submission_id = submission_id,
      programme_title = title,
      programme_title_norm = title_norm,
      programme_presenter = presenter_display,
      programme_authors = authors,
      programme_presenter_for_match = strip_presenter_role_labels(presenter_display),
      workbook_full_name,
      workbook_email,
      workbook_email_norm = normalize_email(workbook_email),
      room,
      day = day_label,
      session = session_title,
      time
    )

  if (nrow(unmatched_slides) == 0 || nrow(candidate_programme) == 0) {
    return(empty_suggested_matches())
  }

  suggestions <- unmatched_slides %>%
    inner_join(candidate_programme, by = "join_key", relationship = "many-to-many") %>%
    mutate(
      title_similarity = edit_distance_ratio(submitted_title_norm, programme_title_norm),
      email_match = submitter_email_norm != "" &
        workbook_email_norm != "" &
        submitter_email_norm == workbook_email_norm,
      author_name_match = normalized_name_matches(submitter_name_norm, programme_authors),
      presenter_name_match = normalized_name_matches(submitter_name_norm, programme_presenter_for_match),
      workbook_name_match = normalized_name_matches(submitter_name_norm, workbook_full_name),
      name_match = author_name_match | presenter_name_match | workbook_name_match,
      name_match_source = case_when(
        author_name_match ~ "authors",
        presenter_name_match ~ "presenter_display",
        workbook_name_match ~ "workbook_full_name",
        TRUE ~ ""
      ),
      match_reason = case_when(
        name_match ~ "author_name",
        email_match & title_similarity >= 0.70 ~ "email_title",
        title_similarity >= 0.92 ~ "title_similarity",
        TRUE ~ ""
      )
    ) %>%
    filter(
      name_match |
        (email_match & title_similarity >= 0.70) |
        title_similarity >= 0.92
    ) %>%
    left_join(
      rule_state_for_suggestions(rules),
      by = c("programme_submission_id", "submitted_title_norm")
    ) %>%
    filter(!(rule_active %in% TRUE & rule_decision == "reject")) %>%
    arrange(
      submitted_title_norm,
      desc(name_match),
      desc(email_match),
      desc(title_similarity),
      programme_submission_id
    ) %>%
    group_by(submitted_title_norm) %>%
    slice_head(n = max_suggestions) %>%
    ungroup() %>%
    transmute(
      submitter_name,
      submitter_email,
      submitted_title,
      submitted_title_norm,
      csv_submission_id,
      slide_submitted_at,
      slide_url,
      programme_submission_id,
      programme_title,
      programme_presenter,
      room,
      day,
      session,
      time,
      title_similarity,
      email_match,
      name_match,
      name_match_source,
      match_reason,
      rule_decision = ifelse(is.na(rule_decision), "", rule_decision),
      rule_active = ifelse(is.na(rule_active), FALSE, rule_active),
      rule_notes = ifelse(is.na(rule_notes), "", rule_notes),
      rule_updated_at = ifelse(is.na(rule_updated_at), "", rule_updated_at)
    )

  if (nrow(suggestions) == 0) {
    return(empty_suggested_matches())
  }

  suggestions
}

can_prompt_in_terminal <- function() {
  isTRUE(isatty(stdin()))
}

terminal_input <- function(prompt = "") {
  cat(prompt)
  flush.console()
  response <- readLines("stdin", n = 1, warn = FALSE)
  if (length(response) == 0) {
    return("")
  }
  response[[1]]
}

write_review_line <- function(output_fn, text = "") {
  output_fn(paste0(text, "\n"))
}

format_match_evidence <- function(suggestion) {
  name_source <- if ("name_match_source" %in% names(suggestion)) {
    clean_text(suggestion$name_match_source)
  } else {
    ""
  }
  match_reason <- if ("match_reason" %in% names(suggestion)) {
    clean_text(suggestion$match_reason)
  } else {
    ""
  }
  name_detail <- ifelse(name_source == "", "", sprintf(" via %s", name_source))
  reason_detail <- ifelse(match_reason == "", "", sprintf("reason %s; ", match_reason))
  sprintf(
    "evidence: %stitle similarity %.2f; email match %s; name match %s%s",
    reason_detail,
    suggestion$title_similarity,
    ifelse(isTRUE(suggestion$email_match), "yes", "no"),
    ifelse(isTRUE(suggestion$name_match), "yes", "no"),
    name_detail
  )
}

review_suggested_matches <- function(
  suggestions,
  rules = NULL,
  programme = NULL,
  input_fn = terminal_input,
  output_fn = cat,
  now_fn = current_timestamp
) {
  rules <- coerce_match_rules(rules)
  suggestions <- as_tibble(suggestions)
  if (nrow(suggestions) == 0) {
    return(list(rules = rules, changed = FALSE, quit = FALSE))
  }

  changed <- FALSE
  quit <- FALSE
  grouped <- split(suggestions, suggestions$submitted_title_norm)
  programme_lookup <- NULL
  if (!is.null(programme)) {
    programme_lookup <- as_tibble(programme) %>%
      transmute(
        programme_submission_id = clean_text(submission_id),
        programme_title = clean_text(title),
        programme_presenter = clean_text(presenter_display)
      )
  }

  for (slide_suggestions in grouped) {
    slide <- slide_suggestions[1, ]
    write_review_line(output_fn)
    write_review_line(output_fn, "Slide submission")
    write_review_line(output_fn, sprintf("  submitter: %s <%s>", slide$submitter_name, slide$submitter_email))
    write_review_line(output_fn, sprintf("  title: %s", slide$submitted_title))
    write_review_line(output_fn, sprintf("  csv submission id: %s", slide$csv_submission_id))

    for (i in seq_len(nrow(slide_suggestions))) {
      suggestion <- slide_suggestions[i, ]
      write_review_line(output_fn)
      write_review_line(
        output_fn,
        sprintf("Suggested programme match %s/%s", i, nrow(slide_suggestions))
      )
      write_review_line(
        output_fn,
        sprintf("  %s | %s", suggestion$programme_submission_id, suggestion$programme_presenter)
      )
      write_review_line(output_fn, sprintf("  %s", suggestion$programme_title))
      write_review_line(
        output_fn,
        sprintf("  %s | %s | %s | %s", suggestion$day, suggestion$time, suggestion$room, suggestion$session)
      )
      write_review_line(output_fn, sprintf("  %s", format_match_evidence(suggestion)))

      repeat {
        answer <- str_to_lower(str_trim(input_fn("Accept/reject/skip/edit/quit? [a/r/s/e/q]: ")))
        if (answer == "") {
          answer <- "s"
        }

        if (answer == "a") {
          rules <- upsert_match_rule(
            rules,
            programme_submission_id = suggestion$programme_submission_id,
            submitted_title_norm = suggestion$submitted_title_norm,
            decision = "accept",
            submitted_title = suggestion$submitted_title,
            programme_title = suggestion$programme_title,
            submitter_name = suggestion$submitter_name,
            programme_presenter = suggestion$programme_presenter,
            updated_at = now_fn()
          )
          changed <- TRUE
          break
        }

        if (answer == "r") {
          rules <- upsert_match_rule(
            rules,
            programme_submission_id = suggestion$programme_submission_id,
            submitted_title_norm = suggestion$submitted_title_norm,
            decision = "reject",
            submitted_title = suggestion$submitted_title,
            programme_title = suggestion$programme_title,
            submitter_name = suggestion$submitter_name,
            programme_presenter = suggestion$programme_presenter,
            updated_at = now_fn()
          )
          changed <- TRUE
          break
        }

        if (answer == "s") {
          break
        }

        if (answer == "e") {
          programme_submission_id <- clean_text(input_fn("Programme submission ID: "))
          if (programme_submission_id == "") {
            write_review_line(output_fn, "  No ID entered; skipped.")
            break
          }
          programme_title <- ""
          programme_presenter <- ""
          if (!is.null(programme_lookup)) {
            entered_programme <- programme_lookup %>%
              filter(programme_submission_id == !!programme_submission_id) %>%
              slice(1)
            if (nrow(entered_programme) == 0) {
              write_review_line(output_fn, sprintf("  Programme submission ID not found: %s", programme_submission_id))
              next
            }
            programme_title <- entered_programme$programme_title[[1]]
            programme_presenter <- entered_programme$programme_presenter[[1]]
          }
          rules <- upsert_match_rule(
            rules,
            programme_submission_id = programme_submission_id,
            submitted_title_norm = suggestion$submitted_title_norm,
            decision = "accept",
            submitted_title = suggestion$submitted_title,
            programme_title = programme_title,
            submitter_name = suggestion$submitter_name,
            programme_presenter = programme_presenter,
            notes = "manual programme_submission_id entered during review",
            updated_at = now_fn()
          )
          changed <- TRUE
          break
        }

        if (answer == "q") {
          quit <- TRUE
          break
        }

        write_review_line(output_fn, "  Enter a, r, s, e, or q.")
      }

      if (answer %in% c("a", "s", "e") || quit) {
        break
      }
    }

    if (quit) {
      break
    }
  }

  list(rules = coerce_match_rules(rules), changed = changed, quit = quit)
}

review_unmatched_submissions <- function(
  unmatched_submissions,
  decisions = NULL,
  rules = NULL,
  programme = NULL,
  input_fn = terminal_input,
  output_fn = cat,
  now_fn = current_timestamp
) {
  decisions <- coerce_unmatched_decisions(decisions)
  rules <- coerce_match_rules(rules)
  unmatched_submissions <- as_tibble(unmatched_submissions)
  if (nrow(unmatched_submissions) == 0) {
    return(list(
      decisions = decisions,
      rules = rules,
      decisions_changed = FALSE,
      rules_changed = FALSE,
      changed = FALSE,
      quit = FALSE
    ))
  }

  if (!"submitted_title_norm" %in% names(unmatched_submissions)) {
    unmatched_submissions$submitted_title_norm <- normalize_title(unmatched_submissions$submitted_title)
  }
  if (!"unmatched_decision" %in% names(unmatched_submissions)) {
    unmatched_submissions$unmatched_decision <- ""
  }

  review_rows <- unmatched_submissions %>%
    filter(unmatched_decision == "") %>%
    arrange(submitted_title, desc(slide_submitted_at)) %>%
    group_by(submitted_title_norm) %>%
    slice(1) %>%
    ungroup()

  if (nrow(review_rows) == 0) {
    return(list(
      decisions = decisions,
      rules = rules,
      decisions_changed = FALSE,
      rules_changed = FALSE,
      changed = FALSE,
      quit = FALSE
    ))
  }

  programme_lookup <- NULL
  if (!is.null(programme)) {
    programme_lookup <- as_tibble(programme) %>%
      transmute(
        programme_submission_id = clean_text(submission_id),
        programme_title = clean_text(title),
        programme_presenter = clean_text(presenter_display)
      )
  }

  decisions_changed <- FALSE
  rules_changed <- FALSE
  quit <- FALSE
  for (row_index in seq_len(nrow(review_rows))) {
    submission <- review_rows[row_index, ]
    write_review_line(output_fn)
    write_review_line(output_fn, sprintf("Unmatched slide submission %s/%s", row_index, nrow(review_rows)))
    write_review_line(output_fn, sprintf("  submitter: %s <%s>", submission$submitter_name, submission$submitter_email))
    write_review_line(output_fn, sprintf("  title: %s", submission$submitted_title))
    write_review_line(output_fn, sprintf("  csv submission id: %s", submission$csv_submission_id))

    repeat {
      answer <- str_to_lower(str_trim(input_fn("Exclude/keep/manual/skip/quit? [e/k/m/s/q]: ")))
      if (answer == "") {
        answer <- "s"
      }

      if (answer == "e") {
        decisions <- upsert_unmatched_decision(
          decisions,
          submitted_title_norm = submission$submitted_title_norm,
          decision = "exclude",
          submitted_title = submission$submitted_title,
          submitter_name = submission$submitter_name,
          submitter_email = submission$submitter_email,
          csv_submission_id = submission$csv_submission_id,
          slide_url = submission$slide_url,
          updated_at = now_fn()
        )
        decisions_changed <- TRUE
        break
      }

      if (answer == "k") {
        decisions <- upsert_unmatched_decision(
          decisions,
          submitted_title_norm = submission$submitted_title_norm,
          decision = "keep",
          submitted_title = submission$submitted_title,
          submitter_name = submission$submitter_name,
          submitter_email = submission$submitter_email,
          csv_submission_id = submission$csv_submission_id,
          slide_url = submission$slide_url,
          updated_at = now_fn()
        )
        decisions_changed <- TRUE
        break
      }

      if (answer == "m") {
        programme_submission_id <- clean_text(input_fn("Programme submission ID: "))
        if (programme_submission_id == "") {
          write_review_line(output_fn, "  No ID entered; skipped.")
          break
        }
        programme_title <- ""
        programme_presenter <- ""
        if (!is.null(programme_lookup)) {
          entered_programme <- programme_lookup %>%
            filter(programme_submission_id == !!programme_submission_id) %>%
            slice(1)
          if (nrow(entered_programme) == 0) {
            write_review_line(output_fn, sprintf("  Programme submission ID not found: %s", programme_submission_id))
            next
          }
          programme_title <- entered_programme$programme_title[[1]]
          programme_presenter <- entered_programme$programme_presenter[[1]]
        }
        rules <- upsert_match_rule(
          rules,
          programme_submission_id = programme_submission_id,
          submitted_title_norm = submission$submitted_title_norm,
          decision = "accept",
          submitted_title = submission$submitted_title,
          programme_title = programme_title,
          submitter_name = submission$submitter_name,
          programme_presenter = programme_presenter,
          notes = "manual programme_submission_id entered during unmatched review",
          updated_at = now_fn()
        )
        rules_changed <- TRUE
        break
      }

      if (answer == "s") {
        break
      }

      if (answer == "q") {
        quit <- TRUE
        break
      }

      write_review_line(output_fn, "  Enter e, k, m, s, or q.")
    }

    if (quit) {
      break
    }
  }

  list(
    decisions = coerce_unmatched_decisions(decisions),
    rules = coerce_match_rules(rules),
    decisions_changed = decisions_changed,
    rules_changed = rules_changed,
    changed = decisions_changed || rules_changed,
    quit = quit
  )
}

review_existing_match_rules <- function(
  rules,
  input_fn = terminal_input,
  output_fn = cat,
  now_fn = current_timestamp
) {
  rules <- latest_rule_per_key(rules)
  if (nrow(rules) == 0) {
    write_review_line(output_fn, "No saved match rules to review.")
    return(list(rules = rules, changed = FALSE, quit = FALSE))
  }

  changed <- FALSE
  quit <- FALSE
  for (row_index in seq_len(nrow(rules))) {
    rule <- rules[row_index, ]
    write_review_line(output_fn)
    write_review_line(
      output_fn,
      sprintf(
        "Rule %s/%s: %s %s for %s",
        row_index,
        nrow(rules),
        ifelse(rule$active, "active", "inactive"),
        rule$decision,
        rule$programme_submission_id
      )
    )
    write_review_line(output_fn, sprintf("  slide title: %s", rule$submitted_title))
    write_review_line(output_fn, sprintf("  programme title: %s", rule$programme_title))

    repeat {
      answer <- str_to_lower(str_trim(input_fn("Keep/deactivate/accept/reject/edit/quit? [k/d/a/r/e/q]: ")))
      if (answer == "") {
        answer <- "k"
      }
      if (answer == "k") {
        break
      }
      if (answer %in% c("d", "a", "r", "e")) {
        if (answer == "d") {
          rules$active[[row_index]] <- FALSE
        } else if (answer == "a") {
          rules$decision[[row_index]] <- "accept"
          rules$active[[row_index]] <- TRUE
        } else if (answer == "r") {
          rules$decision[[row_index]] <- "reject"
          rules$active[[row_index]] <- TRUE
        } else if (answer == "e") {
          new_id <- clean_text(input_fn("Programme submission ID: "))
          if (new_id != "") {
            rules$programme_submission_id[[row_index]] <- new_id
            rules$active[[row_index]] <- TRUE
          }
        }
        rules$updated_at[[row_index]] <- now_fn()
        changed <- TRUE
        break
      }
      if (answer == "q") {
        quit <- TRUE
        break
      }
      write_review_line(output_fn, "  Enter k, d, a, r, e, or q.")
    }
    if (quit) {
      break
    }
  }

  list(rules = coerce_match_rules(rules), changed = changed, quit = quit)
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

write_report <- function(
  report_path,
  summary,
  slide_status,
  unmatched_submissions,
  suggested_matches = empty_suggested_matches(),
  unmatched_decisions = empty_unmatched_decisions()
) {
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
    unmatched_decisions = latest_unmatched_decisions(unmatched_decisions),
    suggested_matches = suggested_matches,
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
  message(sprintf("Using slide match rules: %s", options$match_rules))
  message(sprintf("Using unmatched-submission decisions: %s", options$unmatched_decisions))

  programme <- read_programme_papers(options$programme_source, options$programme_json)
  slides <- read_slide_submissions(selected_csv$path)
  email_lookup <- read_email_lookup(options$email_workbook)
  match_rules <- read_match_rules(options$match_rules)
  unmatched_decisions <- read_unmatched_decisions(options$unmatched_decisions)

  if (options$review_existing_rules) {
    if (can_prompt_in_terminal()) {
      review_result <- review_existing_match_rules(match_rules)
      match_rules <- review_result$rules
      if (review_result$changed) {
        write_match_rules(options$match_rules, match_rules)
      }
    } else {
      message("Skipping existing-rule review because stdin is not a terminal.")
    }
  }

  slide_matches <- resolve_slide_matches(programme, slides, email_lookup, match_rules)
  suggested_matches <- generate_suggested_matches(
    programme,
    slides,
    email_lookup,
    match_rules,
    unmatched_decisions,
    existing_matches = slide_matches
  )

  if (options$review_suggested_matches && nrow(suggested_matches) > 0) {
    if (can_prompt_in_terminal()) {
      review_result <- review_suggested_matches(suggested_matches, match_rules, programme = programme)
      match_rules <- review_result$rules
      if (review_result$changed) {
        write_match_rules(options$match_rules, match_rules)
        slide_matches <- resolve_slide_matches(programme, slides, email_lookup, match_rules)
        suggested_matches <- generate_suggested_matches(
          programme,
          slides,
          email_lookup,
          match_rules,
          unmatched_decisions,
          existing_matches = slide_matches
        )
      }
    } else {
      message(sprintf(
        "Found %s suggested fuzzy match(es); skipping terminal review because stdin is not a terminal.",
        nrow(suggested_matches)
      ))
    }
  }

  unmatched <- unmatched_slide_submissions(
    slides,
    programme,
    email_lookup,
    match_rules,
    slide_matches = slide_matches,
    unmatched_decisions = unmatched_decisions
  )

  if (options$review_unmatched_submissions && nrow(unmatched %>% filter(unmatched_decision == "")) > 0) {
    if (can_prompt_in_terminal()) {
      review_result <- review_unmatched_submissions(
        unmatched,
        decisions = unmatched_decisions,
        rules = match_rules,
        programme = programme
      )
      unmatched_decisions <- review_result$decisions
      match_rules <- review_result$rules
      if (review_result$decisions_changed) {
        write_unmatched_decisions(options$unmatched_decisions, unmatched_decisions)
      }
      if (review_result$rules_changed) {
        write_match_rules(options$match_rules, match_rules)
        slide_matches <- resolve_slide_matches(programme, slides, email_lookup, match_rules)
      }
      if (review_result$changed) {
        suggested_matches <- generate_suggested_matches(
          programme,
          slides,
          email_lookup,
          match_rules,
          unmatched_decisions,
          existing_matches = slide_matches
        )
        unmatched <- unmatched_slide_submissions(
          slides,
          programme,
          email_lookup,
          match_rules,
          slide_matches = slide_matches,
          unmatched_decisions = unmatched_decisions
        )
      }
    } else {
      message(sprintf(
        "Found %s undecided unmatched submission(s); skipping terminal review because stdin is not a terminal.",
        nrow(unmatched %>% filter(unmatched_decision == ""))
      ))
    }
  }

  slide_status <- build_slide_status(programme, slides, email_lookup, options$output_dir, match_rules)

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
  write_report(report_path, summary, slide_status, unmatched, suggested_matches, unmatched_decisions)

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
    suggested_matches = suggested_matches,
    match_rules = match_rules,
    unmatched_decisions = unmatched_decisions,
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
