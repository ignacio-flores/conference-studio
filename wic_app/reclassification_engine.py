from __future__ import annotations

import csv
import copy
import re
import shutil
import uuid
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from engine.classification import classify_papers as classify_papers_core
from engine.config import ConferenceConfig, load_conference_config, resolve_config_path
from engine.scheduling import apply_paper_placements as apply_paper_placements_core
from engine.scheduling import apply_programme_layout_overrides as apply_programme_layout_overrides_core
from engine.scheduling import build_equal_time_ranges
from engine.validation import validate_programme_state as validate_programme_state_core

NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

APP_DIR = Path(__file__).resolve().parent
BASE_DIR = APP_DIR.parent
SOURCE_DIR = BASE_DIR / "source_data"
STATE_DIR = APP_DIR / "state"
EXPORT_DIR = BASE_DIR / "exports"

ACTIVE_CONFERENCE_CONFIG = load_conference_config()

SUBMISSIONS_FILE = SOURCE_DIR / ACTIVE_CONFERENCE_CONFIG.files.get("submissions", "WIC 2026 - Submissions (Reviewed).xlsx")
PROGRAMME_FILE = SOURCE_DIR / ACTIVE_CONFERENCE_CONFIG.files.get("programme", "WIC2026_Programme.xlsx")

CLASSIFICATION_OVERRIDES_FILE = STATE_DIR / "classification_overrides.csv"
SESSION_NAME_OVERRIDES_FILE = STATE_DIR / "session_name_overrides.csv"
PROGRAMME_LAYOUT_OVERRIDES_FILE = STATE_DIR / "programme_layout_overrides.csv"
SESSION_STRUCTURE_FILE = STATE_DIR / "session_structure.csv"
PAPER_PLACEMENTS_FILE = STATE_DIR / "paper_placements.csv"
PAPER_METADATA_OVERRIDES_FILE = STATE_DIR / "paper_metadata_overrides.csv"
PAPER_ARCHIVE_OVERRIDES_FILE = STATE_DIR / "paper_archive_overrides.csv"
MANUAL_TALKS_FILE = STATE_DIR / "manual_talks.csv"
LABEL_CATALOG_FILE = STATE_DIR / "label_catalog.csv"
EMPTY_LABEL_SENTINEL = "__WIC_EMPTY_LABEL__"

DRAFT_OUTPUT_FILE = EXPORT_DIR / ACTIVE_CONFERENCE_CONFIG.files.get("draft_output", "WIC2026_Programme_Draft.xlsx")
PUBLISH_XLSX_FILE = EXPORT_DIR / ACTIVE_CONFERENCE_CONFIG.files.get("publish_xlsx_output", "WIC2026_Programme_Publish.xlsx")
PUBLISH_PDF_FILE = EXPORT_DIR / ACTIVE_CONFERENCE_CONFIG.files.get("publish_pdf_output", "WIC2026_Programme_Publish.pdf")
PUBLISH_DOCX_FILE = EXPORT_DIR / ACTIVE_CONFERENCE_CONFIG.files.get("publish_docx_output", "WIC2026_Programme_Publish.docx")

DAY_ORDER = list(ACTIVE_CONFERENCE_CONFIG.days)
DAY_TO_NUM = ACTIVE_CONFERENCE_CONFIG.day_to_num

ROOM_PRIORITY = dict(ACTIVE_CONFERENCE_CONFIG.room_priority)

THEME_ORDER = [
    "Measurement of historical income and wealth inequality dynamics",
    "Environmental inequalities",
    "Global wealth distribution dynamics",
    "Income and wealth mobility",
    "Land inequality",
    "Factors contributing to income inequalities",
    "Political inequalities",
    "Gender inequality",
    "Inequality perceptions",
    "Taxation and tax evasion",
    "Methodological advances in inequality measurement",
]

THEME_SHORT = {
    "Measurement of historical income and wealth inequality dynamics": "Historical Measurement",
    "Environmental inequalities": "Environmental Inequalities",
    "Global wealth distribution dynamics": "Global Wealth Dynamics",
    "Income and wealth mobility": "Income and Wealth Mobility",
    "Land inequality": "Land Inequality",
    "Factors contributing to income inequalities": "Income Inequality Drivers",
    "Political inequalities": "Political Inequalities",
    "Gender inequality": "Gender Inequality",
    "Inequality perceptions": "Inequality Perceptions",
    "Taxation and tax evasion": "Taxation and Evasion",
    "Methodological advances in inequality measurement": "Methods and Measurement",
}

THEME_ALIAS = {
    "measurement of historical dynamics of income and wealth": "Measurement of historical income and wealth inequality dynamics",
    "environmental inequalities": "Environmental inequalities",
    "global wealth distribution dynamics": "Global wealth distribution dynamics",
    "income and wealth mobility": "Income and wealth mobility",
    "intergenerational mobility": "Income and wealth mobility",
    "land inequality": "Land inequality",
    "agricultural land inequality": "Land inequality",
    "factors contributing to income inequality": "Factors contributing to income inequalities",
    "political inequalities": "Political inequalities",
    "gender inequality": "Gender inequality",
    "inequality perceptions": "Inequality perceptions",
    "taxation and tax evasion": "Taxation and tax evasion",
    "methological advances in the measurement of inequalities": "Methodological advances in inequality measurement",
    "methodological advances in the measurement of inequalities": "Methodological advances in inequality measurement",
}

THEME_KEYWORDS = {
    "Measurement of historical income and wealth inequality dynamics": [
        "historical",
        "long run",
        "distributional national accounts",
        "dina",
        "top incomes",
        "top wealth",
        "national accounts",
        "historical series",
        "wealth share",
    ],
    "Environmental inequalities": [
        "climate",
        "carbon",
        "emissions",
        "energy transition",
        "warming",
        "pollution",
        "biodiversity",
        "environmental justice",
        "decarbon",
    ],
    "Global wealth distribution dynamics": [
        "wealth",
        "assets",
        "inheritance",
        "portfolio",
        "rates of return",
        "saving",
        "capital gains",
        "net worth",
    ],
    "Income and wealth mobility": [
        "mobility",
        "intergenerational",
        "social mobility",
        "upward mobility",
        "downward mobility",
        "opportunity",
        "income mobility",
        "wealth mobility",
        "class mobility",
    ],
    "Land inequality": [
        "landholding",
        "land ownership",
        "agrarian",
        "agricultural",
        "farmland",
        "farm",
        "tenant",
        "rural property",
        "land reform",
        "tenure",
    ],
    "Factors contributing to income inequalities": [
        "labor",
        "wage",
        "union",
        "minimum wage",
        "education",
        "human capital",
        "trade",
        "productivity",
        "market power",
        "skills",
        "employment",
        "unemployment",
    ],
    "Political inequalities": [
        "voting",
        "election",
        "democracy",
        "polarization",
        "political",
        "institutions",
        "party",
        "coalition",
        "governance",
    ],
    "Gender inequality": [
        "gender",
        "female",
        "women",
        "motherhood",
        "care work",
        "patriarchy",
        "sex",
        "femin",
    ],
    "Inequality perceptions": [
        "perception",
        "belief",
        "preference",
        "redistribution",
        "attitudes",
        "survey experiment",
        "fairness",
    ],
    "Taxation and tax evasion": [
        "tax",
        "taxation",
        "fiscal",
        "evasion",
        "avoidance",
        "wealth tax",
        "corporate tax",
        "vat",
        "income tax",
    ],
    "Methodological advances in inequality measurement": [
        "method",
        "methodology",
        "estimation",
        "identification",
        "causal",
        "instrumental variable",
        "panel model",
        "machine learning",
        "decomposition",
    ],
}

SUBTHEME_RULES = {
    "Measurement of historical income and wealth inequality dynamics": [
        ("Historical Series and Archives", ["historical", "archive", "long run", "century"]),
        ("Distributional National Accounts and Data Infrastructure", ["dina", "national accounts", "dataset", "database"]),
        ("Top Incomes, Wealth Shares and Concentration", ["top", "wealth share", "concentration", "elite"]),
        ("Regional and Global Comparison of Inequality Trajectories", ["cross-country", "global", "comparative", "panel of countries"]),
    ],
    "Environmental inequalities": [
        ("Carbon Pricing and Climate Policy Distributional Effects", ["carbon", "pricing", "tax", "mitigation", "policy"]),
        ("Climate Justice, Vulnerability and Adaptation", ["justice", "vulnerability", "adaptation", "resilience", "loss and damage"]),
        ("Energy Transition, Fossil Lock-in and Decarbonization", ["energy", "fossil", "decarbon", "renewable", "transition"]),
        ("Emissions Accounting and Environmental Footprints", ["footprint", "emissions", "pollution", "consumption-based"]),
    ],
    "Global wealth distribution dynamics": [
        ("Inheritance, Bequests and Intergenerational Wealth", ["inheritance", "bequest", "intergenerational", "estate"]),
        ("Asset Prices, Returns and Portfolio Dynamics", ["asset", "portfolio", "return", "capital gains", "valuation"]),
        ("Savings, Capital Accumulation and Wealth Mobility", ["saving", "accumulation", "mobility", "net worth", "capital stock"]),
        ("Global Wealth Convergence and Divergence", ["global", "between countries", "convergence", "divergence"]),
    ],
    "Income and wealth mobility": [
        (
            "Intergenerational Mobility and Equality of Opportunity",
            ["intergenerational mobility", "intergenerational", "parent child", "equality of opportunity", "social mobility"],
        ),
        (
            "Income Mobility Over the Life Cycle",
            ["income mobility", "life cycle", "lifecycle", "earnings dynamics", "income transition"],
        ),
        (
            "Wealth Mobility, Inheritance and Class Persistence",
            ["wealth mobility", "inheritance", "bequest", "class persistence", "net worth"],
        ),
        (
            "Mobility Traps, Segregation and Stratification",
            ["mobility trap", "segregation", "stratification", "neighborhood effects", "upward mobility"],
        ),
    ],
    "Land inequality": [
        (
            "Land Concentration, Ownership and Agrarian Structure",
            ["land concentration", "land ownership", "landholding", "agrarian", "farm size"],
        ),
        (
            "Land Reform, Redistribution and Rural Institutions",
            ["land reform", "redistribution", "agrarian reform", "tenancy reform", "rural institution"],
        ),
        (
            "Tenure Security, Property Rights and Informality",
            ["tenure", "property rights", "titling", "informality", "land registry"],
        ),
        (
            "Agricultural Productivity, Smallholders and Rural Inequality",
            ["agricultural", "smallholder", "productivity", "rural inequality", "farm household"],
        ),
    ],
    "Factors contributing to income inequalities": [
        ("Labor Markets, Wages and Bargaining Power", ["labor", "wage", "union", "bargaining", "employment", "minimum wage"]),
        ("Macroeconomic Drivers: Inflation, Growth and Cycles", ["inflation", "growth", "recession", "business cycle", "monetary"]),
        ("Education, Skills and Human Capital Channels", ["education", "skills", "school", "human capital", "training"]),
        ("Firm Dynamics, Market Power and Productivity", ["firm", "market power", "markup", "productivity", "competition"]),
        ("Trade, Globalization and Structural Change", ["trade", "globalization", "exports", "imports", "structural change"]),
        ("Technology, Automation and Digital Transformation", ["technology", "automation", "ai", "digital", "platform"]),
    ],
    "Political inequalities": [
        ("Voting, Participation and Electoral Cleavages", ["voting", "electoral", "participation", "turnout", "party"]),
        ("Polarization, Media and Democratic Trust", ["polarization", "media", "trust", "misinformation", "social media"]),
        ("State Capacity, Institutions and Policy Design", ["institution", "state", "governance", "public goods", "policy"]),
        ("Political Economy of Redistribution", ["redistribution", "tax policy", "welfare", "coalition", "ideology"]),
    ],
    "Gender inequality": [
        ("Gender Wage Gaps and Labor Income Inequality", ["wage gap", "female labor", "labor income", "occupation", "employment"]),
        ("Care Work, Household Dynamics and Time Use", ["care", "household", "time use", "motherhood", "unpaid"]),
        ("Gendered Institutions, Norms and Social Exclusion", ["norm", "patriarchy", "discrimination", "caste", "exclusion"]),
        ("Gender, Violence and Bodily Autonomy", ["violence", "harassment", "agency", "sexual", "autonomy"]),
    ],
    "Inequality perceptions": [
        ("Perceptions of Fairness and Social Mobility", ["perception", "fairness", "mobility", "belief"]),
        ("Redistribution Preferences and Policy Support", ["redistribution", "policy support", "tax support", "welfare attitudes"]),
        ("Information, Narratives and Belief Formation", ["information", "narrative", "framing", "belief update"]),
        ("Experimental and Survey Evidence on Inequality Attitudes", ["experiment", "survey", "stated preference", "choice experiment"]),
    ],
    "Taxation and tax evasion": [
        ("Wealth Taxation and Capital Income Tax Design", ["wealth tax", "capital income", "net wealth", "progressive tax"]),
        ("Corporate Taxation, Profit Shifting and Evasion", ["corporate tax", "profit shifting", "multinational", "evasion", "avoidance"]),
        ("Tax Incidence, Redistribution and Welfare Effects", ["incidence", "redistribution", "welfare", "fiscal", "progressivity"]),
        ("Tax Compliance, Administration and Enforcement", ["compliance", "enforcement", "audit", "tax administration", "informality"]),
        ("Carbon and Environmental Taxation", ["carbon tax", "emissions tax", "green tax", "climate policy"]),
    ],
    "Methodological advances in inequality measurement": [
        ("Identification Strategies and Causal Inference", ["identification", "instrumental variable", "causal", "quasi-experimental"]),
        ("Advanced Panel and Time-Series Methods", ["panel", "dynamic panel", "time-series", "threshold model"]),
        ("Distributional Decomposition and Counterfactual Methods", ["decomposition", "counterfactual", "shapley", "reweighting"]),
        ("Data Fusion, Harmonization and Measurement Error", ["harmonization", "data fusion", "measurement error", "imputation"]),
        ("Machine Learning and Computational Approaches", ["machine learning", "algorithm", "text-as-data", "nlp"]),
    ],
}


def _hydrate_theme_constants(config: ConferenceConfig) -> None:
    global THEME_ORDER, THEME_SHORT, THEME_ALIAS, THEME_KEYWORDS, SUBTHEME_RULES
    THEME_ORDER = list(config.themes.order)
    THEME_SHORT = dict(config.themes.short)
    THEME_ALIAS = dict(config.themes.alias)
    THEME_KEYWORDS = {
        theme: list(words)
        for theme, words in config.themes.keywords.items()
    }
    SUBTHEME_RULES = {
        theme: [(rule.label, list(rule.keywords)) for rule in rules]
        for theme, rules in config.themes.subtheme_rules.items()
    }


def _hydrate_runtime_constants(config: ConferenceConfig) -> None:
    global DAY_ORDER, DAY_TO_NUM, ROOM_PRIORITY
    DAY_ORDER = list(config.days)
    DAY_TO_NUM = config.day_to_num
    ROOM_PRIORITY = dict(config.room_priority)
    _hydrate_theme_constants(config)


_hydrate_runtime_constants(ACTIVE_CONFERENCE_CONFIG)

CLASSIFICATION_HEADERS = [
    "SubmissionID",
    "OverridePrimaryTheme",
    "OverrideSubtheme",
    "Reviewed",
    "OverrideNotes",
    "UpdatedAt",
]

SESSION_NAME_HEADERS = ["SessionCode", "SessionTitleOverride", "UpdatedAt"]

PROGRAMME_LAYOUT_HEADERS = [
    "SubmissionID",
    "PlacementStatus",
    "SessionCode",
    "TalkIndex",
    "OverflowOrder",
    "UpdatedAt",
]

SESSION_STRUCTURE_HEADERS = [
    "SessionId",
    "SessionCode",
    "Status",
    "DayLabel",
    "DayNum",
    "BlockLabel",
    "BlockNum",
    "TimeLabel",
    "StartMin",
    "EndMin",
    "Room",
    "Capacity",
    "Source",
    "UpdatedAt",
]

PAPER_PLACEMENT_HEADERS = [
    "SubmissionID",
    "PlacementStatus",
    "SessionId",
    "TalkIndex",
    "OverflowOrder",
    "UpdatedAt",
]

PAPER_METADATA_HEADERS = [
    "SubmissionID",
    "TitleOverride",
    "AuthorOverride",
    "UpdatedAt",
]

