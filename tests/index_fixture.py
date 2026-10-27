"""Synthetic chunks and a stand-in tokenizer for the embedding / index tests (issue #5)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import embeddings as em  # noqa: E402

CFG = em.EmbeddingConfig(dimensions=16, batch_size=2)   # small vectors keep the tests fast


class WordTokenizer:
    """Test stand-in only. Real runs use the model tokenizer (embeddings.get_tokenizer)."""
    name = "test-words"

    def count(self, text: str) -> int:
        return len(text.split())


def concept(n: int, text: str = "Precision is TP / (TP + FP).", math: bool = True, notebook: str = "nb_12") -> dict:
    return {
        "chunk_id": f"CON_{n:06d}", "chunk_type": "concept", "notebook_id": notebook,
        "notebook_title": "Model Evaluation", "section_path": ["Model Evaluation", "Precision"],
        "source_cell_ids": [n], "source_span_ids": [f"{notebook}_cell_{n:03d}_span_000"],
        "content": f"Notebook: Model Evaluation\nSection path: Model Evaluation > Precision\n\n{text}",
        "contains_math": math, "contains_latex": math, "contains_table": False, "contains_code": False,
        "linked_tool_ids": ["TOOL_0001"], "linked_tool_chunk_ids": ["TOOLCHUNK_000001"], "linked_resource_ids": [],
        "quality_flags": {"is_tiny": False, "is_oversized": False}, "retrieval_eligible": True,
    }


def tool(n: int, code: str = "def precision(tp, fp):\n    return tp / (tp + fp)") -> dict:
    return {
        "chunk_id": f"TOOLCHUNK_{n:06d}", "chunk_type": "tool", "tool_id": f"TOOL_{n:04d}", "notebook_id": "nb_12",
        "notebook_title": "Model Evaluation", "section_path": ["Model Evaluation", "Precision"],
        "breadcrumb": "Notebook: Model Evaluation\nSection path: Model Evaluation > Precision",
        "source_cell_id": f"nb_12_cell_{n:03d}", "source_cell_ids": [n], "tool_type": "tool_function",
        "title": "Precision", "purpose": "Defines a function for Precision",
        "description": "Precision is the share of predicted positives that are right.", "language": "python",
        "libraries": ["numpy"], "code": code, "linked_concept_chunk_ids": ["CON_000001"], "linked_resource_ids": [],
        "repeats_code_of": None, "retrieval_eligible": True,
    }


def corpus() -> list[dict]:
    return [concept(1), concept(2, "Recall is TP / (TP + FN).", notebook="nb_13"), concept(3, "No math here.", False),
            tool(1), tool(2, "import numpy as np\nnp.mean([1, 2, 3])")]
