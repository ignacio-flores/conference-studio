from __future__ import annotations

import csv
import re
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

APP_DIR = Path(__file__).resolve().parent
BASE_DIR = APP_DIR.parent
SOURCE_DIR = BASE_DIR / "source_data"

SUBMISSIONS_FILE = SOURCE_DIR / "WIC 2026 - Submissions (Reviewed).xlsx"
PROGRAMME_FILE = SOURCE_DIR / "WIC2026_Programme.xlsx"

STATE_DIR = APP_DIR / "state"
CLASSIFICATION_OVERRIDES_FILE = STATE_DIR / "classification_overrides.csv"
SESSION_NAME_OVERRIDES_FILE = STATE_DIR / "session_name_overrides.csv"
PROGRAMME_LAYOUT_OVERRIDES_FILE = STATE_DIR / "programme_layout_overrides.csv"

EXPORT_DIR = BASE_DIR / "exports"
DRAFT_OUTPUT_FILE = EXPORT_DIR / "WIC2026_Programme_Draft.xlsx"
PUBLISH_XLSX_FILE = EXPORT_DIR / "WIC2026_Programme_Publish.xlsx"
PUBLISH_PDF_FILE = EXPORT_DIR / "WIC2026_Programme_Publish.pdf"

DAY_ORDER = ["Day 1 (4th June)", "Day 2 (5th June)", "Day 3 (6th June)"]
DAY_TO_NUM = {day: idx for idx, day in enumerate(DAY_ORDER, start=1)}

ROOM_PRIORITY = {
    "R2-01": 10,
    "R2-21": 20,
    "R1-09": 30,
    "R2-20": 40,
    "R1-10": 50,
    "R3-71": 60,
    "TBD-A": 70,
    "TBD-B": 80,
    "TBD-C": 90,
}

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
    primary_theme: str = ""
    detailed_subtheme: str = ""
    secondary_tags: List[str] = field(default_factory=list)
    matched_keywords: List[str] = field(default_factory=list)
    rationale: str = ""
    reviewed: bool = False
    override_notes: str = ""
    session_code: str = ""
    session_title: str = ""
    day_label: str = ""
    day_num: int = 0
    block_label: str = ""
    block_num: int = 0
    time: str = ""
    room: str = ""
    talk_index: int = 0
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
    session_code: str
    day_label: str
    day_num: int
    time: str
    block_label: str
    block_num: int
    room: str
    session_title: str
    primary_theme: str
    subtheme: str
    papers: List[Optional[Paper]]
    overflow_papers: List[Paper] = field(default_factory=list)


@dataclass
class ProgrammeState:
    papers: List[Paper]
    sessions: List[Session]
    validations: Dict[str, object]
    unassigned_papers: List[Paper] = field(default_factory=list)
    slot_conflicts: List[Dict[str, str]] = field(default_factory=list)


@dataclass
class PackedGroup:
    index: int
    papers: List[Optional[Paper]]
    dominant_primary: str
    dominant_subtheme: str
    auto_title: str


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


def format_minutes(total_minutes: int) -> str:
    return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"


def room_sort_key(room: str) -> Tuple[int, str]:
    return (ROOM_PRIORITY.get(room, 999), room)


def parse_bool(value: str) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


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


def parse_submissions(path: Path) -> List[Paper]:
    reader = XlsxXmlReader(path)
    rows = reader.read_sheet_rows("Sheet1")
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

    accepted: List[Paper] = []
    for _, cells in rows[1:]:
        score = str(cells.get(col_idx["ReviewerScore"], "")).strip()
        if score != "1":
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