PAPER_ARCHIVE_HEADERS = [
    "SubmissionID",
    "ArchiveReason",
    "ArchiveNote",
    "ArchivedAt",
    "PreviousPlacementStatus",
    "PreviousSessionId",
    "PreviousTalkIndex",
    "PreviousOverflowOrder",
    "UpdatedAt",
]

MANUAL_TALKS_HEADERS = [
    "SubmissionID",
    "FullName",
    "EmailAddress",
    "Title",
    "Abstract",
    "Themes",
    "LinkToPDF",
    "ReviewerScore",
    "UpdatedAt",
]

LABEL_TYPE_PRIMARY = "primary"
LABEL_TYPE_SECONDARY = "secondary"
LABEL_TYPE_ARCHIVE_REASON = "archive_reason"
DEFAULT_ARCHIVE_REASON_OPTIONS = ["Duplicate submission", "Author cancelled attendance", "Other"]
LABEL_CATALOG_HEADERS = ["LabelType", "LabelValue", "UpdatedAt"]


@dataclass
class Paper:
    submission_id: str
    full_name: str
    email: str
    reviewer_score: str
    source_themes: str
    title: str
    abstract: str
    link_to_pdf: str
    source: str = "submissions"
    primary_theme: str = ""
    detailed_subtheme: str = ""
    secondary_tags: List[str] = field(default_factory=list)
    matched_keywords: List[str] = field(default_factory=list)
    rationale: str = ""
    reviewed: bool = False
    override_notes: str = ""
    session_id: str = ""
    session_code: str = ""
    session_title: str = ""
    day_label: str = ""
    day_num: int = 0
    block_label: str = ""
    block_num: int = 0
    time: str = ""
    room: str = ""
    talk_index: int = 0
    talk_start_min: int = 0
    talk_end_min: int = 0
    placement_status: str = "scheduled"
    overflow_order: int = 0


@dataclass
class Slot:
    day_label: str
    day_num: int
    time: str
    block_label: str
    block_num: int
    room: str
    row_in_source: int

    @property
    def session_code(self) -> str:
        return f"D{self.day_num}-B{self.block_num}-{self.room}"


@dataclass
class Session:
    session_id: str
    session_code: str
    status: str
    day_label: str
    day_num: int
    time: str
    block_label: str
    block_num: int
    room: str
    start_min: int
    end_min: int
    capacity: int
    source: str
    session_title: str
    primary_theme: str
    subtheme: str
    papers: List[Optional[Paper]]
    overflow_papers: List[Paper] = field(default_factory=list)


@dataclass
class ProgrammeState:
    papers: List[Paper]
    sessions: List[Session]
    inactive_sessions: List[Session]
    all_sessions: List[Session]
    archived_papers: List[Paper]
    validations: Dict[str, object]
    unassigned_papers: List[Paper] = field(default_factory=list)
    slot_conflicts: List[Dict[str, str]] = field(default_factory=list)
    edited_submission_ids: set[str] = field(default_factory=set)


@dataclass
class PackedGroup:
    index: int
    papers: List[Optional[Paper]]
    dominant_primary: str
    dominant_subtheme: str
    auto_title: str


_BASE_PARSE_CACHE: Dict[Tuple[str, str, str], Tuple[List[Paper], List[Slot]]] = {}


def _file_signature(path: Path) -> str:
    if not path.exists():
        return f"{path.resolve()}::MISSING"
    stat = path.stat()
    return f"{path.resolve()}::{stat.st_mtime_ns}::{stat.st_size}"


def _base_cache_key(submissions_path: Path, programme_path: Path, config: ConferenceConfig) -> Tuple[str, str, str]:
    return (_file_signature(submissions_path), _file_signature(programme_path), config.signature())


def _compute_edited_submission_ids(
    class_overrides: Dict[str, Dict[str, str]],
    layout_overrides: Dict[str, Dict[str, str]],
    metadata_overrides: Optional[Dict[str, Dict[str, str]]] = None,
    archive_overrides: Optional[Dict[str, Dict[str, str]]] = None,
) -> set[str]:
    edited: set[str] = set()
    for sid, row in class_overrides.items():
        if (
            str(row.get("OverridePrimaryTheme", "")).strip()
            or str(row.get("OverrideSubtheme", "")).strip()
            or str(row.get("OverrideNotes", "")).strip()
            or parse_bool(str(row.get("Reviewed", "")))
        ):
            edited.add(sid)

    for sid, row in layout_overrides.items():
        status = str(row.get("PlacementStatus", "")).strip().lower()
        session_code = str(row.get("SessionCode", "")).strip()
        talk_index = str(row.get("TalkIndex", "")).strip()
        overflow_order = str(row.get("OverflowOrder", "")).strip()
        if status in {"unassigned", "overflow"} or session_code or talk_index or overflow_order:
            edited.add(sid)

    for sid, row in (metadata_overrides or {}).items():
        if str(row.get("TitleOverride", "")).strip() or str(row.get("AuthorOverride", "")).strip():
            edited.add(sid)

    for sid, row in (archive_overrides or {}).items():
        if (
            str(row.get("ArchiveReason", "")).strip()
            or str(row.get("ArchiveNote", "")).strip()
            or str(row.get("ArchivedAt", "")).strip()
        ):
            edited.add(sid)

    return edited


class XlsxXmlReader:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.zipf = zipfile.ZipFile(path)
        self.shared_strings = self._load_shared_strings()
        self.sheet_targets = self._load_sheet_targets()

    def _load_shared_strings(self) -> List[str]:
        if "xl/sharedStrings.xml" not in self.zipf.namelist():
            return []
        root = ET.fromstring(self.zipf.read("xl/sharedStrings.xml"))
        out: List[str] = []
        for si in root.findall("main:si", NS):
            parts = [t.text or "" for t in si.findall(".//main:t", NS)]
            out.append("".join(parts))
        return out

    def _load_sheet_targets(self) -> Dict[str, str]:
        rel_root = ET.fromstring(self.zipf.read("xl/_rels/workbook.xml.rels"))
        rid_to_target: Dict[str, str] = {}
        for rel in rel_root.findall("pkgrel:Relationship", NS):
            rid = rel.attrib.get("Id")
            target = rel.attrib.get("Target", "")
            if rid:
                rid_to_target[rid] = target if target.startswith("xl/") else f"xl/{target}"

        wb_root = ET.fromstring(self.zipf.read("xl/workbook.xml"))
        out: Dict[str, str] = {}
        for sheet in wb_root.findall("main:sheets/main:sheet", NS):
            name = sheet.attrib.get("name", "")
            rid = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            if name and rid in rid_to_target:
                out[name] = rid_to_target[rid]
        return out

    def read_sheet_rows(self, sheet_name: str) -> List[Tuple[int, Dict[int, str]]]:
        target = self.sheet_targets[sheet_name]
        root = ET.fromstring(self.zipf.read(target))
        sheet_data = root.find("main:sheetData", NS)
        rows: List[Tuple[int, Dict[int, str]]] = []

        if sheet_data is None:
            return rows

        for row in sheet_data.findall("main:row", NS):
            row_num = int(row.attrib.get("r", "0"))
            cells: Dict[int, str] = {}
            for cell in row.findall("main:c", NS):
                ref = cell.attrib.get("r", "")
                m = re.match(r"([A-Z]+)", ref)
                if not m:
                    continue
                col_idx = col_to_index(m.group(1))
                cell_type = cell.attrib.get("t")

                val = ""
                if cell_type == "inlineStr":
                    is_node = cell.find("main:is", NS)
                    if is_node is not None:
                        val = "".join(t.text or "" for t in is_node.findall(".//main:t", NS))
                else:
                    v_node = cell.find("main:v", NS)
                    if v_node is not None and v_node.text is not None:
                        raw = v_node.text
                        if cell_type == "s":
                            try:
                                val = self.shared_strings[int(raw)]
                            except Exception:
                                val = raw
                        else:
                            val = raw
                cells[col_idx] = val
            rows.append((row_num, cells))
        return rows


def col_to_index(col: str) -> int:
    n = 0
    for ch in col:
        if not ch.isalpha():
            break
        n = n * 26 + (ord(ch.upper()) - 64)
    return n


def normalize_key(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", (text or "").strip().lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def keyword_matches(text: str, keywords: List[str]) -> List[str]:
    return [kw for kw in keywords if kw in text]


def parse_start_minutes(time_range: str) -> int:
    m = re.match(r"\s*(\d{1,2})h(\d{0,2})", str(time_range))
    if not m:
        return 0
    hour = int(m.group(1))
    minute = int(m.group(2)) if m.group(2) else 0
    return hour * 60 + minute


def parse_end_minutes(time_range: str, default_duration: int = 90) -> int:
    text = str(time_range or "")
    parts = text.split("-", 1)
    start = parse_start_minutes(text)
    if len(parts) < 2:
        return start + default_duration
    end_match = re.search(r"(\d{1,2})h(\d{0,2})", parts[1])
    if not end_match:
        return start + default_duration
    end_h = int(end_match.group(1))
    end_m = int(end_match.group(2)) if end_match.group(2) else 0
    end = end_h * 60 + end_m
    if end <= start:
        end += 24 * 60
    return end


def format_minutes(total_minutes: int) -> str:
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def build_time_label(start_min: int, end_min: int) -> str:
    start = max(0, int(start_min))
    end = max(start + 1, int(end_min))
    return f"{start // 60}h{start % 60:02d}-{end // 60}h{end % 60:02d}"


def room_sort_key(room: str) -> Tuple[int, str]:
    return (ROOM_PRIORITY.get(room, 999), room)


def parse_bool(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _parse_positive_int(raw: str, default: int = 0) -> int:
    try:
        value = int(str(raw).strip())
        return value if value > 0 else default
    except Exception:
        return default


def _parse_nonnegative_int(raw: str, default: int = 0) -> int:
    try:
        value = int(str(raw).strip())
        return value if value >= 0 else default
    except Exception:
        return default


def build_group_slices(total_items: int) -> List[int]:
    if total_items <= 0:
        return []
    remainder = total_items % 4
    groups_of_three = 0 if remainder == 0 else 4 - remainder
    groups_of_four = (total_items - (groups_of_three * 3)) // 4
    if groups_of_four < 0:
        groups_of_four = 0
    sizes = [4] * groups_of_four + [3] * groups_of_three
    if sum(sizes) != total_items:
        raise RuntimeError("Group sizing mismatch")
    return sizes


def map_source_themes(raw: str) -> List[str]:
    tags: List[str] = []
    for part in [p.strip() for p in (raw or "").split(",") if p.strip()]:
        key = normalize_key(part)
        if key in THEME_ALIAS:
            tags.append(THEME_ALIAS[key])
    return tags


def infer_theme_from_text(text: str) -> str:
    best_theme = "Factors contributing to income inequalities"
    best_score = 0
    for theme, words in THEME_KEYWORDS.items():
        score = 0
        for w in words:
            if w in text:
                score += 1
        if score > best_score:
            best_theme = theme
            best_score = score
    return best_theme


def classify_subtheme(primary_theme: str, text: str) -> Tuple[str, List[str]]:
    rules = SUBTHEME_RULES.get(primary_theme, [])
    best_label = "General Inequality Dynamics"
    best_score = -1
    best_hits: List[str] = []
    for label, keywords in rules:
        hits = [k for k in keywords if k in text]
        score = len(hits)
        if score > best_score:
            best_label = label
            best_score = score
            best_hits = hits

    if best_score <= 0:
        if primary_theme == "Factors contributing to income inequalities":
            best_label = "Income Distribution Drivers"
        elif primary_theme == "Methodological advances in inequality measurement":
            best_label = "Methodological Innovations in Inequality Research"
        else:
            best_label = f"{THEME_SHORT.get(primary_theme, primary_theme)} - General"
        best_hits = []

    return best_label, best_hits[:5]


def parse_submissions(path: Path, config: ConferenceConfig = ACTIVE_CONFERENCE_CONFIG) -> List[Paper]:
    if not path.exists():
        return []
    reader = XlsxXmlReader(path)
    rows = reader.read_sheet_rows(config.parsing.submissions_sheet)
    if not rows:
        raise RuntimeError("Submissions file appears empty")

    header_cells = rows[0][1]
    max_col = max(header_cells.keys()) if header_cells else 0
    headers = [header_cells.get(i, "") for i in range(1, max_col + 1)]
    col_idx = {h: i + 1 for i, h in enumerate(headers) if h}

    required = [
        "SubmissionID",
        "FullName",
        "EmailAddress",
        "Title",
        "Abstract",
        "Themes",
        "LinkToPDF",
        "ReviewerScore",
    ]
    missing = [c for c in required if c not in col_idx]
    if missing:
        raise RuntimeError(f"Missing expected columns: {missing}")

    accepted_scores = set(config.parsing.accepted_reviewer_scores)
    accepted: List[Paper] = []
    for _, cells in rows[1:]:
        score = str(cells.get(col_idx["ReviewerScore"], "")).strip()
        if score not in accepted_scores:
            continue

        accepted.append(
            Paper(
                submission_id=str(cells.get(col_idx["SubmissionID"], "")).strip(),
                full_name=str(cells.get(col_idx["FullName"], "")).strip(),
                email=str(cells.get(col_idx["EmailAddress"], "")).strip(),
                reviewer_score=score,
                source_themes=str(cells.get(col_idx["Themes"], "")).strip(),
                title=str(cells.get(col_idx["Title"], "")).strip(),
                abstract=str(cells.get(col_idx["Abstract"], "")).strip(),
                link_to_pdf=str(cells.get(col_idx["LinkToPDF"], "")).strip(),
            )
        )

    return accepted


def parse_programme_slots(path: Path, config: ConferenceConfig = ACTIVE_CONFERENCE_CONFIG) -> List[Slot]:
    if not path.exists():
        return []
    reader = XlsxXmlReader(path)
    slots: List[Slot] = []
    parsing = config.parsing.programme
    room_name_pattern = re.compile(parsing.room_name_pattern)
    session_label_regex = re.compile(parsing.session_label_regex)
    required_token = parsing.session_required_token.upper()
    optional_token = parsing.optional_token.upper()

    for day_name in config.days:
        rows = reader.read_sheet_rows(day_name)
        matrix: Dict[Tuple[int, int], str] = {}
        for row_num, cells in rows:
            for col_num, value in cells.items():
                matrix[(row_num, col_num)] = value

        room_cols = []
        for col_num in range(parsing.room_column_start, parsing.room_column_end + 1):
            name = matrix.get((parsing.room_header_row, col_num), "")
            if room_name_pattern.match(name):
                room_cols.append(col_num)

        for row_num in range(parsing.scan_row_start, parsing.scan_row_end + 1):
            block_label = matrix.get((row_num, parsing.block_column), "")
            block_upper = block_label.upper()
            if required_token not in block_upper:
                continue
            if optional_token and optional_token in block_upper:
                continue

            time_label = matrix.get((row_num, parsing.time_column), "")
            if any(window.matches(day_name, time_label) for window in parsing.skip_time_windows):
                continue

            session_match = session_label_regex.search(block_upper)
            block_num = int(session_match.group(1)) if session_match else 0

            open_rooms: List[str] = []
            for col_num in room_cols:
                if matrix.get((row_num, col_num), "") == "":
                    open_rooms.append(matrix.get((parsing.room_header_row, col_num), f"Room-{col_num}"))

            extra_rooms: List[str] = []
            for rule in parsing.extra_rooms:
                if rule.matches(day_name, block_num):
                    extra_rooms.extend(list(rule.rooms))
            all_rooms = open_rooms + extra_rooms
            for room in all_rooms:
                slots.append(
                    Slot(
                        day_label=day_name,
                        day_num=config.day_to_num[day_name],
                        time=time_label,
                        block_label=block_label,
                        block_num=block_num,
                        room=room,
                        row_in_source=row_num,
                    )
                )

    return sorted(slots, key=lambda s: (s.day_num, s.row_in_source, room_sort_key(s.room)))


def ensure_state_files(
    state_dir: Path = STATE_DIR,
    classification_overrides_file: Path = CLASSIFICATION_OVERRIDES_FILE,
    session_name_overrides_file: Path = SESSION_NAME_OVERRIDES_FILE,
    programme_layout_overrides_file: Path = PROGRAMME_LAYOUT_OVERRIDES_FILE,
    session_structure_file: Path = SESSION_STRUCTURE_FILE,
    paper_placements_file: Path = PAPER_PLACEMENTS_FILE,
    paper_metadata_overrides_file: Path = PAPER_METADATA_OVERRIDES_FILE,
    paper_archive_overrides_file: Path = PAPER_ARCHIVE_OVERRIDES_FILE,
    manual_talks_file: Path = MANUAL_TALKS_FILE,
    label_catalog_file: Path = LABEL_CATALOG_FILE,
) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)

    if not classification_overrides_file.exists():
        with classification_overrides_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CLASSIFICATION_HEADERS)
            writer.writeheader()

    if not session_name_overrides_file.exists():
        with session_name_overrides_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=SESSION_NAME_HEADERS)
            writer.writeheader()

    if not programme_layout_overrides_file.exists():
        with programme_layout_overrides_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=PROGRAMME_LAYOUT_HEADERS)
            writer.writeheader()

    if not session_structure_file.exists():
        with session_structure_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=SESSION_STRUCTURE_HEADERS)
            writer.writeheader()

    if not paper_placements_file.exists():
        with paper_placements_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=PAPER_PLACEMENT_HEADERS)
            writer.writeheader()

    if not paper_metadata_overrides_file.exists():
        with paper_metadata_overrides_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=PAPER_METADATA_HEADERS)
            writer.writeheader()

    if not paper_archive_overrides_file.exists():
        with paper_archive_overrides_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=PAPER_ARCHIVE_HEADERS)
            writer.writeheader()

    if not manual_talks_file.exists():
        with manual_talks_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=MANUAL_TALKS_HEADERS)
            writer.writeheader()

    if not label_catalog_file.exists():
        with label_catalog_file.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=LABEL_CATALOG_HEADERS)
            writer.writeheader()


