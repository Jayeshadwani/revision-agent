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

PIPELINE_VERSION = "phase1-v1"
EXPECTED_NOTEBOOKS = 53

# Section assigned to cells that come before the first heading
DEFAULT_SECTION = "Untitled / beginning of notebook"

# Headings that label a block rather than start a section (MCQ blocks, "Code:" labels).
# They stay in the cell content but do not change the section of later cells.
NON_STRUCTURAL_HEADINGS = {"question", "questions", "choices", "choice", "code", "answer", "options"}

# Output handling
MAX_OUTPUT_CHARS = 4000          # longer text outputs are truncated and flagged
SHORT_CELL_CHARS = 20            # non-empty cells shorter than this are flagged as short

# Quality thresholds used by the report and the tests
MIN_SECTION_COVERAGE = 0.90      # share of non-empty cells with a real section
SMALL_NOTEBOOK_CELLS = 15        # notebooks with fewer cells are flagged for review