def parse_programme_slots(path: Path) -> List[Slot]:
    reader = XlsxXmlReader(path)
    slots: List[Slot] = []

    for day_name in DAY_ORDER:
        rows = reader.read_sheet_rows(day_name)
        matrix: Dict[Tuple[int, int], str] = {}
        for row_num, cells in rows:
            for col_num, value in cells.items():
                matrix[(row_num, col_num)] = value

        room_cols = []
        for col_num in range(4, 40):
            name = matrix.get((3, col_num), "")
            if re.match(r"^(Amphi|R\d+-\d+)$", name):
                room_cols.append(col_num)

        for row_num in range(1, 90):
            block_label = matrix.get((row_num, 3), "")
            block_upper = block_label.upper()
            if "SESSION" not in block_upper:
                continue
            if "OPTIONAL" in block_upper:
                continue

            time_label = matrix.get((row_num, 2), "")
            if day_name == "Day 1 (4th June)" and time_label.strip() == "9h30-10h":
                # Opening plenary period has no paper presentations.
                continue

            session_match = re.search(r"SESSION\s*(\d+)", block_upper)
            block_num = int(session_match.group(1)) if session_match else 0

            open_rooms: List[str] = []
            for col_num in room_cols:
                if matrix.get((row_num, col_num), "") == "":
                    open_rooms.append(matrix.get((3, col_num), f"Room-{col_num}"))

            extra_rooms = ["TBD-A", "TBD-B"]
            if day_name == "Day 2 (5th June)" and block_num in {2, 3, 4}:
                extra_rooms.append("TBD-C")

            all_rooms = open_rooms + extra_rooms
            for room in all_rooms:
                slots.append(
                    Slot(
                        day_label=day_name,
                        day_num=DAY_TO_NUM[day_name],
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
) -> Dict[str, Dict[str, str]]:
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
) -> None:
    normalized: Dict[str, Dict[str, str]] = {}
    now = datetime.utcnow().isoformat(timespec="seconds")
    for row in rows:
        sid = str(row.get("SubmissionID", "")).strip()
        if not sid:
            continue
        status = str(row.get("PlacementStatus", "")).strip().lower()
        if status not in {"scheduled", "unassigned", "overflow"}:
            status = "scheduled"
        normalized[sid] = {
            "SubmissionID": sid,
            "PlacementStatus": status,
            "SessionCode": str(row.get("SessionCode", "")).strip(),
            "TalkIndex": str(row.get("TalkIndex", "")).strip(),
            "OverflowOrder": str(row.get("OverflowOrder", "")).strip(),
            "UpdatedAt": str(row.get("UpdatedAt", "")).strip() or now,
        }

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=PROGRAMME_LAYOUT_HEADERS)
        writer.writeheader()
        for sid in sorted(normalized.keys(), key=lambda x: (len(x), x)):
            writer.writerow(normalized[sid])


def classify_papers(
    papers: List[Paper],
    classification_overrides: Optional[Dict[str, Dict[str, str]]] = None,
) -> None:
    overrides = classification_overrides or {}

    for paper in papers:
        text = normalize_key(f"{paper.title} {paper.abstract}")
        tags = map_source_themes(paper.source_themes)
        inferred_primary = infer_theme_from_text(text)

        if tags:
            primary = tags[0]
            secondary = list(dict.fromkeys(tags[1:]))[:2]
            source_hint = "source theme"

            # Let abstract/title evidence surface mobility and land themes
            # even when source tags are broad.
            override_candidates = {"Income and wealth mobility", "Land inequality"}
            if inferred_primary in override_candidates and inferred_primary != primary:
                inferred_hits = keyword_matches(text, THEME_KEYWORDS.get(inferred_primary, []))
                if len(inferred_hits) >= 2:
                    secondary = list(dict.fromkeys([primary] + secondary))[:2]
                    primary = inferred_primary
                    source_hint = "title/abstract override"
        else:
            primary = inferred_primary
            secondary = []
            source_hint = "title/abstract inference"

        subtheme, matched_keywords = classify_subtheme(primary, text)

        paper.primary_theme = primary
        paper.detailed_subtheme = subtheme
        paper.secondary_tags = secondary
        paper.matched_keywords = matched_keywords
        paper.rationale = (
            f"Mapped via {source_hint} to '{primary}' and grouped under '{subtheme}'."
        )
        paper.reviewed = False
        paper.override_notes = ""

        override = overrides.get(paper.submission_id)
        if not override:
            continue

        override_theme = override.get("OverridePrimaryTheme", "")
        override_subtheme = override.get("OverrideSubtheme", "")
        reviewed = parse_bool(override.get("Reviewed", ""))
        notes = override.get("OverrideNotes", "")

        if override_theme:
            paper.primary_theme = override_theme
            if paper.primary_theme not in paper.secondary_tags and paper.primary_theme != primary:
                paper.secondary_tags = list(dict.fromkeys([primary] + paper.secondary_tags))[:2]

        if override_subtheme:
            paper.detailed_subtheme = override_subtheme
        elif override_theme and override_theme != primary:
            paper.detailed_subtheme = classify_subtheme(paper.primary_theme, text)[0]

        if override_theme or override_subtheme:
            paper.rationale = "Mapped by manual override in curation UI."

        paper.reviewed = reviewed
        paper.override_notes = notes


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
                session_code=session_code,
                day_label=slot.day_label,
                day_num=slot.day_num,
                time=slot.time,
                block_label=slot.block_label,
                block_num=slot.block_num,
                room=slot.room,
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