def _load_csv_rows(path: Path, expected_headers: List[str]) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            return []
        rows = []
        for row in reader:
            rows.append({h: (row.get(h, "") or "").strip() for h in expected_headers})
    return rows


def _normalize_label_type(value: object) -> str:
    label_type = str(value or "").strip().lower()
    return label_type if label_type in {LABEL_TYPE_PRIMARY, LABEL_TYPE_SECONDARY, LABEL_TYPE_ARCHIVE_REASON} else ""


def load_label_catalog(path: Path = LABEL_CATALOG_FILE) -> Dict[str, List[str]]:
    rows = _load_csv_rows(path, LABEL_CATALOG_HEADERS)
    labels_by_type = {
        LABEL_TYPE_PRIMARY: set(),
        LABEL_TYPE_SECONDARY: set(),
        LABEL_TYPE_ARCHIVE_REASON: set(),
    }
    for row in rows:
        label_type = _normalize_label_type(row.get("LabelType", ""))
        if not label_type:
            continue
        value = str(row.get("LabelValue", "")).strip()
        if not value:
            continue
        labels_by_type[label_type].add(value)

    return {
        LABEL_TYPE_PRIMARY: sorted(labels_by_type[LABEL_TYPE_PRIMARY], key=str.casefold),
        LABEL_TYPE_SECONDARY: sorted(labels_by_type[LABEL_TYPE_SECONDARY], key=str.casefold),
        LABEL_TYPE_ARCHIVE_REASON: sorted(labels_by_type[LABEL_TYPE_ARCHIVE_REASON], key=str.casefold),
    }


def write_label_catalog(
    catalog: Dict[str, Iterable[str]],
    path: Path = LABEL_CATALOG_FILE,
) -> None:
    normalized = {
        LABEL_TYPE_PRIMARY: set(),
        LABEL_TYPE_SECONDARY: set(),
        LABEL_TYPE_ARCHIVE_REASON: set(),
    }
    for label_type in (LABEL_TYPE_PRIMARY, LABEL_TYPE_SECONDARY, LABEL_TYPE_ARCHIVE_REASON):
        for value in list(catalog.get(label_type, []) or []):
            cleaned = str(value or "").strip()
            if cleaned:
                normalized[label_type].add(cleaned)

    now = datetime.utcnow().isoformat(timespec="seconds")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LABEL_CATALOG_HEADERS)
        writer.writeheader()
        for label_type in (LABEL_TYPE_PRIMARY, LABEL_TYPE_SECONDARY, LABEL_TYPE_ARCHIVE_REASON):
            for value in sorted(normalized[label_type], key=str.casefold):
                writer.writerow(
                    {
                        "LabelType": label_type,
                        "LabelValue": value,
                        "UpdatedAt": now,
                    }
                )


def merge_label_catalog_labels(
    primary_values: Iterable[str],
    secondary_values: Iterable[str],
    archive_reason_values: Iterable[str] = (),
    path: Path = LABEL_CATALOG_FILE,
) -> bool:
    existing = load_label_catalog(path)
    current_primary = set(existing.get(LABEL_TYPE_PRIMARY, []))
    current_secondary = set(existing.get(LABEL_TYPE_SECONDARY, []))
    current_archive_reasons = set(existing.get(LABEL_TYPE_ARCHIVE_REASON, []))
    merged_primary = set(current_primary)
    merged_secondary = set(current_secondary)
    merged_archive_reasons = set(current_archive_reasons)

    for value in list(primary_values or []):
        cleaned = str(value or "").strip()
        if cleaned:
            merged_primary.add(cleaned)
    for value in list(secondary_values or []):
        cleaned = str(value or "").strip()
        if cleaned:
            merged_secondary.add(cleaned)
    for value in list(archive_reason_values or []):
        cleaned = str(value or "").strip()
        if cleaned:
            merged_archive_reasons.add(cleaned)

    if (
        merged_primary == current_primary
        and merged_secondary == current_secondary
        and merged_archive_reasons == current_archive_reasons
    ):
        return False

    write_label_catalog(
        {
            LABEL_TYPE_PRIMARY: merged_primary,
            LABEL_TYPE_SECONDARY: merged_secondary,
            LABEL_TYPE_ARCHIVE_REASON: merged_archive_reasons,
        },
        path=path,
    )
    return True


def load_classification_overrides(path: Path = CLASSIFICATION_OVERRIDES_FILE) -> Dict[str, Dict[str, str]]:
    rows = _load_csv_rows(path, CLASSIFICATION_HEADERS)
    out: Dict[str, Dict[str, str]] = {}
    for row in rows:
        sid = row.get("SubmissionID", "")
        if not sid:
            continue
        out[sid] = row
    return out


def write_classification_overrides(rows: Iterable[Dict[str, str]], path: Path = CLASSIFICATION_OVERRIDES_FILE) -> None:
    normalized: Dict[str, Dict[str, str]] = {}
    now = datetime.utcnow().isoformat(timespec="seconds")
    for row in rows:
        sid = str(row.get("SubmissionID", "")).strip()
        if not sid:
            continue
        normalized[sid] = {
            "SubmissionID": sid,
            "OverridePrimaryTheme": str(row.get("OverridePrimaryTheme", "")).strip(),
            "OverrideSubtheme": str(row.get("OverrideSubtheme", "")).strip(),
            "Reviewed": str(row.get("Reviewed", "False")).strip() or "False",
            "OverrideNotes": str(row.get("OverrideNotes", "")).strip(),
            "UpdatedAt": str(row.get("UpdatedAt", "")).strip() or now,
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CLASSIFICATION_HEADERS)
        writer.writeheader()
        for sid in sorted(normalized.keys(), key=lambda x: (len(x), x)):
            writer.writerow(normalized[sid])


def load_paper_metadata_overrides(path: Path = PAPER_METADATA_OVERRIDES_FILE) -> Dict[str, Dict[str, str]]:
    rows = _load_csv_rows(path, PAPER_METADATA_HEADERS)
    out: Dict[str, Dict[str, str]] = {}
    for row in rows:
        sid = row.get("SubmissionID", "")
        if not sid:
            continue
        out[sid] = row
    return out


def write_paper_metadata_overrides(
    rows: Iterable[Dict[str, str]],
    path: Path = PAPER_METADATA_OVERRIDES_FILE,
) -> None:
    normalized: Dict[str, Dict[str, str]] = {}
    now = datetime.utcnow().isoformat(timespec="seconds")
    for row in rows:
        sid = str(row.get("SubmissionID", "")).strip()
        if not sid:
            continue
        title_override = str(row.get("TitleOverride", "")).strip()
        author_override = str(row.get("AuthorOverride", "")).strip()
        if not title_override and not author_override:
            continue
        normalized[sid] = {
            "SubmissionID": sid,
            "TitleOverride": title_override,
            "AuthorOverride": author_override,
            "UpdatedAt": str(row.get("UpdatedAt", "")).strip() or now,
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PAPER_METADATA_HEADERS)
        writer.writeheader()
        for sid in sorted(normalized.keys(), key=lambda x: (len(x), x)):
            writer.writerow(normalized[sid])


def load_paper_archive_overrides(path: Path = PAPER_ARCHIVE_OVERRIDES_FILE) -> Dict[str, Dict[str, str]]:
    rows = _load_csv_rows(path, PAPER_ARCHIVE_HEADERS)
    out: Dict[str, Dict[str, str]] = {}
    for row in rows:
        sid = str(row.get("SubmissionID", "")).strip()
        if not sid:
            continue
        placement_status = str(row.get("PreviousPlacementStatus", "")).strip().lower()
        if placement_status not in {"scheduled", "unassigned", "overflow"}:
            placement_status = "unassigned"
        out[sid] = {
            "SubmissionID": sid,
            "ArchiveReason": str(row.get("ArchiveReason", "")).strip(),
            "ArchiveNote": str(row.get("ArchiveNote", "")).strip(),
            "ArchivedAt": str(row.get("ArchivedAt", "")).strip(),
            "PreviousPlacementStatus": placement_status,
            "PreviousSessionId": str(row.get("PreviousSessionId", "")).strip(),
            "PreviousTalkIndex": str(row.get("PreviousTalkIndex", "")).strip(),
            "PreviousOverflowOrder": str(row.get("PreviousOverflowOrder", "")).strip(),
            "UpdatedAt": str(row.get("UpdatedAt", "")).strip(),
        }
    return out


def write_paper_archive_overrides(
    rows: Iterable[Dict[str, str]],
    path: Path = PAPER_ARCHIVE_OVERRIDES_FILE,
) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    normalized: Dict[str, Dict[str, str]] = {}
    for row in rows:
        sid = str(row.get("SubmissionID", "")).strip()
        if not sid:
            continue
        placement_status = str(row.get("PreviousPlacementStatus", "")).strip().lower()
        if placement_status not in {"scheduled", "unassigned", "overflow"}:
            placement_status = "unassigned"
        normalized[sid] = {
            "SubmissionID": sid,
            "ArchiveReason": str(row.get("ArchiveReason", "")).strip(),
            "ArchiveNote": str(row.get("ArchiveNote", "")).strip(),
            "ArchivedAt": str(row.get("ArchivedAt", "")).strip() or now,
            "PreviousPlacementStatus": placement_status,
            "PreviousSessionId": str(row.get("PreviousSessionId", "")).strip(),
            "PreviousTalkIndex": str(row.get("PreviousTalkIndex", "")).strip(),
            "PreviousOverflowOrder": str(row.get("PreviousOverflowOrder", "")).strip(),
            "UpdatedAt": str(row.get("UpdatedAt", "")).strip() or now,
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PAPER_ARCHIVE_HEADERS)
        writer.writeheader()
        for sid in sorted(normalized.keys(), key=lambda x: (len(x), x)):
            writer.writerow(normalized[sid])


def load_session_name_overrides(path: Path = SESSION_NAME_OVERRIDES_FILE) -> Dict[str, str]:
    rows = _load_csv_rows(path, SESSION_NAME_HEADERS)
    out: Dict[str, str] = {}
    for row in rows:
        session_code = row.get("SessionCode", "")
        if not session_code:
            continue
        title = row.get("SessionTitleOverride", "")
        if title:
            out[session_code] = title
    return out


def write_session_name_overrides(overrides: Dict[str, str], path: Path = SESSION_NAME_OVERRIDES_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.utcnow().isoformat(timespec="seconds")
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SESSION_NAME_HEADERS)
        writer.writeheader()
        for session_code in sorted(overrides.keys()):
            title = overrides[session_code].strip()
            if not title:
                continue
            writer.writerow(
                {
                    "SessionCode": session_code,
                    "SessionTitleOverride": title,
                    "UpdatedAt": now,
                }
            )


def load_programme_layout_overrides(
    path: Path = PROGRAMME_LAYOUT_OVERRIDES_FILE,
    paper_placements_path: Path = PAPER_PLACEMENTS_FILE,
    session_structure_path: Path = SESSION_STRUCTURE_FILE,
) -> Dict[str, Dict[str, str]]:
    placements = load_paper_placements(paper_placements_path)
    if placements:
        session_rows = load_session_structure_rows(session_structure_path)
        session_id_to_code = {
            str(row.get("SessionId", "")).strip(): str(row.get("SessionCode", "")).strip()
            for row in session_rows.values()
        }
        out: Dict[str, Dict[str, str]] = {}
        for sid, row in placements.items():
            session_id = str(row.get("SessionId", "")).strip()
            out[sid] = {
                "SubmissionID": sid,
                "PlacementStatus": str(row.get("PlacementStatus", "")).strip(),
                "SessionCode": session_id_to_code.get(session_id, "") if session_id else "",
                "TalkIndex": str(row.get("TalkIndex", "")).strip(),
                "OverflowOrder": str(row.get("OverflowOrder", "")).strip(),
                "UpdatedAt": str(row.get("UpdatedAt", "")).strip(),
            }
        return out

    rows = _load_csv_rows(path, PROGRAMME_LAYOUT_HEADERS)
    out: Dict[str, Dict[str, str]] = {}
    for row in rows:
        sid = row.get("SubmissionID", "")
        if not sid:
            continue
        out[sid] = row
    return out


def write_programme_layout_overrides(
    rows: Iterable[Dict[str, str]],
    path: Path = PROGRAMME_LAYOUT_OVERRIDES_FILE,
    session_structure_path: Path = SESSION_STRUCTURE_FILE,
    paper_placements_path: Path = PAPER_PLACEMENTS_FILE,
) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    session_rows = load_session_structure_rows(session_structure_path)
    code_to_id = {}
    for row in session_rows.values():
        session_code = str(row.get("SessionCode", "")).strip()
        session_id = str(row.get("SessionId", "")).strip()
        if session_code and session_id:
            code_to_id[session_code] = session_id

    placements: Dict[str, Dict[str, str]] = {}
    for row in rows:
        sid = str(row.get("SubmissionID", "")).strip()
        if not sid:
            continue
        status = str(row.get("PlacementStatus", "")).strip().lower()
        if status not in {"scheduled", "unassigned", "overflow"}:
            status = "scheduled"
        session_code = str(row.get("SessionCode", "")).strip()
        session_id = code_to_id.get(session_code, "")
        if status in {"scheduled", "overflow"} and not session_id:
            status = "unassigned"
        placements[sid] = {
            "SubmissionID": sid,
            "PlacementStatus": status,
            "SessionId": session_id if status in {"scheduled", "overflow"} else "",
            "TalkIndex": str(row.get("TalkIndex", "")).strip() if status == "scheduled" else "",
            "OverflowOrder": str(row.get("OverflowOrder", "")).strip() if status == "overflow" else "",
            "UpdatedAt": str(row.get("UpdatedAt", "")).strip() or now,
        }

    write_paper_placements(placements.values(), paper_placements_path)


def load_session_structure_rows(path: Path = SESSION_STRUCTURE_FILE) -> Dict[str, Dict[str, str]]:
    rows = _load_csv_rows(path, SESSION_STRUCTURE_HEADERS)
    out: Dict[str, Dict[str, str]] = {}
    for row in rows:
        session_id = str(row.get("SessionId", "")).strip()
        if not session_id:
            continue
        status = str(row.get("Status", "active")).strip().lower()
        if status not in {"active", "inactive"}:
            status = "active"
        normalized = {
            "SessionId": session_id,
            "SessionCode": str(row.get("SessionCode", "")).strip(),
            "Status": status,
            "DayLabel": str(row.get("DayLabel", "")).strip(),
            "DayNum": str(row.get("DayNum", "")).strip(),
            "BlockLabel": str(row.get("BlockLabel", "")).strip(),
            "BlockNum": str(row.get("BlockNum", "")).strip(),
            "TimeLabel": str(row.get("TimeLabel", "")).strip(),
            "StartMin": str(row.get("StartMin", "")).strip(),
            "EndMin": str(row.get("EndMin", "")).strip(),
            "Room": str(row.get("Room", "")).strip(),
            "Capacity": str(row.get("Capacity", "")).strip(),
            "Source": str(row.get("Source", "")).strip() or "template",
            "UpdatedAt": str(row.get("UpdatedAt", "")).strip(),
        }
        out[session_id] = normalized
    return out


