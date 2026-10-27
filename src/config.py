"""Paths and constants shared by the Phase 1 ingestion pipeline."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Inputs
RAW_NOTEBOOKS_DIR = ROOT / "data" / "raw" / "notebooks"   # originals, never modified
TOPIC_CATALOG = ROOT / "data" / "topic_catalog.json"       # finalized 40-topic catalog

# Outputs (local only; data/ is gitignored except the topic catalog)
PROCESSED_DIR = ROOT / "data" / "processed"
CELLS_JSONL = "cells.jsonl"
NOTEBOOKS_JSONL = "notebooks.jsonl"
INVENTORY_CSV = "corpus_inventory.csv"
TOPIC_CANDIDATES_CSV = "topic_candidates.csv"
REPORT_MD = "ingestion_report.md"

PIPELINE_VERSION = "phase1-v2"            # v2: heading-span sections, output roles (PH1-FIX-001)
EXPECTED_NOTEBOOKS = 53

# Section title for text that comes before the notebook's first heading (section_path is [])
DEFAULT_SECTION = "Preamble"

# Headings that label a block rather than start a section (MCQ blocks, "Code:" labels).
# They stay in the cell content but do not change the section of later cells.
NON_STRUCTURAL_HEADINGS = {"question", "questions", "choices", "choice", "code", "answer", "options"}

# Output handling (see notebook_parser.classify_output for the roles)
MAX_OUTPUT_CHARS = 4000          # logs, dataframe dumps and errors longer than this are truncated
MAX_TEACHING_OUTPUT_CHARS = 20000  # printed teaching text and results keep up to this much
LARGE_TABLE_LINES = 15           # table outputs longer than this are dataframe dumps, not results
SHORT_CELL_CHARS = 20            # non-empty cells shorter than this are flagged as short

# Quality thresholds used by the report and the tests
MAX_SECTION_MISLABEL_RATE = 0.02  # share of markdown text under the wrong section (PH1-FIX-001)
SMALL_NOTEBOOK_CELLS = 15        # notebooks with fewer cells are flagged for review