def _parse_positive_int(raw: str, default: int = 0) -> int:
    try:
        value = int(str(raw).strip())
        return value if value > 0 else default
    except Exception:
        return default


def apply_programme_layout_overrides(
    papers: List[Paper],
    sessions: List[Session],
    overrides: Dict[str, Dict[str, str]],
) -> Tuple[List[Paper], List[Dict[str, str]]]:
    paper_map = {p.submission_id: p for p in papers}
    session_map = {s.session_code: s for s in sessions}

    slot_map: Dict[Tuple[str, int], Optional[str]] = {}
    paper_place: Dict[str, Tuple[str, str, int]] = {}
    overflow_map: Dict[str, List[Tuple[int, str]]] = defaultdict(list)
    unassigned_ids: set[str] = set()
    slot_conflicts: List[Dict[str, str]] = []

    for session in sessions:
        session.overflow_papers = []
        for idx in range(1, 5):
            paper = session.papers[idx - 1]
            sid = None if paper is None else paper.submission_id
            slot_map[(session.session_code, idx)] = sid
            if sid:
                paper_place[sid] = ("scheduled", session.session_code, idx)

    def detach(sid: str) -> None:
        current = paper_place.get(sid)
        if not current:
            return
        status, session_code, position = current
        if status == "scheduled":
            slot_map[(session_code, position)] = None
        elif status == "overflow":
            overflow_map[session_code] = [
                (o, existing_sid)
                for o, existing_sid in overflow_map.get(session_code, [])
                if existing_sid != sid
            ]
        elif status == "unassigned":
            unassigned_ids.discard(sid)
        paper_place.pop(sid, None)

    for sid, row in overrides.items():
        if sid not in paper_map:
            continue

        status = str(row.get("PlacementStatus", "")).strip().lower()
        target_session = str(row.get("SessionCode", "")).strip()
        talk_index = _parse_positive_int(row.get("TalkIndex", ""), default=0)
        overflow_order = _parse_positive_int(row.get("OverflowOrder", ""), default=9999)

        detach(sid)

        if status == "unassigned":
            unassigned_ids.add(sid)
            paper_place[sid] = ("unassigned", "", 0)
            continue

        if status == "scheduled":
            if target_session not in session_map or talk_index not in {1, 2, 3, 4}:
                unassigned_ids.add(sid)
                paper_place[sid] = ("unassigned", "", 0)
                continue
            key = (target_session, talk_index)
            occupant_sid = slot_map.get(key)
            if occupant_sid is None:
                slot_map[key] = sid
                paper_place[sid] = ("scheduled", target_session, talk_index)
            else:
                # Session slot already occupied: keep existing scheduled paper and
                # send moved paper to overflow for organizer resolution.
                overflow_map[target_session].append((overflow_order, sid))
                paper_place[sid] = ("overflow", target_session, overflow_order)
                slot_conflicts.append(
                    {
                        "SubmissionID": sid,
                        "SessionCode": target_session,
                        "TalkIndex": str(talk_index),
                        "Reason": f"Target slot occupied by {occupant_sid}; moved to overflow.",
                    }
                )
            continue

        if status == "overflow":
            if target_session not in session_map:
                unassigned_ids.add(sid)
                paper_place[sid] = ("unassigned", "", 0)
                continue
            overflow_map[target_session].append((overflow_order, sid))
            paper_place[sid] = ("overflow", target_session, overflow_order)
            continue

        # Unknown status fallback.
        unassigned_ids.add(sid)
        paper_place[sid] = ("unassigned", "", 0)

    # Rebuild sessions and paper placement fields.
    for session in sessions:
        rebuilt_slots: List[Optional[Paper]] = []
        for idx in range(1, 5):
            sid = slot_map.get((session.session_code, idx))
            paper = paper_map.get(sid) if sid else None
            rebuilt_slots.append(paper)
            if paper is not None:
                paper.placement_status = "scheduled"
                paper.session_code = session.session_code
                paper.session_title = session.session_title
                paper.day_label = session.day_label
                paper.day_num = session.day_num
                paper.block_label = session.block_label
                paper.block_num = session.block_num
                paper.time = session.time
                paper.room = session.room
                paper.talk_index = idx
                paper.overflow_order = 0
        session.papers = rebuilt_slots

        ordered_overflow = sorted(
            overflow_map.get(session.session_code, []),
            key=lambda x: (x[0], paper_map[x[1]].title.lower()),
        )
        session.overflow_papers = []
        for rank, (_, sid) in enumerate(ordered_overflow, start=1):
            paper = paper_map[sid]
            paper.placement_status = "overflow"
            paper.session_code = session.session_code
            paper.session_title = session.session_title
            paper.day_label = session.day_label
            paper.day_num = session.day_num
            paper.block_label = session.block_label
            paper.block_num = session.block_num
            paper.time = session.time
            paper.room = session.room
            paper.talk_index = 0
            paper.overflow_order = rank
            session.overflow_papers.append(paper)

    for sid in unassigned_ids:
        paper = paper_map[sid]
        paper.placement_status = "unassigned"
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

    # Any paper not explicitly set remains in scheduled default state.
    for paper in papers:
        if paper.submission_id in unassigned_ids:
            continue
        if paper.placement_status == "overflow":
            continue
        if paper.session_code:
            paper.placement_status = "scheduled"

    unassigned_papers = sorted(
        [paper_map[sid] for sid in unassigned_ids if sid in paper_map],
        key=lambda p: p.title.lower(),
    )
    return unassigned_papers, slot_conflicts