def write_session_structure_rows(rows: Iterable[Dict[str, str]], path: Path = SESSION_STRUCTURE_FILE) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    normalized: Dict[str, Dict[str, str]] = {}
    for row in rows:
        session_id = str(row.get("SessionId", "")).strip() or str(uuid.uuid4())
        status = str(row.get("Status", "active")).strip().lower()
        if status not in {"active", "inactive"}:
            status = "active"
        capacity = _parse_positive_int(row.get("Capacity", "4"), default=4)
        start_min = _parse_positive_int(row.get("StartMin", "0"), default=0)
        end_min = _parse_positive_int(
            row.get("EndMin", "0"),
            default=max(1, start_min + ACTIVE_CONFERENCE_CONFIG.structure.default_session_duration_min),
        )
        if end_min <= start_min:
            end_min = start_min + ACTIVE_CONFERENCE_CONFIG.structure.default_session_duration_min
        normalized[session_id] = {
            "SessionId": session_id,
            "SessionCode": str(row.get("SessionCode", "")).strip(),
            "Status": status,
            "DayLabel": str(row.get("DayLabel", "")).strip(),
            "DayNum": str(row.get("DayNum", "")).strip(),
            "BlockLabel": str(row.get("BlockLabel", "")).strip(),
            "BlockNum": str(row.get("BlockNum", "")).strip(),
            "TimeLabel": str(row.get("TimeLabel", "")).strip(),
            "StartMin": str(start_min),
            "EndMin": str(end_min),
            "Room": str(row.get("Room", "")).strip(),
            "Capacity": str(capacity),
            "Source": str(row.get("Source", "")).strip() or "manual",
            "UpdatedAt": str(row.get("UpdatedAt", "")).strip() or now,
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SESSION_STRUCTURE_HEADERS)
        writer.writeheader()
        for session_id in sorted(normalized.keys()):
            writer.writerow(normalized[session_id])


def load_paper_placements(path: Path = PAPER_PLACEMENTS_FILE) -> Dict[str, Dict[str, str]]:
    rows = _load_csv_rows(path, PAPER_PLACEMENT_HEADERS)
    out: Dict[str, Dict[str, str]] = {}
    for row in rows:
        sid = str(row.get("SubmissionID", "")).strip()
        if not sid:
            continue
        status = str(row.get("PlacementStatus", "")).strip().lower()
        if status not in {"scheduled", "unassigned", "overflow"}:
            status = "unassigned"
        out[sid] = {
            "SubmissionID": sid,
            "PlacementStatus": status,
            "SessionId": str(row.get("SessionId", "")).strip() if status in {"scheduled", "overflow"} else "",
            "TalkIndex": str(row.get("TalkIndex", "")).strip() if status == "scheduled" else "",
            "OverflowOrder": str(row.get("OverflowOrder", "")).strip() if status == "overflow" else "",
            "UpdatedAt": str(row.get("UpdatedAt", "")).strip(),
        }
    return out


def write_paper_placements(rows: Iterable[Dict[str, str]], path: Path = PAPER_PLACEMENTS_FILE) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    normalized: Dict[str, Dict[str, str]] = {}
    for row in rows:
        sid = str(row.get("SubmissionID", "")).strip()
        if not sid:
            continue
        status = str(row.get("PlacementStatus", "")).strip().lower()
        if status not in {"scheduled", "unassigned", "overflow"}:
            status = "unassigned"
        normalized[sid] = {
            "SubmissionID": sid,
            "PlacementStatus": status,
            "SessionId": str(row.get("SessionId", "")).strip() if status in {"scheduled", "overflow"} else "",
            "TalkIndex": str(row.get("TalkIndex", "")).strip() if status == "scheduled" else "",
            "OverflowOrder": str(row.get("OverflowOrder", "")).strip() if status == "overflow" else "",
            "UpdatedAt": str(row.get("UpdatedAt", "")).strip() or now,
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PAPER_PLACEMENT_HEADERS)
        writer.writeheader()
        for sid in sorted(normalized.keys(), key=lambda x: (len(x), x)):
            writer.writerow(normalized[sid])


def load_manual_talks(path: Path = MANUAL_TALKS_FILE) -> List[Paper]:
    rows = _load_csv_rows(path, MANUAL_TALKS_HEADERS)
    out: List[Paper] = []
    for idx, row in enumerate(rows, start=1):
        sid = str(row.get("SubmissionID", "")).strip() or f"MANUAL-{idx:04d}"
        out.append(
            Paper(
                submission_id=sid,
                full_name=str(row.get("FullName", "")).strip(),
                email=str(row.get("EmailAddress", "")).strip(),
                reviewer_score=str(row.get("ReviewerScore", "1")).strip() or "1",
                source_themes=str(row.get("Themes", "")).strip(),
                title=str(row.get("Title", "")).strip(),
                abstract=str(row.get("Abstract", "")).strip(),
                link_to_pdf=str(row.get("LinkToPDF", "")).strip(),
                source="manual",
            )
        )
    return out


def write_manual_talks(rows: Iterable[Dict[str, str]], path: Path = MANUAL_TALKS_FILE) -> None:
    now = datetime.utcnow().isoformat(timespec="seconds")
    normalized: Dict[str, Dict[str, str]] = {}
    counter = 1
    for row in rows:
        sid = str(row.get("SubmissionID", "")).strip()
        if not sid:
            sid = f"MANUAL-{counter:04d}"
            counter += 1
        normalized[sid] = {
            "SubmissionID": sid,
            "FullName": str(row.get("FullName", "")).strip(),
            "EmailAddress": str(row.get("EmailAddress", "")).strip(),
            "Title": str(row.get("Title", "")).strip(),
            "Abstract": str(row.get("Abstract", "")).strip(),
            "Themes": str(row.get("Themes", "")).strip(),
            "LinkToPDF": str(row.get("LinkToPDF", "")).strip(),
            "ReviewerScore": str(row.get("ReviewerScore", "1")).strip() or "1",
            "UpdatedAt": str(row.get("UpdatedAt", "")).strip() or now,
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=MANUAL_TALKS_HEADERS)
        writer.writeheader()
        for sid in sorted(normalized.keys(), key=lambda x: (len(x), x)):
            writer.writerow(normalized[sid])


def _apply_paper_metadata_overrides(
    papers: Iterable[Paper],
    metadata_overrides: Dict[str, Dict[str, str]],
) -> None:
    if not metadata_overrides:
        return
    for paper in papers:
        row = metadata_overrides.get(paper.submission_id, {})
        if not row:
            continue
        title_override = str(row.get("TitleOverride", "")).strip()
        author_override = str(row.get("AuthorOverride", "")).strip()
        if title_override:
            paper.title = title_override
        if author_override:
            paper.full_name = author_override


def _parse_block_num_from_label(block_label: str, default: int = 0) -> int:
    match = re.search(r"(\d+)", str(block_label))
    if not match:
        return default
    try:
        return int(match.group(1))
    except Exception:
        return default


def _next_available_session_code(base_code: str, active_codes: set[str]) -> str:
    candidate = base_code
    suffix = 2
    while candidate in active_codes:
        candidate = f"{base_code}-{suffix}"
        suffix += 1
    return candidate


def validate_session_structure_rows(
    rows: Iterable[Dict[str, str]],
    config: ConferenceConfig = ACTIVE_CONFERENCE_CONFIG,
) -> List[str]:
    errors: List[str] = []
    seen_ids: set[str] = set()
    active_rows: List[Dict[str, str]] = []

    for row in rows:
        session_id = str(row.get("SessionId", "")).strip()
        if not session_id:
            errors.append("SessionId is required for all rows.")
            continue
        if session_id in seen_ids:
            errors.append(f"Duplicate SessionId detected: {session_id}")
            continue
        seen_ids.add(session_id)

        status = str(row.get("Status", "active")).strip().lower()
        if status not in {"active", "inactive"}:
            errors.append(f"Invalid Status for {session_id}: {status}")
            continue
        if status != "active":
            continue
        active_rows.append(row)

    if config.structure.enforce_unique_session_code:
        seen_codes: Dict[str, str] = {}
        for row in active_rows:
            session_id = str(row.get("SessionId", "")).strip()
            session_code = str(row.get("SessionCode", "")).strip()
            if not session_code:
                errors.append(f"Active session {session_id} must have SessionCode.")
                continue
            existing_id = seen_codes.get(session_code)
            if existing_id and existing_id != session_id:
                errors.append(f"Duplicate active SessionCode: {session_code}")
            else:
                seen_codes[session_code] = session_id

    if not config.structure.allow_duplicate_day_time_room:
        seen_slots: Dict[Tuple[str, str, str], str] = {}
        for row in active_rows:
            session_id = str(row.get("SessionId", "")).strip()
            day_num = str(row.get("DayNum", "")).strip()
            time_label = str(row.get("TimeLabel", "")).strip()
            room = str(row.get("Room", "")).strip()
            if not day_num or not time_label or not room:
                errors.append(f"Active session {session_id} must define DayNum, TimeLabel, and Room.")
                continue
            key = (day_num, time_label, room)
            existing_id = seen_slots.get(key)
            if existing_id and existing_id != session_id:
                errors.append(
                    f"Duplicate active slot DayNum={day_num}, TimeLabel={time_label}, Room={room}."
                )
            else:
                seen_slots[key] = session_id

    for row in active_rows:
        session_id = str(row.get("SessionId", "")).strip()
        capacity = _parse_positive_int(str(row.get("Capacity", "0")), default=0)
        if capacity <= 0:
            errors.append(f"Active session {session_id} must have Capacity >= 1.")
        start_min = _parse_positive_int(str(row.get("StartMin", "0")), default=0)
        end_min = _parse_positive_int(str(row.get("EndMin", "0")), default=0)
        if end_min <= start_min:
            errors.append(f"Active session {session_id} has invalid time bounds StartMin={start_min}, EndMin={end_min}.")

    return sorted(set(errors))


def clear_session(
    session_id: str,
    paper_placements_path: Path = PAPER_PLACEMENTS_FILE,
) -> Dict[str, object]:
    target_session_id = str(session_id).strip()
    if not target_session_id:
        return {"ok": False, "error": "SessionId is required."}

    placements = load_paper_placements(paper_placements_path)
    now = datetime.utcnow().isoformat(timespec="seconds")
    changed = 0
    for row in placements.values():
        if str(row.get("SessionId", "")).strip() != target_session_id:
            continue
        status = str(row.get("PlacementStatus", "")).strip().lower()
        if status not in {"scheduled", "overflow"}:
            continue
        row["PlacementStatus"] = "unassigned"
        row["SessionId"] = ""
        row["TalkIndex"] = ""
        row["OverflowOrder"] = ""
        row["UpdatedAt"] = now
        changed += 1

    if changed > 0:
        write_paper_placements(placements.values(), paper_placements_path)
    return {"ok": True, "moved_to_unassigned": changed}


def remove_session(
    session_id: str,
    session_structure_path: Path = SESSION_STRUCTURE_FILE,
    paper_placements_path: Path = PAPER_PLACEMENTS_FILE,
) -> Dict[str, object]:
    target_session_id = str(session_id).strip()
    if not target_session_id:
        return {"ok": False, "error": "SessionId is required."}

    rows = load_session_structure_rows(session_structure_path)
    target = rows.get(target_session_id)
    if target is None:
        return {"ok": False, "error": f"Session not found: {target_session_id}"}

    target["Status"] = "inactive"
    target["UpdatedAt"] = datetime.utcnow().isoformat(timespec="seconds")
    rows[target_session_id] = target
    write_session_structure_rows(rows.values(), session_structure_path)

    clear_result = clear_session(target_session_id, paper_placements_path)
    if not clear_result.get("ok", False):
        return clear_result
    return {
        "ok": True,
        "session_id": target_session_id,
        "session_code": str(target.get("SessionCode", "")).strip(),
        "moved_to_unassigned": int(clear_result.get("moved_to_unassigned", 0) or 0),
    }


def restore_session(
    session_id: str,
    session_structure_path: Path = SESSION_STRUCTURE_FILE,
    config_path: Optional[Path] = None,
) -> Dict[str, object]:
    target_session_id = str(session_id).strip()
    if not target_session_id:
        return {"ok": False, "error": "SessionId is required."}

    config = load_conference_config(config_path)
    rows = load_session_structure_rows(session_structure_path)
    target = rows.get(target_session_id)
    if target is None:
        return {"ok": False, "error": f"Session not found: {target_session_id}"}

    target["Status"] = "active"
    target["UpdatedAt"] = datetime.utcnow().isoformat(timespec="seconds")
    rows[target_session_id] = target

    errors = validate_session_structure_rows(rows.values(), config)
    if errors:
        return {"ok": False, "error": errors[0], "errors": errors}

    write_session_structure_rows(rows.values(), session_structure_path)
    return {
        "ok": True,
        "session_id": target_session_id,
        "session_code": str(target.get("SessionCode", "")).strip(),
    }


def create_session(
    day_label: str,
    block_label: str,
    time_label: str,
    room: str,
    capacity: int = 4,
    day_num: Optional[int] = None,
    block_num: Optional[int] = None,
    start_min: Optional[int] = None,
    end_min: Optional[int] = None,
    session_code: str = "",
    source: str = "manual",
    session_structure_path: Path = SESSION_STRUCTURE_FILE,
    config_path: Optional[Path] = None,
) -> Dict[str, object]:
    config = load_conference_config(config_path)
    rows = load_session_structure_rows(session_structure_path)
    now = datetime.utcnow().isoformat(timespec="seconds")

    day_label_clean = str(day_label).strip()
    block_label_clean = str(block_label).strip()
    time_label_clean = str(time_label).strip()
    room_clean = str(room).strip()
    if not (day_label_clean and time_label_clean and room_clean):
        return {"ok": False, "error": "DayLabel, TimeLabel, and Room are required."}

    resolved_day_num = int(day_num) if day_num is not None else config.day_to_num.get(day_label_clean, 0)
    if resolved_day_num <= 0:
        resolved_day_num = _parse_positive_int(str(day_num or ""), default=0)
    resolved_block_num = (
        int(block_num)
        if block_num is not None
        else _parse_block_num_from_label(block_label_clean, default=0)
    )
    resolved_start_min = int(start_min) if start_min is not None else parse_start_minutes(time_label_clean)
    resolved_end_min = (
        int(end_min)
        if end_min is not None
        else parse_end_minutes(time_label_clean, default_duration=config.structure.default_session_duration_min)
    )
    if resolved_end_min <= resolved_start_min:
        resolved_end_min = resolved_start_min + config.structure.default_session_duration_min
    resolved_capacity = _parse_positive_int(str(capacity), default=config.structure.default_session_capacity)

    active_rows = [row for row in rows.values() if str(row.get("Status", "active")).strip().lower() == "active"]
    active_codes = {str(row.get("SessionCode", "")).strip() for row in active_rows}
    base_code = str(session_code).strip() or _default_session_code(resolved_day_num, resolved_block_num, room_clean)
    if config.structure.enforce_unique_session_code and base_code in active_codes:
        if str(session_code).strip():
            return {"ok": False, "error": f"Active SessionCode already exists: {base_code}"}
        base_code = _next_available_session_code(base_code, active_codes)

    if not config.structure.allow_duplicate_day_time_room:
        duplicate = next(
            (
                row
                for row in active_rows
                if str(row.get("DayNum", "")).strip() == str(resolved_day_num)
                and str(row.get("TimeLabel", "")).strip() == time_label_clean
                and str(row.get("Room", "")).strip() == room_clean
            ),
            None,
        )
        if duplicate is not None:
            duplicate_code = str(duplicate.get("SessionCode", "")).strip()
            return {
                "ok": False,
                "error": (
                    "An active session already exists for the same day/time/room: "
                    f"{duplicate_code or duplicate.get('SessionId', '')}"
                ),
            }

    session_id = str(uuid.uuid4())
    rows[session_id] = {
        "SessionId": session_id,
        "SessionCode": base_code,
        "Status": "active",
        "DayLabel": day_label_clean,
        "DayNum": str(resolved_day_num),
        "BlockLabel": block_label_clean,
        "BlockNum": str(resolved_block_num),
        "TimeLabel": time_label_clean,
        "StartMin": str(resolved_start_min),
        "EndMin": str(resolved_end_min),
        "Room": room_clean,
        "Capacity": str(resolved_capacity),
        "Source": str(source).strip() or "manual",
        "UpdatedAt": now,
    }

    errors = validate_session_structure_rows(rows.values(), config)
    if errors:
        return {"ok": False, "error": errors[0], "errors": errors}

    write_session_structure_rows(rows.values(), session_structure_path)
    return {
        "ok": True,
        "session_id": session_id,
        "session_code": base_code,
    }


def add_room_session(
    day_label: str,
    block_label: str,
    time_label: str,
    room: str,
    capacity: int = 4,
    session_structure_path: Path = SESSION_STRUCTURE_FILE,
    config_path: Optional[Path] = None,
) -> Dict[str, object]:
    config = load_conference_config(config_path)
    start_min = parse_start_minutes(time_label)
    end_min = start_min + max(1, int(config.structure.default_session_duration_min))
    return create_session(
        day_label=day_label,
        block_label=block_label,
        time_label=time_label,
        room=room,
        capacity=capacity,
        start_min=start_min,
        end_min=end_min,
        source="manual",
        session_structure_path=session_structure_path,
        config_path=config_path,
    )


def bulk_add_room_sessions(
    room: str,
    capacity: int,
    day_labels: List[str],
    block_signatures: List[str],
    session_structure_path: Path = SESSION_STRUCTURE_FILE,
    config_path: Optional[Path] = None,
) -> Dict[str, object]:
    config = load_conference_config(config_path)
    rows = load_session_structure_rows(session_structure_path)
    now = datetime.utcnow().isoformat(timespec="seconds")
    room_clean = str(room).strip()
    if not room_clean:
        return {"ok": False, "error": "Room is required."}

    normalized_days = sorted({str(day).strip() for day in (day_labels or []) if str(day).strip()})
    normalized_signatures = sorted({str(sig).strip() for sig in (block_signatures or []) if str(sig).strip()})
    if not normalized_days:
        return {"ok": False, "error": "At least one day must be selected."}
    if not normalized_signatures:
        return {"ok": False, "error": "At least one block signature must be selected."}

    existing_by_slot: Dict[Tuple[str, str, str], Dict[str, str]] = {}
    for row in rows.values():
        key = (
            str(row.get("DayLabel", "")).strip(),
            str(row.get("TimeLabel", "")).strip(),
            str(row.get("Room", "")).strip(),
        )
        if key not in existing_by_slot:
            existing_by_slot[key] = row
        elif str(row.get("Status", "")).strip().lower() == "active":
            existing_by_slot[key] = row

    active_codes = {
        str(row.get("SessionCode", "")).strip()
        for row in rows.values()
        if str(row.get("Status", "active")).strip().lower() == "active" and str(row.get("SessionCode", "")).strip()
    }
    parsed_blocks: Dict[str, Tuple[int, str, str]] = {}
    parse_errors: List[str] = []
    for signature in normalized_signatures:
        try:
            parsed_blocks[signature] = parse_block_signature(signature)
        except Exception:
            parse_errors.append(f"Invalid block signature: {signature}")

    if parse_errors:
        return {"ok": False, "error": parse_errors[0], "errors": parse_errors}

    created: List[str] = []
    skipped_active: List[str] = []
    skipped_inactive: List[str] = []
    errors: List[str] = []
    resolved_capacity = _parse_positive_int(str(capacity), default=config.structure.default_session_capacity)
    default_duration = max(1, int(config.structure.default_session_duration_min))

    for day_label in normalized_days:
        resolved_day_num = int(config.day_to_num.get(day_label, 0))
        if resolved_day_num <= 0:
            day_rows = [row for row in rows.values() if str(row.get("DayLabel", "")).strip() == day_label]
            if day_rows:
                resolved_day_num = _parse_positive_int(day_rows[0].get("DayNum", ""), default=0)
        if resolved_day_num <= 0:
            errors.append(f"Unknown day label: {day_label}")
            continue

        for signature in normalized_signatures:
            block_num, block_label, time_label = parsed_blocks[signature]
            slot_key = (day_label, time_label, room_clean)
            existing = existing_by_slot.get(slot_key)
            if existing is not None:
                status = str(existing.get("Status", "active")).strip().lower()
                code = str(existing.get("SessionCode", "")).strip() or str(existing.get("SessionId", "")).strip()
                if status == "active":
                    skipped_active.append(code)
                else:
                    skipped_inactive.append(code)
                continue

            start_min = parse_start_minutes(time_label)
            end_min = start_min + default_duration
            base_code = _default_session_code(resolved_day_num, block_num, room_clean)
            session_code = base_code
            if config.structure.enforce_unique_session_code and session_code in active_codes:
                session_code = _next_available_session_code(base_code, active_codes)

            session_id = str(uuid.uuid4())
            new_row = {
                "SessionId": session_id,
                "SessionCode": session_code,
                "Status": "active",
                "DayLabel": day_label,
                "DayNum": str(resolved_day_num),
                "BlockLabel": block_label,
                "BlockNum": str(block_num),
                "TimeLabel": time_label,
                "StartMin": str(start_min),
                "EndMin": str(end_min),
                "Room": room_clean,
                "Capacity": str(resolved_capacity),
                "Source": "manual",
                "UpdatedAt": now,
            }
            rows[session_id] = new_row
            existing_by_slot[slot_key] = new_row
            active_codes.add(session_code)
            created.append(session_code)

    if not created and not errors:
        return {
            "ok": True,
            "created": 0,
            "created_codes": [],
            "skipped_active": len(skipped_active),
            "skipped_active_codes": sorted(skipped_active),
            "skipped_inactive": len(skipped_inactive),
            "skipped_inactive_codes": sorted(skipped_inactive),
            "errors": [],
        }

    validation_errors = validate_session_structure_rows(rows.values(), config)
    if validation_errors:
        return {"ok": False, "error": validation_errors[0], "errors": validation_errors}

    write_session_structure_rows(rows.values(), session_structure_path)
    return {
        "ok": True,
        "created": len(created),
        "created_codes": sorted(created),
        "skipped_active": len(skipped_active),
        "skipped_active_codes": sorted(skipped_active),
        "skipped_inactive": len(skipped_inactive),
        "skipped_inactive_codes": sorted(skipped_inactive),
        "errors": errors,
    }


def _resolve_day_num_for_label(
    day_label: str,
    rows: Dict[str, Dict[str, str]],
    config: ConferenceConfig,
) -> int:
    day_label_clean = str(day_label).strip()
    if not day_label_clean:
        return 0

    config_day_num = int(config.day_to_num.get(day_label_clean, 0))
    if config_day_num > 0:
        return config_day_num

    for row in rows.values():
        if str(row.get("DayLabel", "")).strip() != day_label_clean:
            continue
        parsed = _parse_positive_int(str(row.get("DayNum", "")).strip(), default=0)
        if parsed > 0:
            return parsed
    return 0


def _find_existing_session_for_slot(
    rows: Dict[str, Dict[str, str]],
    day_label: str,
    time_label: str,
    room: str,
) -> Optional[Dict[str, str]]:
    day_clean = str(day_label).strip()
    time_clean = str(time_label).strip()
    room_clean = str(room).strip()
    best: Optional[Dict[str, str]] = None
    for row in rows.values():
        if (
            str(row.get("DayLabel", "")).strip() != day_clean
            or str(row.get("TimeLabel", "")).strip() != time_clean
            or str(row.get("Room", "")).strip() != room_clean
        ):
            continue
        if best is None:
            best = row
            continue
        if str(row.get("Status", "active")).strip().lower() == "active":
            best = row
    return best


def rename_room_for_day(
    day_label: str,
    room: str,
    new_room: str,
    session_structure_path: Path = SESSION_STRUCTURE_FILE,
    config_path: Optional[Path] = None,
) -> Dict[str, object]:
    day_label_clean = str(day_label).strip()
    room_clean = str(room).strip()
    new_room_clean = str(new_room).strip()
    if not day_label_clean or not room_clean or not new_room_clean:
        return {"ok": False, "error": "Day label, room, and new room are required."}

    rows = load_session_structure_rows(session_structure_path)
    matched_ids = [
        session_id
        for session_id, row in rows.items()
        if str(row.get("DayLabel", "")).strip() == day_label_clean
        and str(row.get("Room", "")).strip() == room_clean
    ]
    if not matched_ids:
        return {"ok": False, "error": f"No sessions found for {day_label_clean} / {room_clean}."}

    if room_clean == new_room_clean:
        return {"ok": True, "updated": 0, "updated_session_ids": [], "errors": []}

    now = datetime.utcnow().isoformat(timespec="seconds")
    updated_ids: List[str] = []
    for session_id in matched_ids:
        row = dict(rows[session_id])
        row["Room"] = new_room_clean
        row["UpdatedAt"] = now
        rows[session_id] = row
        updated_ids.append(session_id)

    config = load_conference_config(config_path)
    validation_errors = validate_session_structure_rows(rows.values(), config)
    if validation_errors:
        return {"ok": False, "error": validation_errors[0], "errors": validation_errors}

    write_session_structure_rows(rows.values(), session_structure_path)
    return {
        "ok": True,
        "updated": len(updated_ids),
        "updated_session_ids": sorted(updated_ids),
        "errors": [],
    }


def add_block_row_sessions(
    day_label: str,
    block_label: str,
    start_min: int,
    duration_min: int,
    capacity: int,
    block_num: Optional[int] = None,
    source: str = "manual",
    session_structure_path: Path = SESSION_STRUCTURE_FILE,
    config_path: Optional[Path] = None,
) -> Dict[str, object]:
    day_label_clean = str(day_label).strip()
    if not day_label_clean:
        return {"ok": False, "error": "Day label is required."}

    config = load_conference_config(config_path)
    rows = load_session_structure_rows(session_structure_path)
    day_rows = [
        row
        for row in rows.values()
        if str(row.get("DayLabel", "")).strip() == day_label_clean and str(row.get("Room", "")).strip()
    ]
    if not day_rows:
        return {"ok": False, "error": f"No day sessions found for {day_label_clean}."}

    rooms = sorted({str(row.get("Room", "")).strip() for row in day_rows if str(row.get("Room", "")).strip()}, key=room_sort_key)
    if not rooms:
        return {"ok": False, "error": f"No rooms found for {day_label_clean}."}

    resolved_day_num = _resolve_day_num_for_label(day_label_clean, rows, config)
    if resolved_day_num <= 0:
        return {"ok": False, "error": f"Unable to resolve day number for {day_label_clean}."}

    max_block_num = max(
        _parse_positive_int(str(row.get("BlockNum", "")).strip(), default=0)
        for row in day_rows
    )
    resolved_block_num = int(block_num) if block_num is not None else max_block_num + 1
    if resolved_block_num <= 0:
        resolved_block_num = max(1, max_block_num + 1)

    start_min_resolved = _parse_nonnegative_int(str(start_min), default=0)
    duration_resolved = max(
        1,
        _parse_positive_int(str(duration_min), default=config.structure.default_session_duration_min),
    )
    end_min_resolved = start_min_resolved + duration_resolved
    time_label = build_time_label(start_min_resolved, end_min_resolved)
    block_label_clean = str(block_label).strip() or f"SESSION {resolved_block_num}"
    capacity_resolved = _parse_positive_int(str(capacity), default=config.structure.default_session_capacity)
    source_clean = str(source).strip() or "manual"

    active_codes = {
        str(row.get("SessionCode", "")).strip()
        for row in rows.values()
        if str(row.get("Status", "active")).strip().lower() == "active" and str(row.get("SessionCode", "")).strip()
    }
    now = datetime.utcnow().isoformat(timespec="seconds")
    created_codes: List[str] = []
    skipped_active: List[str] = []
    skipped_inactive: List[str] = []

    for room_name in rooms:
        existing = _find_existing_session_for_slot(rows, day_label_clean, time_label, room_name)
        if existing is not None:
            status = str(existing.get("Status", "active")).strip().lower()
            existing_code = str(existing.get("SessionCode", "")).strip() or str(existing.get("SessionId", "")).strip()
            if status == "active":
                skipped_active.append(existing_code)
            else:
                skipped_inactive.append(existing_code)
            continue

        base_code = _default_session_code(resolved_day_num, resolved_block_num, room_name)
        session_code = base_code
        if config.structure.enforce_unique_session_code and session_code in active_codes:
            session_code = _next_available_session_code(base_code, active_codes)

        session_id = str(uuid.uuid4())
        rows[session_id] = {
            "SessionId": session_id,
            "SessionCode": session_code,
            "Status": "active",
            "DayLabel": day_label_clean,
            "DayNum": str(resolved_day_num),
            "BlockLabel": block_label_clean,
            "BlockNum": str(resolved_block_num),
            "TimeLabel": time_label,
            "StartMin": str(start_min_resolved),
            "EndMin": str(end_min_resolved),
            "Room": room_name,
            "Capacity": str(capacity_resolved),
            "Source": source_clean,
            "UpdatedAt": now,
        }
        active_codes.add(session_code)
        created_codes.append(session_code)

    if not created_codes:
        return {
            "ok": True,
            "created": 0,
            "created_codes": [],
            "skipped_active": len(skipped_active),
            "skipped_active_codes": sorted(skipped_active),
            "skipped_inactive": len(skipped_inactive),
            "skipped_inactive_codes": sorted(skipped_inactive),
            "errors": [],
        }

    validation_errors = validate_session_structure_rows(rows.values(), config)
    if validation_errors:
        return {"ok": False, "error": validation_errors[0], "errors": validation_errors}

    write_session_structure_rows(rows.values(), session_structure_path)
    return {
        "ok": True,
        "created": len(created_codes),
        "created_codes": sorted(created_codes),
        "skipped_active": len(skipped_active),
        "skipped_active_codes": sorted(skipped_active),
        "skipped_inactive": len(skipped_inactive),
        "skipped_inactive_codes": sorted(skipped_inactive),
        "errors": [],
    }