def validate_programme_state(state: ProgrammeState) -> Dict[str, object]:
    papers = state.papers
    sessions = state.sessions

    scheduled_ids: List[str] = []
    overflow_ids: List[str] = []
    overflow_by_session: Dict[str, List[str]] = {}
    for session in sessions:
        if len(session.papers) != 4:
            raise RuntimeError(f"Session {session.session_code} does not have 4 slots")
        for paper in session.papers:
            if paper is not None:
                scheduled_ids.append(paper.submission_id)
        if session.overflow_papers:
            overflow_by_session[session.session_code] = [p.submission_id for p in session.overflow_papers]
            overflow_ids.extend(overflow_by_session[session.session_code])

    unassigned_ids = [paper.submission_id for paper in state.unassigned_papers]
    accounted_ids = scheduled_ids + overflow_ids + unassigned_ids
    id_counts = Counter(accounted_ids)
    duplicates = sorted([sid for sid, count in id_counts.items() if count > 1])

    all_ids = sorted([p.submission_id for p in papers])
    assigned_set = set(accounted_ids)
    missing = sorted([sid for sid in all_ids if sid not in assigned_set])

    reserve_slots = sum(1 for session in sessions for paper in session.papers if paper is None)
    day1_opening_assigned = [
        session.session_code
        for session in sessions
        if session.day_num == 1 and session.time.strip() == "9h30-10h"
    ]
    optional_block_sessions = [
        session.session_code for session in sessions if "OPTIONAL" in session.block_label.upper()
    ]

    reviewed_count = sum(1 for p in papers if p.reviewed)
    over_capacity_sessions = sorted([code for code, values in overflow_by_session.items() if values])

    validations = {
        "accepted_papers": len(papers),
        "sessions": len(sessions),
        "assigned_papers": len(scheduled_ids),
        "scheduled_papers": len(scheduled_ids),
        "overflow_papers": len(overflow_ids),
        "unassigned_papers": len(unassigned_ids),
        "accounted_papers": len(accounted_ids),
        "duplicate_submission_ids": duplicates,
        "missing_submission_ids": missing,
        "unassigned_submission_ids": sorted(unassigned_ids),
        "overflow_submission_ids": sorted(overflow_ids),
        "overflow_by_session": overflow_by_session,
        "over_capacity_sessions": over_capacity_sessions,
        "slot_conflicts": list(state.slot_conflicts),
        "reserve_slots": reserve_slots,
        "day1_opening_assigned_sessions": day1_opening_assigned,
        "optional_block_assigned_sessions": optional_block_sessions,
        "reviewed_papers": reviewed_count,
        "unreviewed_papers": len(papers) - reviewed_count,
    }

    hard_constraints_ok = (
        len(sessions) == 75
        and len(day1_opening_assigned) == 0
        and len(optional_block_sessions) == 0
    )
    planning_issues_present = (
        len(duplicates) == 0
        and len(missing) == 0
        and reserve_slots == 3
        and len(unassigned_ids) == 0
        and len(overflow_ids) == 0
        and len(state.slot_conflicts) == 0
    )
    validations["hard_constraints_ok"] = hard_constraints_ok
    validations["is_valid"] = hard_constraints_ok and planning_issues_present
    validations["has_planning_issues"] = not planning_issues_present

    return validations