def clone_day_structure(
    source_day_label: str,
    target_day_label: str,
    target_day_num: Optional[int] = None,
    session_structure_path: Path = SESSION_STRUCTURE_FILE,
    config_path: Optional[Path] = None,
) -> Dict[str, object]:
    source_day_clean = str(source_day_label).strip()
    target_day_clean = str(target_day_label).strip()
    if not source_day_clean or not target_day_clean:
        return {"ok": False, "error": "Source and target day labels are required."}

    config = load_conference_config(config_path)
    rows = load_session_structure_rows(session_structure_path)
    source_rows = [
        row
        for row in rows.values()
        if str(row.get("DayLabel", "")).strip() == source_day_clean
        and str(row.get("Status", "active")).strip().lower() == "active"
    ]
    if not source_rows:
        return {"ok": False, "error": f"No active sessions found for source day {source_day_clean}."}

    resolved_target_day_num = int(target_day_num) if target_day_num is not None else 0
    if resolved_target_day_num <= 0:
        resolved_target_day_num = _resolve_day_num_for_label(target_day_clean, rows, config)
    if resolved_target_day_num <= 0:
        return {"ok": False, "error": f"Unable to resolve target day number for {target_day_clean}."}

    active_codes = {
        str(row.get("SessionCode", "")).strip()
        for row in rows.values()
        if str(row.get("Status", "active")).strip().lower() == "active" and str(row.get("SessionCode", "")).strip()
    }
    created_codes: List[str] = []
    skipped_active: List[str] = []
    skipped_inactive: List[str] = []
    errors: List[str] = []
    now = datetime.utcnow().isoformat(timespec="seconds")

    ordered_source_rows = sorted(
        source_rows,
        key=lambda row: (
            _parse_positive_int(str(row.get("BlockNum", "")).strip(), default=0),
            _parse_nonnegative_int(str(row.get("StartMin", "")).strip(), default=0),
            room_sort_key(str(row.get("Room", "")).strip()),
        ),
    )
    for row in ordered_source_rows:
        block_num = _parse_positive_int(str(row.get("BlockNum", "")).strip(), default=0)
        block_label = str(row.get("BlockLabel", "")).strip()
        time_label = str(row.get("TimeLabel", "")).strip()
        start_min = _parse_nonnegative_int(str(row.get("StartMin", "")).strip(), default=parse_start_minutes(time_label))
        end_min = _parse_positive_int(
            str(row.get("EndMin", "")).strip(),
            default=max(start_min + 1, parse_end_minutes(time_label, default_duration=config.structure.default_session_duration_min)),
        )
        if end_min <= start_min:
            end_min = start_min + max(1, int(config.structure.default_session_duration_min))
        room = str(row.get("Room", "")).strip()
        if not time_label or not room or block_num <= 0:
            errors.append(f"Skipped invalid source row with room/time/block: {row.get('SessionId', '')}")
            continue

        existing = _find_existing_session_for_slot(rows, target_day_clean, time_label, room)
        if existing is not None:
            status = str(existing.get("Status", "active")).strip().lower()
            existing_code = str(existing.get("SessionCode", "")).strip() or str(existing.get("SessionId", "")).strip()
            if status == "active":
                skipped_active.append(existing_code)
            else:
                skipped_inactive.append(existing_code)
            continue

        base_code = _default_session_code(resolved_target_day_num, block_num, room)
        session_code = base_code
        if config.structure.enforce_unique_session_code and session_code in active_codes:
            session_code = _next_available_session_code(base_code, active_codes)

        session_id = str(uuid.uuid4())
        rows[session_id] = {
            "SessionId": session_id,
            "SessionCode": session_code,
            "Status": "active",
            "DayLabel": target_day_clean,
            "DayNum": str(resolved_target_day_num),
            "BlockLabel": block_label,
            "BlockNum": str(block_num),
            "TimeLabel": time_label,
            "StartMin": str(start_min),
            "EndMin": str(end_min),
            "Room": room,
            "Capacity": str(
                _parse_positive_int(
                    str(row.get("Capacity", "")).strip(),
                    default=config.structure.default_session_capacity,
                )
            ),
            "Source": str(row.get("Source", "")).strip() or "manual",
            "UpdatedAt": now,
        }
        active_codes.add(session_code)
        created_codes.append(session_code)

    if not created_codes and not errors:
        return {
            "ok": True,
            "created": 0,
            "created_codes": [],
            "skipped_active": len(skipped_active),
            "skipped_active_codes": sorted(skipped_active),
            "skipped_inactive": len(skipped_inactive),
            "skipped_inactive_codes": sorted(skipped_inactive),
            "errors": [],
        }

    validation_errors = validate_session_structure_rows(rows.values(), config)
    if validation_errors:
        return {"ok": False, "error": validation_errors[0], "errors": validation_errors}

    write_session_structure_rows(rows.values(), session_structure_path)
    return {
        "ok": True,
        "created": len(created_codes),
        "created_codes": sorted(created_codes),
        "skipped_active": len(skipped_active),
        "skipped_active_codes": sorted(skipped_active),
        "skipped_inactive": len(skipped_inactive),
        "skipped_inactive_codes": sorted(skipped_inactive),
        "errors": errors,
    }


def clear_day_sessions(
    day_label: str,
    session_structure_path: Path = SESSION_STRUCTURE_FILE,
    paper_placements_path: Path = PAPER_PLACEMENTS_FILE,
) -> Dict[str, object]:
    day_label_clean = str(day_label).strip()
    if not day_label_clean:
        return {"ok": False, "error": "Day label is required."}

    rows = load_session_structure_rows(session_structure_path)
    target_session_ids = {
        str(row.get("SessionId", "")).strip()
        for row in rows.values()
        if str(row.get("DayLabel", "")).strip() == day_label_clean
    }
    target_session_ids.discard("")
    if not target_session_ids:
        return {"ok": False, "error": f"No sessions found for day {day_label_clean}."}

    placements = load_paper_placements(paper_placements_path)
    now = datetime.utcnow().isoformat(timespec="seconds")
    moved = 0
    for row in placements.values():
        if str(row.get("SessionId", "")).strip() not in target_session_ids:
            continue
        status = str(row.get("PlacementStatus", "")).strip().lower()
        if status not in {"scheduled", "overflow"}:
            continue
        row["PlacementStatus"] = "unassigned"
        row["SessionId"] = ""
        row["TalkIndex"] = ""
        row["OverflowOrder"] = ""
        row["UpdatedAt"] = now
        moved += 1

    if moved > 0:
        write_paper_placements(placements.values(), paper_placements_path)

    return {
        "ok": True,
        "updated": moved,
        "moved_to_unassigned": moved,
        "session_count": len(target_session_ids),
    }


def delete_day_sessions(
    day_label: str,
    session_structure_path: Path = SESSION_STRUCTURE_FILE,
    paper_placements_path: Path = PAPER_PLACEMENTS_FILE,
) -> Dict[str, object]:
    day_label_clean = str(day_label).strip()
    if not day_label_clean:
        return {"ok": False, "error": "Day label is required."}

    rows = load_session_structure_rows(session_structure_path)
    removed_session_ids = {
        session_id
        for session_id, row in rows.items()
        if str(row.get("DayLabel", "")).strip() == day_label_clean
    }
    if not removed_session_ids:
        return {"ok": False, "error": f"No sessions found for day {day_label_clean}."}

    remaining_rows = {session_id: row for session_id, row in rows.items() if session_id not in removed_session_ids}
    placements = load_paper_placements(paper_placements_path)
    now = datetime.utcnow().isoformat(timespec="seconds")
    moved = 0
    for row in placements.values():
        if str(row.get("SessionId", "")).strip() not in removed_session_ids:
            continue
        status = str(row.get("PlacementStatus", "")).strip().lower()
        if status not in {"scheduled", "overflow"}:
            continue
        row["PlacementStatus"] = "unassigned"
        row["SessionId"] = ""
        row["TalkIndex"] = ""
        row["OverflowOrder"] = ""
        row["UpdatedAt"] = now
        moved += 1

    if moved > 0:
        write_paper_placements(placements.values(), paper_placements_path)
    write_session_structure_rows(remaining_rows.values(), session_structure_path)
    return {
        "ok": True,
        "deleted": len(removed_session_ids),
        "deleted_session_ids": sorted(removed_session_ids),
        "moved_to_unassigned": moved,
    }


def relabel_day_sessions(
    day_label: str,
    new_day_label: str,
    new_day_num: int,
    session_structure_path: Path = SESSION_STRUCTURE_FILE,
    session_name_overrides_path: Path = SESSION_NAME_OVERRIDES_FILE,
    config_path: Optional[Path] = None,
) -> Dict[str, object]:
    day_label_clean = str(day_label).strip()
    new_day_label_clean = str(new_day_label).strip()
    resolved_new_day_num = _parse_positive_int(str(new_day_num), default=0)
    if not day_label_clean or not new_day_label_clean or resolved_new_day_num <= 0:
        return {"ok": False, "error": "Day label, new day label, and new day number are required."}

    rows = load_session_structure_rows(session_structure_path)
    target_ids = [
        session_id
        for session_id, row in rows.items()
        if str(row.get("DayLabel", "")).strip() == day_label_clean
    ]
    if not target_ids:
        return {"ok": False, "error": f"No sessions found for day {day_label_clean}."}

    assigned_codes = {
        str(row.get("SessionCode", "")).strip()
        for session_id, row in rows.items()
        if session_id not in target_ids and str(row.get("SessionCode", "")).strip()
    }
    now = datetime.utcnow().isoformat(timespec="seconds")
    ordered_target_ids = sorted(
        target_ids,
        key=lambda session_id: (
            _parse_positive_int(str(rows[session_id].get("BlockNum", "")).strip(), default=0),
            _parse_nonnegative_int(str(rows[session_id].get("StartMin", "")).strip(), default=0),
            room_sort_key(str(rows[session_id].get("Room", "")).strip()),
            str(rows[session_id].get("SessionId", "")).strip(),
        ),
    )

    moved_overrides: List[Tuple[str, str]] = []
    updated = 0
    for session_id in ordered_target_ids:
        row = dict(rows[session_id])
        block_num = _parse_positive_int(
            str(row.get("BlockNum", "")).strip(),
            default=_parse_block_num_from_label(str(row.get("BlockLabel", "")).strip(), default=0),
        )
        room = str(row.get("Room", "")).strip()
        base_code = _default_session_code(resolved_new_day_num, block_num, room)
        new_code = base_code
        if new_code in assigned_codes:
            new_code = _next_available_session_code(base_code, assigned_codes)
        assigned_codes.add(new_code)

        old_code = str(row.get("SessionCode", "")).strip()
        if old_code and old_code != new_code:
            moved_overrides.append((old_code, new_code))

        changed = (
            str(row.get("DayLabel", "")).strip() != new_day_label_clean
            or str(row.get("DayNum", "")).strip() != str(resolved_new_day_num)
            or old_code != new_code
        )
        row["DayLabel"] = new_day_label_clean
        row["DayNum"] = str(resolved_new_day_num)
        row["SessionCode"] = new_code
        if changed:
            row["UpdatedAt"] = now
            updated += 1
        rows[session_id] = row

    config = load_conference_config(config_path)
    validation_errors = validate_session_structure_rows(rows.values(), config)
    if validation_errors:
        return {"ok": False, "error": validation_errors[0], "errors": validation_errors}

    session_name_overrides = load_session_name_overrides(session_name_overrides_path)
    migrated_overrides = 0
    if moved_overrides and session_name_overrides:
        rewritten_overrides = dict(session_name_overrides)
        for old_code, new_code in moved_overrides:
            title = str(session_name_overrides.get(old_code, "")).strip()
            if not title:
                continue
            rewritten_overrides.pop(old_code, None)
            rewritten_overrides[new_code] = title
            migrated_overrides += 1
    else:
        rewritten_overrides = session_name_overrides

    write_session_structure_rows(rows.values(), session_structure_path)
    if migrated_overrides > 0:
        write_session_name_overrides(rewritten_overrides, session_name_overrides_path)

    return {
        "ok": True,
        "updated": updated,
        "migrated_overrides": migrated_overrides,
        "errors": [],
    }


def transfer_session_content(
    source_session_id: str,
    target_session_id: str,
    mode: str,
    session_structure_path: Path = SESSION_STRUCTURE_FILE,
    paper_placements_path: Path = PAPER_PLACEMENTS_FILE,
    session_name_overrides_path: Path = SESSION_NAME_OVERRIDES_FILE,
    config_path: Optional[Path] = None,
    source_effective_title: str = "",
    target_effective_title: str = "",
) -> Dict[str, object]:
    source_id = str(source_session_id).strip()
    target_id = str(target_session_id).strip()
    mode_clean = str(mode).strip().lower()
    if not source_id or not target_id:
        return {"ok": False, "error": "Source and target SessionId are required."}
    if source_id == target_id:
        return {"ok": False, "error": "Source and target sessions must be different."}
    if mode_clean not in {"replace", "swap"}:
        return {"ok": False, "error": "Transfer mode must be 'replace' or 'swap'."}

    rows = load_session_structure_rows(session_structure_path)
    source_row = rows.get(source_id)
    target_row = rows.get(target_id)
    if source_row is None:
        return {"ok": False, "error": f"Source session not found: {source_id}"}
    if target_row is None:
        return {"ok": False, "error": f"Target session not found: {target_id}"}

    source_code = str(source_row.get("SessionCode", "")).strip()
    target_code = str(target_row.get("SessionCode", "")).strip()
    source_status = str(source_row.get("Status", "active")).strip().lower()
    target_status = str(target_row.get("Status", "active")).strip().lower()
    warnings: List[str] = []
    if source_status != "active" or target_status != "active":
        warnings.append(
            "Transfer involves inactive session(s). "
            f"Source={source_code or source_id} ({source_status or 'unknown'}), "
            f"Target={target_code or target_id} ({target_status or 'unknown'})."
        )

    placements = load_paper_placements(paper_placements_path)
    source_assignments: Dict[str, Dict[str, str]] = {}
    target_assignments: Dict[str, Dict[str, str]] = {}
    for submission_id, row in placements.items():
        session_id = str(row.get("SessionId", "")).strip()
        status = str(row.get("PlacementStatus", "")).strip().lower()
        if status not in {"scheduled", "overflow"}:
            continue
        if session_id == source_id:
            source_assignments[submission_id] = dict(row)
        elif session_id == target_id:
            target_assignments[submission_id] = dict(row)

    def _max_scheduled_talk_index(rows_by_submission_id: Dict[str, Dict[str, str]]) -> int:
        max_idx = 0
        for row in rows_by_submission_id.values():
            status = str(row.get("PlacementStatus", "")).strip().lower()
            if status != "scheduled":
                continue
            max_idx = max(max_idx, _parse_positive_int(str(row.get("TalkIndex", "")).strip(), default=0))
        return max_idx

    now = datetime.utcnow().isoformat(timespec="seconds")
    source_capacity = _parse_positive_int(str(source_row.get("Capacity", "")).strip(), default=1)
    target_capacity = _parse_positive_int(str(target_row.get("Capacity", "")).strip(), default=1)
    max_source_talk_index = _max_scheduled_talk_index(source_assignments)
    max_target_talk_index = _max_scheduled_talk_index(target_assignments)

    capacity_updates = 0
    updated_session_ids: set[str] = set()
    if mode_clean == "replace":
        resolved_target_capacity = max(target_capacity, source_capacity, max_source_talk_index, 1)
        if resolved_target_capacity != target_capacity:
            target_row = dict(target_row)
            target_row["Capacity"] = str(resolved_target_capacity)
            target_row["UpdatedAt"] = now
            rows[target_id] = target_row
            capacity_updates += 1
            updated_session_ids.add(target_id)
    else:
        resolved_source_capacity = max(source_capacity, max_target_talk_index, 1)
        resolved_target_capacity = max(target_capacity, max_source_talk_index, 1)
        if resolved_source_capacity != source_capacity:
            source_row = dict(source_row)
            source_row["Capacity"] = str(resolved_source_capacity)
            source_row["UpdatedAt"] = now
            rows[source_id] = source_row
            capacity_updates += 1
            updated_session_ids.add(source_id)
        if resolved_target_capacity != target_capacity:
            target_row = dict(target_row)
            target_row["Capacity"] = str(resolved_target_capacity)
            target_row["UpdatedAt"] = now
            rows[target_id] = target_row
            capacity_updates += 1
            updated_session_ids.add(target_id)

    overrides = load_session_name_overrides(session_name_overrides_path)
    rewritten_overrides = dict(overrides)
    title_updates = 0
    source_title = str(source_effective_title).strip()
    target_title = str(target_effective_title).strip()

    def _set_session_title_override(session_code: str, title: str) -> int:
        code = str(session_code).strip()
        if not code:
            return 0
        desired = str(title).strip()
        current = str(rewritten_overrides.get(code, "")).strip()
        if desired:
            if current == desired:
                return 0
            rewritten_overrides[code] = desired
            return 1
        if code not in rewritten_overrides:
            return 0
        rewritten_overrides.pop(code, None)
        return 1

    if mode_clean == "replace":
        title_updates += _set_session_title_override(target_code, source_title)
        title_updates += _set_session_title_override(source_code, "")
    else:
        title_updates += _set_session_title_override(source_code, target_title)
        title_updates += _set_session_title_override(target_code, source_title)

    moved_to_target = 0
    moved_to_source = 0
    unassigned_from_target = 0
    changed_submission_ids: set[str] = set()

    def _rewrite_for_session(row: Dict[str, str], session_id: str) -> Dict[str, str]:
        status = str(row.get("PlacementStatus", "")).strip().lower()
        updated = dict(row)
        updated["SessionId"] = str(session_id).strip()
        if status == "scheduled":
            updated["TalkIndex"] = str(row.get("TalkIndex", "")).strip()
            updated["OverflowOrder"] = ""
        elif status == "overflow":
            updated["TalkIndex"] = ""
            updated["OverflowOrder"] = str(row.get("OverflowOrder", "")).strip()
        else:
            updated["PlacementStatus"] = "unassigned"
            updated["SessionId"] = ""
            updated["TalkIndex"] = ""
            updated["OverflowOrder"] = ""
        updated["UpdatedAt"] = now
        return updated

    if mode_clean == "replace":
        for submission_id, row in target_assignments.items():
            updated = dict(row)
            updated["PlacementStatus"] = "unassigned"
            updated["SessionId"] = ""
            updated["TalkIndex"] = ""
            updated["OverflowOrder"] = ""
            updated["UpdatedAt"] = now
            placements[submission_id] = updated
            unassigned_from_target += 1
            changed_submission_ids.add(submission_id)
        for submission_id, row in source_assignments.items():
            placements[submission_id] = _rewrite_for_session(row, target_id)
            moved_to_target += 1
            changed_submission_ids.add(submission_id)
    else:
        for submission_id, row in source_assignments.items():
            placements[submission_id] = _rewrite_for_session(row, target_id)
            moved_to_target += 1
            changed_submission_ids.add(submission_id)
        for submission_id, row in target_assignments.items():
            placements[submission_id] = _rewrite_for_session(row, source_id)
            moved_to_source += 1
            changed_submission_ids.add(submission_id)

    config = load_conference_config(config_path)
    validation_errors = validate_session_structure_rows(rows.values(), config)
    if validation_errors:
        return {"ok": False, "error": validation_errors[0], "errors": validation_errors}

    if updated_session_ids:
        write_session_structure_rows(rows.values(), session_structure_path)
    if changed_submission_ids:
        write_paper_placements(placements.values(), paper_placements_path)
    if title_updates > 0:
        write_session_name_overrides(rewritten_overrides, session_name_overrides_path)

    return {
        "ok": True,
        "mode": mode_clean,
        "source_session_id": source_id,
        "target_session_id": target_id,
        "source_session_code": source_code,
        "target_session_code": target_code,
        "moved_to_target": moved_to_target,
        "moved_to_source": moved_to_source,
        "unassigned_from_target": unassigned_from_target,
        "capacity_updates": capacity_updates,
        "title_updates": title_updates,
        "warnings": warnings,
    }


def update_session_structure_row(
    session_id: str,
    updates: Dict[str, object],
    session_structure_path: Path = SESSION_STRUCTURE_FILE,
    config_path: Optional[Path] = None,
) -> Dict[str, object]:
    target_session_id = str(session_id).strip()
    if not target_session_id:
        return {"ok": False, "error": "SessionId is required."}

    config = load_conference_config(config_path)
    rows = load_session_structure_rows(session_structure_path)
    row = rows.get(target_session_id)
    if row is None:
        return {"ok": False, "error": f"Session not found: {target_session_id}"}

    candidate = dict(row)
    for key in [
        "SessionCode",
        "Status",
        "DayLabel",
        "DayNum",
        "BlockLabel",
        "BlockNum",
        "TimeLabel",
        "StartMin",
        "EndMin",
        "Room",
        "Capacity",
        "Source",
    ]:
        if key not in updates:
            continue
        candidate[key] = str(updates.get(key, "")).strip()

    if "DayNum" not in updates and candidate.get("DayLabel", "").strip():
        day_num = config.day_to_num.get(candidate["DayLabel"].strip(), 0)
        if day_num > 0:
            candidate["DayNum"] = str(day_num)
    if "BlockNum" not in updates:
        candidate["BlockNum"] = str(
            _parse_positive_int(candidate.get("BlockNum", ""), default=_parse_block_num_from_label(candidate.get("BlockLabel", ""), default=0))
        )
    if "StartMin" not in updates:
        candidate["StartMin"] = str(
            _parse_positive_int(candidate.get("StartMin", ""), default=parse_start_minutes(candidate.get("TimeLabel", "")))
        )
    if "EndMin" not in updates:
        candidate["EndMin"] = str(
            _parse_positive_int(
                candidate.get("EndMin", ""),
                default=parse_end_minutes(
                    candidate.get("TimeLabel", ""),
                    default_duration=config.structure.default_session_duration_min,
                ),
            )
        )
    if _parse_nonnegative_int(candidate.get("EndMin", ""), default=0) <= _parse_nonnegative_int(candidate.get("StartMin", ""), default=0):
        candidate["EndMin"] = str(
            _parse_nonnegative_int(candidate.get("StartMin", ""), default=0)
            + max(1, int(config.structure.default_session_duration_min))
        )
    if "Capacity" not in updates:
        candidate["Capacity"] = str(
            _parse_positive_int(candidate.get("Capacity", ""), default=config.structure.default_session_capacity)
        )

    candidate["UpdatedAt"] = datetime.utcnow().isoformat(timespec="seconds")
    rows[target_session_id] = candidate
    errors = validate_session_structure_rows(rows.values(), config)
    if errors:
        return {"ok": False, "error": errors[0], "errors": errors}

    write_session_structure_rows(rows.values(), session_structure_path)
    return {"ok": True, "session_id": target_session_id, "session_code": candidate.get("SessionCode", "")}


def create_manual_talk(
    full_name: str,
    title: str,
    abstract: str = "",
    themes: str = "",
    email: str = "",
    link_to_pdf: str = "",
    reviewer_score: str = "1",
    submission_id: str = "",
    manual_talks_path: Path = MANUAL_TALKS_FILE,
    paper_placements_path: Path = PAPER_PLACEMENTS_FILE,
) -> Dict[str, object]:
    name = str(full_name).strip()
    talk_title = str(title).strip()
    if not name or not talk_title:
        return {"ok": False, "error": "Full name and title are required for manual talks."}

    existing_rows = _load_csv_rows(manual_talks_path, MANUAL_TALKS_HEADERS)
    existing_ids = {str(row.get("SubmissionID", "")).strip() for row in existing_rows}

    sid = str(submission_id).strip()
    if not sid:
        sid = f"MANUAL-{uuid.uuid4().hex[:8].upper()}"
    if sid in existing_ids:
        return {"ok": False, "error": f"SubmissionID already exists in manual talks: {sid}"}

    now = datetime.utcnow().isoformat(timespec="seconds")
    existing_rows.append(
        {
            "SubmissionID": sid,
            "FullName": name,
            "EmailAddress": str(email).strip(),
            "Title": talk_title,
            "Abstract": str(abstract).strip(),
            "Themes": str(themes).strip(),
            "LinkToPDF": str(link_to_pdf).strip(),
            "ReviewerScore": str(reviewer_score).strip() or "1",
            "UpdatedAt": now,
        }
    )
    write_manual_talks(existing_rows, manual_talks_path)

    placements = load_paper_placements(paper_placements_path)
    if sid not in placements:
        placements[sid] = {
            "SubmissionID": sid,
            "PlacementStatus": "unassigned",
            "SessionId": "",
            "TalkIndex": "",
            "OverflowOrder": "",
            "UpdatedAt": now,
        }
        write_paper_placements(placements.values(), paper_placements_path)

    return {"ok": True, "submission_id": sid}


def classify_papers(
    papers: List[Paper],
    classification_overrides: Optional[Dict[str, Dict[str, str]]] = None,
) -> None:
    classify_papers_core(
        papers,
        classification_overrides,
        normalize_key=normalize_key,
        map_source_themes=map_source_themes,
        infer_theme_from_text=infer_theme_from_text,
        classify_subtheme=classify_subtheme,
        keyword_matches=keyword_matches,
        theme_keywords=THEME_KEYWORDS,
        parse_bool=parse_bool,
        empty_label_sentinel=EMPTY_LABEL_SENTINEL,
    )


def build_packed_groups(papers: List[Paper]) -> List[PackedGroup]:
    ordered = sorted(
        papers,
        key=lambda p: (
            THEME_ORDER.index(p.primary_theme) if p.primary_theme in THEME_ORDER else len(THEME_ORDER),
            p.detailed_subtheme.lower(),
            p.title.lower(),
            p.submission_id,
        ),
    )

    groups: List[List[Optional[Paper]]] = []
    idx = 0
    for size in build_group_slices(len(ordered)):
        grp = ordered[idx : idx + size]
        idx += size
        groups.append(grp + [None] * (4 - len(grp)))

    if idx != len(ordered):
        raise RuntimeError("Unexpected paper-to-session packing mismatch")

    out: List[PackedGroup] = []
    title_counter: Dict[str, int] = defaultdict(int)
    for gidx, grp in enumerate(groups, start=1):
        non_null = [p for p in grp if p is not None]
        primary_counts = Counter([p.primary_theme for p in non_null])
        subtheme_counts = Counter([p.detailed_subtheme for p in non_null])
        dominant_primary = primary_counts.most_common(1)[0][0]
        dominant_subtheme = subtheme_counts.most_common(1)[0][0]

        base_title = f"{THEME_SHORT.get(dominant_primary, dominant_primary)}: {dominant_subtheme}"
        title_counter[base_title] += 1
        title_num = title_counter[base_title]
        auto_title = base_title if title_num == 1 else f"{base_title} ({title_num})"

        out.append(
            PackedGroup(
                index=gidx,
                papers=grp,
                dominant_primary=dominant_primary,
                dominant_subtheme=dominant_subtheme,
                auto_title=auto_title,
            )
        )

    return out


def interleave_groups(groups: List[PackedGroup]) -> List[PackedGroup]:
    buckets: Dict[str, List[PackedGroup]] = {theme: [] for theme in THEME_ORDER}
    for group in groups:
        buckets.setdefault(group.dominant_primary, []).append(group)

    out: List[PackedGroup] = []
    while True:
        added = False
        for theme in THEME_ORDER:
            if buckets.get(theme):
                out.append(buckets[theme].pop(0))
                added = True
        if not added:
            break
    return out


def assign_groups_to_slots(
    groups: List[PackedGroup],
    slots: List[Slot],
    session_name_overrides: Optional[Dict[str, str]] = None,
) -> List[Session]:
    if len(groups) != len(slots):
        raise RuntimeError(f"Slots/groups mismatch: {len(slots)} slots for {len(groups)} groups")

    remaining = interleave_groups(groups)
    theme_remaining = Counter([g.dominant_primary for g in remaining])

    block_slices: List[Tuple[int, int]] = []
    i = 0
    while i < len(slots):
        j = i + 1
        while (
            j < len(slots)
            and slots[j].day_num == slots[i].day_num
            and slots[j].row_in_source == slots[i].row_in_source
            and slots[j].time == slots[i].time
            and slots[j].block_label == slots[i].block_label
        ):
            j += 1
        block_slices.append((i, j))
        i = j

    sessions: List[Session] = []
    slot_idx = 0
    for block_start, block_end in block_slices:
        block_theme_count = Counter()
        block_size = block_end - block_start

        for _ in range(block_size):
            best_idx = 0
            best_score: Optional[float] = None
            for idx, group in enumerate(remaining):
                theme = group.dominant_primary
                score = theme_remaining[theme] * 10 - block_theme_count[theme] * 7 - idx * 0.01
                if best_score is None or score > best_score:
                    best_score = score
                    best_idx = idx

            chosen = remaining.pop(best_idx)
            theme_remaining[chosen.dominant_primary] -= 1
            block_theme_count[chosen.dominant_primary] += 1

            slot = slots[slot_idx]
            slot_idx += 1
            session_code = slot.session_code
            session_title = chosen.auto_title
            if session_name_overrides and session_code in session_name_overrides:
                session_title = session_name_overrides[session_code]

            session = Session(
                session_id=str(uuid.uuid5(uuid.NAMESPACE_DNS, f"session:{session_code}")),
                session_code=session_code,
                status="active",
                day_label=slot.day_label,
                day_num=slot.day_num,
                time=slot.time,
                block_label=slot.block_label,
                block_num=slot.block_num,
                room=slot.room,
                start_min=parse_start_minutes(slot.time),
                end_min=parse_end_minutes(
                    slot.time,
                    default_duration=ACTIVE_CONFERENCE_CONFIG.structure.default_session_duration_min,
                ),
                capacity=4,
                source="template",
                session_title=session_title,
                primary_theme=chosen.dominant_primary,
                subtheme=chosen.dominant_subtheme,
                papers=chosen.papers,
            )
            sessions.append(session)

            for talk_idx, paper in enumerate(chosen.papers, start=1):
                if paper is None:
                    continue
                paper.session_code = session_code
                paper.session_title = session_title
                paper.day_label = slot.day_label
                paper.day_num = slot.day_num
                paper.block_label = slot.block_label
                paper.block_num = slot.block_num
                paper.time = slot.time
                paper.room = slot.room
                paper.talk_index = talk_idx

    return sessions


def _default_session_code(day_num: int, block_num: int, room: str) -> str:
    return f"D{day_num}-B{block_num}-{room}"


def _build_block_signature(block_num: int, block_label: str, time_label: str) -> str:
    return f"{int(block_num)}::{str(block_label).strip()}::{str(time_label).strip()}"


def parse_block_signature(signature: str) -> Tuple[int, str, str]:
    parts = str(signature).split("::", 2)
    if len(parts) != 3:
        raise ValueError(f"Invalid block signature: {signature}")
    block_num = _parse_nonnegative_int(parts[0], default=0)
    block_label = str(parts[1]).strip()
    time_label = str(parts[2]).strip()
    if block_num <= 0 or not time_label:
        raise ValueError(f"Invalid block signature: {signature}")
    return block_num, block_label, time_label


def _session_row_to_session(
    row: Dict[str, str],
    title_overrides: Dict[str, str],
    default_duration_min: int = ACTIVE_CONFERENCE_CONFIG.structure.default_session_duration_min,
) -> Session:
    session_id = str(row.get("SessionId", "")).strip() or str(uuid.uuid4())
    day_label = str(row.get("DayLabel", "")).strip()
    day_num = _parse_positive_int(row.get("DayNum", ""), default=DAY_TO_NUM.get(day_label, 0))
    block_label = str(row.get("BlockLabel", "")).strip()
    block_num = _parse_positive_int(row.get("BlockNum", ""), default=0)
    time_label = str(row.get("TimeLabel", "")).strip()
    start_min = _parse_positive_int(row.get("StartMin", ""), default=parse_start_minutes(time_label))
    end_min = _parse_positive_int(
        row.get("EndMin", ""),
        default=parse_end_minutes(time_label, default_duration=default_duration_min),
    )
    if end_min <= start_min:
        end_min = start_min + default_duration_min
    room = str(row.get("Room", "")).strip()
    session_code = str(row.get("SessionCode", "")).strip() or _default_session_code(day_num, block_num, room)
    status = str(row.get("Status", "active")).strip().lower()
    if status not in {"active", "inactive"}:
        status = "active"
    capacity = _parse_positive_int(row.get("Capacity", ""), default=ACTIVE_CONFERENCE_CONFIG.structure.default_session_capacity)
    source = str(row.get("Source", "")).strip() or "manual"

    default_title = f"{session_code} Session"
    session_title = title_overrides.get(session_code, default_title)

    return Session(
        session_id=session_id,
        session_code=session_code,
        status=status,
        day_label=day_label,
        day_num=day_num,
        time=time_label,
        block_label=block_label,
        block_num=block_num,
        room=room,
        start_min=start_min,
        end_min=end_min,
        capacity=capacity,
        source=source,
        session_title=session_title,
        primary_theme="General",
        subtheme="General",
        papers=[None] * capacity,
    )


def seed_session_structure_from_slots(
    slots: List[Slot],
    path: Path = SESSION_STRUCTURE_FILE,
    default_capacity: int = 4,
    default_duration_min: int = ACTIVE_CONFERENCE_CONFIG.structure.default_session_duration_min,
) -> Dict[str, Dict[str, str]]:
    now = datetime.utcnow().isoformat(timespec="seconds")
    rows: List[Dict[str, str]] = []
    for slot in slots:
        session_code = slot.session_code
        session_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"session:{session_code}"))
        start_min = parse_start_minutes(slot.time)
        end_min = start_min + max(1, int(default_duration_min))
        rows.append(
            {
                "SessionId": session_id,
                "SessionCode": session_code,
                "Status": "active",
                "DayLabel": slot.day_label,
                "DayNum": str(slot.day_num),
                "BlockLabel": slot.block_label,
                "BlockNum": str(slot.block_num),
                "TimeLabel": build_time_label(start_min, end_min),
                "StartMin": str(start_min),
                "EndMin": str(end_min),
                "Room": slot.room,
                "Capacity": str(default_capacity),
                "Source": "template",
                "UpdatedAt": now,
            }
        )
    write_session_structure_rows(rows, path)
    return load_session_structure_rows(path)


def repair_template_session_durations(
    session_structure_path: Path = SESSION_STRUCTURE_FILE,
    config_path: Optional[Path] = None,
) -> Dict[str, object]:
    config = load_conference_config(config_path)
    default_duration = max(1, int(config.structure.default_session_duration_min))
    rows = load_session_structure_rows(session_structure_path)
    changed = 0

    for session_id, row in rows.items():
        source = str(row.get("Source", "")).strip().lower()
        if source != "template":
            continue
        start_min = _parse_positive_int(row.get("StartMin", ""), default=parse_start_minutes(row.get("TimeLabel", "")))
        end_min = _parse_positive_int(
            row.get("EndMin", ""),
            default=parse_end_minutes(row.get("TimeLabel", ""), default_duration=default_duration),
        )
        if end_min - start_min != 30:
            continue
        row["StartMin"] = str(start_min)
        row["EndMin"] = str(start_min + default_duration)
        row["TimeLabel"] = build_time_label(start_min, start_min + default_duration)
        row["UpdatedAt"] = datetime.utcnow().isoformat(timespec="seconds")
        rows[session_id] = row
        changed += 1

    if changed > 0:
        write_session_structure_rows(rows.values(), session_structure_path)
    return {"ok": True, "updated_sessions": changed}