def build_programme_state(
    submissions_path: Path = Path(SUBMISSIONS_FILE),
    programme_path: Path = Path(PROGRAMME_FILE),
    classification_overrides_path: Path = CLASSIFICATION_OVERRIDES_FILE,
    session_name_overrides_path: Path = SESSION_NAME_OVERRIDES_FILE,
    programme_layout_overrides_path: Path = PROGRAMME_LAYOUT_OVERRIDES_FILE,
) -> ProgrammeState:
    ensure_state_files(
        STATE_DIR,
        classification_overrides_path,
        session_name_overrides_path,
        programme_layout_overrides_path,
    )

    papers = parse_submissions(submissions_path)
    class_overrides = load_classification_overrides(classification_overrides_path)
    classify_papers(papers, class_overrides)

    slots = parse_programme_slots(programme_path)
    if len(slots) != 75:
        raise RuntimeError(f"Expected 75 slots from programme template, found {len(slots)}")

    groups = build_packed_groups(papers)
    session_name_overrides = load_session_name_overrides(session_name_overrides_path)
    sessions = assign_groups_to_slots(groups, slots, session_name_overrides)
    layout_overrides = load_programme_layout_overrides(programme_layout_overrides_path)
    unassigned_papers, slot_conflicts = apply_programme_layout_overrides(papers, sessions, layout_overrides)

    state = ProgrammeState(
        papers=papers,
        sessions=sessions,
        validations={},
        unassigned_papers=unassigned_papers,
        slot_conflicts=slot_conflicts,
    )
    state.validations = validate_programme_state(state)
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


def sessions_to_rows(state: ProgrammeState) -> List[Dict[str, object]]:
    rows: List[Dict[str, object]] = []
    for session in sorted(
        state.sessions,
        key=lambda s: (s.day_num, parse_start_minutes(s.time), room_sort_key(s.room)),
    ):
        row: Dict[str, object] = {
            "SessionCode": session.session_code,
            "Day": session.day_label,
            "Block": session.block_label,
            "Time": session.time,
            "Room": session.room,
            "SessionTitle": session.session_title,
            "PrimaryTheme": session.primary_theme,
            "Subtheme": session.subtheme,
            "OverflowCount": len(session.overflow_papers),
            "OverflowSubmissionIDs": ", ".join([p.submission_id for p in session.overflow_papers]),
            "OverflowTitles": " | ".join([p.title for p in session.overflow_papers]),
        }
        for idx, paper in enumerate(session.papers, start=1):
            row[f"Slot{idx}_SubmissionID"] = paper.submission_id if paper else ""
            row[f"Slot{idx}_Presenter"] = paper.full_name if paper else "[Reserve slot]"
            row[f"Slot{idx}_Title"] = paper.title if paper else "[Reserve slot]"
        rows.append(row)
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