def _backup_legacy_layout_file(path: Path = PROGRAMME_LAYOUT_OVERRIDES_FILE) -> Optional[Path]:
    if not path.exists() or path.stat().st_size == 0:
        return None
    stamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
    backup_path = path.with_suffix(path.suffix + f".bak.{stamp}")
    shutil.copy2(path, backup_path)
    return backup_path


def _derive_initial_paper_placements(
    papers: List[Paper],
    slots: List[Slot],
    session_rows: Dict[str, Dict[str, str]],
    session_name_overrides: Dict[str, str],
    legacy_layout_overrides: Dict[str, Dict[str, str]],
) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    now = datetime.utcnow().isoformat(timespec="seconds")
    for paper in papers:
        out[paper.submission_id] = {
            "SubmissionID": paper.submission_id,
            "PlacementStatus": "unassigned",
            "SessionId": "",
            "TalkIndex": "",
            "OverflowOrder": "",
            "UpdatedAt": now,
        }

    if not papers or not slots:
        return out

    try:
        groups = build_packed_groups(list(papers))
    except Exception:
        return out
    if len(groups) != len(slots):
        return out

    baseline_sessions = assign_groups_to_slots(groups, slots, session_name_overrides)
    apply_programme_layout_overrides_core(papers, baseline_sessions, legacy_layout_overrides)
    code_to_id = {
        str(row.get("SessionCode", "")).strip(): str(row.get("SessionId", "")).strip()
        for row in session_rows.values()
    }

    for paper in papers:
        session_id = code_to_id.get(str(paper.session_code).strip(), "")
        status = str(paper.placement_status or "unassigned").strip().lower()
        if status in {"scheduled", "overflow"} and not session_id:
            status = "unassigned"
        out[paper.submission_id] = {
            "SubmissionID": paper.submission_id,
            "PlacementStatus": status,
            "SessionId": session_id if status in {"scheduled", "overflow"} else "",
            "TalkIndex": str(paper.talk_index) if status == "scheduled" and paper.talk_index else "",
            "OverflowOrder": str(paper.overflow_order) if status == "overflow" and paper.overflow_order else "",
            "UpdatedAt": now,
        }

    return out


def _refresh_session_theme_metadata(sessions: List[Session]) -> None:
    for session in sessions:
        non_null = [paper for paper in session.papers if paper is not None]
        non_null.extend(list(session.overflow_papers))
        if not non_null:
            session.primary_theme = "General"
            session.subtheme = "General"
            if not session.session_title.strip():
                session.session_title = f"{session.session_code} Session"
            continue
        primary_counts = Counter([paper.primary_theme for paper in non_null if paper.primary_theme])
        subtheme_counts = Counter([paper.detailed_subtheme for paper in non_null if paper.detailed_subtheme])
        session.primary_theme = primary_counts.most_common(1)[0][0] if primary_counts else "General"
        session.subtheme = subtheme_counts.most_common(1)[0][0] if subtheme_counts else "General"
        if not session.session_title.strip() or session.session_title == f"{session.session_code} Session":
            session.session_title = f"{THEME_SHORT.get(session.primary_theme, session.primary_theme)}: {session.subtheme}"


def apply_programme_layout_overrides(
    papers: List[Paper],
    sessions: List[Session],
    overrides: Dict[str, Dict[str, str]],
) -> Tuple[List[Paper], List[Dict[str, str]]]:
    return apply_programme_layout_overrides_core(papers, sessions, overrides)


def validate_programme_state(
    state: ProgrammeState,
    config: ConferenceConfig = ACTIVE_CONFERENCE_CONFIG,
) -> Dict[str, object]:
    return validate_programme_state_core(state, config)


def build_programme_state(
    submissions_path: Optional[Path] = None,
    programme_path: Optional[Path] = None,
    classification_overrides_path: Path = CLASSIFICATION_OVERRIDES_FILE,
    session_name_overrides_path: Path = SESSION_NAME_OVERRIDES_FILE,
    programme_layout_overrides_path: Path = PROGRAMME_LAYOUT_OVERRIDES_FILE,
    session_structure_path: Path = SESSION_STRUCTURE_FILE,
    paper_placements_path: Path = PAPER_PLACEMENTS_FILE,
    paper_metadata_overrides_path: Path = PAPER_METADATA_OVERRIDES_FILE,
    paper_archive_overrides_path: Path = PAPER_ARCHIVE_OVERRIDES_FILE,
    manual_talks_path: Path = MANUAL_TALKS_FILE,
    config_path: Optional[Path] = None,
) -> ProgrammeState:
    conference_config = load_conference_config(config_path)
    _hydrate_runtime_constants(conference_config)
    resolved_submissions_path = Path(
        submissions_path or (SOURCE_DIR / conference_config.files.get("submissions", Path(SUBMISSIONS_FILE).name))
    )
    resolved_programme_path = Path(
        programme_path or (SOURCE_DIR / conference_config.files.get("programme", Path(PROGRAMME_FILE).name))
    )

    ensure_state_files(
        STATE_DIR,
        classification_overrides_path,
        session_name_overrides_path,
        programme_layout_overrides_path,
        session_structure_path,
        paper_placements_path,
        paper_metadata_overrides_path,
        paper_archive_overrides_path,
        manual_talks_path,
    )

    cache_key = _base_cache_key(resolved_submissions_path, resolved_programme_path, conference_config)
    cached_base = _BASE_PARSE_CACHE.get(cache_key)
    if cached_base is None:
        parsed_papers = parse_submissions(resolved_submissions_path, conference_config)
        parsed_slots = parse_programme_slots(resolved_programme_path, conference_config)
        _BASE_PARSE_CACHE[cache_key] = (parsed_papers, parsed_slots)
        if len(_BASE_PARSE_CACHE) > 4:
            _BASE_PARSE_CACHE.pop(next(iter(_BASE_PARSE_CACHE)))
        cached_base = _BASE_PARSE_CACHE[cache_key]

    papers = copy.deepcopy(cached_base[0])
    slots = copy.deepcopy(cached_base[1])
    manual_papers = load_manual_talks(manual_talks_path)
    known_ids = {paper.submission_id for paper in papers}
    for paper in manual_papers:
        sid = paper.submission_id
        if sid in known_ids or not sid:
            sid = f"MANUAL-{uuid.uuid4().hex[:8].upper()}"
            paper.submission_id = sid
        known_ids.add(sid)
        papers.append(paper)

    class_overrides = load_classification_overrides(classification_overrides_path)
    classify_papers(papers, class_overrides)
    metadata_overrides = load_paper_metadata_overrides(paper_metadata_overrides_path)
    _apply_paper_metadata_overrides(papers, metadata_overrides)
    archive_overrides = load_paper_archive_overrides(paper_archive_overrides_path)
    session_name_overrides = load_session_name_overrides(session_name_overrides_path)

    session_rows = load_session_structure_rows(session_structure_path)
    if not session_rows and slots:
        session_rows = seed_session_structure_from_slots(
            slots,
            session_structure_path,
            default_capacity=conference_config.structure.default_session_capacity,
            default_duration_min=conference_config.structure.default_session_duration_min,
        )
    if session_rows:
        repair_result = repair_template_session_durations(
            session_structure_path=session_structure_path,
            config_path=config_path,
        )
        if int(repair_result.get("updated_sessions", 0) or 0) > 0:
            session_rows = load_session_structure_rows(session_structure_path)

    placements = load_paper_placements(paper_placements_path)
    legacy_rows = _load_csv_rows(programme_layout_overrides_path, PROGRAMME_LAYOUT_HEADERS)
    if not placements:
        initial_placements = _derive_initial_paper_placements(
            copy.deepcopy(papers),
            slots,
            session_rows,
            session_name_overrides,
            {row.get("SubmissionID", ""): row for row in legacy_rows if row.get("SubmissionID", "")},
        )
        write_paper_placements(initial_placements.values(), paper_placements_path)
        placements = load_paper_placements(paper_placements_path)
        if legacy_rows:
            _backup_legacy_layout_file(programme_layout_overrides_path)

    all_sessions = sorted(
        [
            _session_row_to_session(
                row,
                session_name_overrides,
                default_duration_min=conference_config.structure.default_session_duration_min,
            )
            for row in session_rows.values()
        ],
        key=lambda s: (s.day_num, s.start_min, room_sort_key(s.room), s.session_code),
    )
    active_sessions = [session for session in all_sessions if session.status == "active"]
    inactive_sessions = [session for session in all_sessions if session.status != "active"]

    archived_submission_ids = {
        paper.submission_id
        for paper in papers
        if paper.submission_id in archive_overrides
    }
    archived_papers: List[Paper] = []
    active_papers: List[Paper] = []
    for paper in papers:
        if paper.submission_id in archived_submission_ids:
            paper.placement_status = "unassigned"
            paper.session_id = ""
            paper.session_code = ""
            paper.session_title = ""
            paper.day_label = ""
            paper.day_num = 0
            paper.block_label = ""
            paper.block_num = 0
            paper.time = ""
            paper.room = ""
            paper.talk_index = 0
            paper.overflow_order = 0
            paper.talk_start_min = 0
            paper.talk_end_min = 0
            archived_papers.append(paper)
        else:
            active_papers.append(paper)

    unassigned_papers, slot_conflicts = apply_paper_placements_core(active_papers, all_sessions, placements)
    _refresh_session_theme_metadata(all_sessions)
    for session in all_sessions:
        if session.session_code in session_name_overrides:
            session.session_title = session_name_overrides[session.session_code]

    layout_overrides = load_programme_layout_overrides(
        programme_layout_overrides_path,
        paper_placements_path=paper_placements_path,
        session_structure_path=session_structure_path,
    )
    edited_submission_ids = _compute_edited_submission_ids(
        class_overrides,
        layout_overrides,
        metadata_overrides,
        archive_overrides,
    )

    archived_reason_counts: Dict[str, int] = {}
    archived_by_previous_status: Dict[str, int] = {
        "scheduled": 0,
        "overflow": 0,
        "unassigned": 0,
    }
    for paper in archived_papers:
        archive_row = archive_overrides.get(paper.submission_id, {})
        reason = str(archive_row.get("ArchiveReason", "")).strip() or "Other"
        archived_reason_counts[reason] = archived_reason_counts.get(reason, 0) + 1
        previous_status = str(archive_row.get("PreviousPlacementStatus", "")).strip().lower()
        if previous_status not in archived_by_previous_status:
            previous_status = "unassigned"
        archived_by_previous_status[previous_status] = archived_by_previous_status.get(previous_status, 0) + 1

    state = ProgrammeState(
        papers=active_papers,
        sessions=active_sessions,
        inactive_sessions=inactive_sessions,
        all_sessions=all_sessions,
        archived_papers=archived_papers,
        validations={},
        unassigned_papers=unassigned_papers,
        slot_conflicts=slot_conflicts,
        edited_submission_ids=edited_submission_ids,
    )
    state.validations = validate_programme_state(state, conference_config)
    state.validations["total_papers"] = len(active_papers) + len(archived_papers)
    state.validations["archived_papers"] = len(archived_papers)
    state.validations["archived_submission_ids"] = sorted([paper.submission_id for paper in archived_papers])
    state.validations["archived_by_previous_status"] = archived_by_previous_status
    state.validations["archived_by_reason"] = dict(sorted(archived_reason_counts.items(), key=lambda item: item[0]))
    state.validations["edited_submission_ids"] = sorted(edited_submission_ids)
    state.validations["conference_config"] = resolve_config_path(config_path).as_posix()
    state.validations["conference_signature"] = conference_config.signature()
    return state


def papers_to_rows(state: ProgrammeState) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for paper in sorted(state.papers, key=lambda p: p.submission_id):
        rows.append(
            {
                "SubmissionID": paper.submission_id,
                "FullName": paper.full_name,
                "EmailAddress": paper.email,
                "ReviewerScore": paper.reviewer_score,
                "SourceThemes": paper.source_themes,
                "PrimaryTheme": paper.primary_theme,
                "Subtheme": paper.detailed_subtheme,
                "SecondaryThemeTags": ", ".join(paper.secondary_tags),
                "Reviewed": paper.reviewed,
                "OverrideNotes": paper.override_notes,
                "SessionCode": paper.session_code,
                "SessionTitle": paper.session_title,
                "Day": paper.day_label,
                "Block": paper.block_label,
                "Time": paper.time,
                "Room": paper.room,
                "TalkIndex": paper.talk_index,
                "PlacementStatus": paper.placement_status,
                "OverflowOrder": paper.overflow_order,
                "Title": paper.title,
                "Abstract": paper.abstract,
                "LinkToPDF": paper.link_to_pdf,
                "AssignmentRationale": paper.rationale,
            }
        )
    return rows


def programme_talk_rows(state: ProgrammeState) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for session in state.sessions:
        for idx, paper in enumerate(session.papers, start=1):
            rows.append(
                {
                    "SessionCode": session.session_code,
                    "Day": session.day_label,
                    "DayNum": session.day_num,
                    "Block": session.block_label,
                    "BlockNum": session.block_num,
                    "Time": session.time,
                    "Room": session.room,
                    "SessionTitle": session.session_title,
                    "PrimaryTheme": session.primary_theme,
                    "Subtheme": session.subtheme,
                    "TalkIndex": idx,
                    "OverflowOrder": 0,
                    "PlacementStatus": "scheduled" if paper is not None else "reserve",
                    "RowType": "scheduled_slot",
                    "SubmissionID": "" if paper is None else paper.submission_id,
                    "Presenter": "[Reserve slot]" if paper is None else paper.full_name,
                    "Title": "[Reserve slot]" if paper is None else paper.title,
                    "Abstract": "" if paper is None else paper.abstract,
                    "LinkToPDF": "" if paper is None else paper.link_to_pdf,
                    "Reviewed": False if paper is None else paper.reviewed,
                }
            )
        for overflow_rank, paper in enumerate(session.overflow_papers, start=1):
            rows.append(
                {
                    "SessionCode": session.session_code,
                    "Day": session.day_label,
                    "DayNum": session.day_num,
                    "Block": session.block_label,
                    "BlockNum": session.block_num,
                    "Time": session.time,
                    "Room": session.room,
                    "SessionTitle": session.session_title,
                    "PrimaryTheme": session.primary_theme,
                    "Subtheme": session.subtheme,
                    "TalkIndex": 0,
                    "OverflowOrder": overflow_rank,
                    "PlacementStatus": "overflow",
                    "RowType": "overflow",
                    "SubmissionID": paper.submission_id,
                    "Presenter": paper.full_name,
                    "Title": paper.title,
                    "Abstract": paper.abstract,
                    "LinkToPDF": paper.link_to_pdf,
                    "Reviewed": paper.reviewed,
                }
            )
    return rows


def build_override_rows_from_papers(papers: Iterable[Paper]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    now = datetime.utcnow().isoformat(timespec="seconds")
    for paper in papers:
        out.append(
            {
                "SubmissionID": paper.submission_id,
                "OverridePrimaryTheme": paper.primary_theme,
                "OverrideSubtheme": paper.detailed_subtheme,
                "Reviewed": "True" if paper.reviewed else "False",
                "OverrideNotes": paper.override_notes,
                "UpdatedAt": now,
            }
        )
    return out


def build_layout_override_rows_from_papers(papers: Iterable[Paper]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    now = datetime.utcnow().isoformat(timespec="seconds")
    for paper in papers:
        session_code = paper.session_code if paper.placement_status in {"scheduled", "overflow"} else ""
        talk_index = str(paper.talk_index) if paper.placement_status == "scheduled" and paper.talk_index else ""
        overflow_order = str(paper.overflow_order) if paper.placement_status == "overflow" and paper.overflow_order else ""
        out.append(
            {
                "SubmissionID": paper.submission_id,
                "PlacementStatus": paper.placement_status or "scheduled",
                "SessionCode": session_code,
                "TalkIndex": talk_index,
                "OverflowOrder": overflow_order,
                "UpdatedAt": now,
            }
        )
    return out
