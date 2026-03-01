"""
Document content extractor — Strategy pattern.

Each file type has its own concrete strategy implementing ``BaseExtractor``.
``ExtractorFactory`` picks the right one based on file extension.
"""

from __future__ import annotations

import csv
import io
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Tuple, Type

import pandas as pd
from pypdf import PdfReader
from docx import Document as DocxDocument


# ═══════════════════════════════════════════════════════
#  Abstract base
# ═══════════════════════════════════════════════════════

class BaseExtractor(ABC):
    """Interface every file-type extractor must implement."""

    @abstractmethod
    def extract(self, data: bytes) -> Tuple[str, int]:
        """Return (extracted_text, page_count)."""
        ...


# ═══════════════════════════════════════════════════════
#  Concrete strategies
# ═══════════════════════════════════════════════════════

class PdfExtractor(BaseExtractor):
    """Extracts text from PDF using pypdf."""

    def extract(self, data: bytes) -> Tuple[str, int]:
        reader = PdfReader(io.BytesIO(data))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages), len(reader.pages)


class DocxExtractor(BaseExtractor):
    """Extracts text from DOCX using python-docx."""

    _CHARS_PER_PAGE = 3_000

    def extract(self, data: bytes) -> Tuple[str, int]:
        doc = DocxDocument(io.BytesIO(data))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        full_text = "\n\n".join(paragraphs)
        page_estimate = max(1, len(full_text) // self._CHARS_PER_PAGE)
        return full_text, page_estimate


class CsvExtractor(BaseExtractor):
    """Renders a CSV as a pipe-delimited readable table."""

    def extract(self, data: bytes) -> Tuple[str, int]:
        text = data.decode("utf-8", errors="replace")
        reader = csv.reader(io.StringIO(text))
        lines = [" | ".join(row) for row in reader]
        return "\n".join(lines), 1


class ExcelExtractor(BaseExtractor):
    """Renders all sheets of an Excel workbook as text tables."""

    def extract(self, data: bytes) -> Tuple[str, int]:
        sheets: Dict[str, pd.DataFrame] = pd.read_excel(
            io.BytesIO(data), sheet_name=None,
        )
        parts: list[str] = []
        for name, df in sheets.items():
            parts.append(f"--- Sheet: {name} ---")
            parts.append(df.to_string(index=False))
        return "\n\n".join(parts), len(sheets)


class PlainTextExtractor(BaseExtractor):
    """Fallback — treat raw bytes as UTF-8 text."""

    def extract(self, data: bytes) -> Tuple[str, int]:
        return data.decode("utf-8", errors="replace"), 1


# ═══════════════════════════════════════════════════════
#  Factory
# ═══════════════════════════════════════════════════════

class ExtractorFactory:
    """
    Resolves a filename extension to the appropriate ``BaseExtractor``.

    Open/Closed: register new extractors without modifying existing code.
    """

    _registry: Dict[str, Type[BaseExtractor]] = {
        ".pdf":  PdfExtractor,
        ".docx": DocxExtractor,
        ".csv":  CsvExtractor,
        ".xlsx": ExcelExtractor,
        ".xls":  ExcelExtractor,
    }

    @classmethod
    def register(cls, extension: str, extractor_cls: Type[BaseExtractor]) -> None:
        cls._registry[extension.lower()] = extractor_cls

    @classmethod
    def get_extractor(cls, filename: str) -> BaseExtractor:
        suffix = Path(filename).suffix.lower()
        extractor_cls = cls._registry.get(suffix, PlainTextExtractor)
        return extractor_cls()

    @classmethod
    def extract_text(cls, file_bytes: bytes, filename: str) -> Tuple[str, int]:
        """Convenience: pick strategy and run extraction in one call."""
        extractor = cls.get_extractor(filename)
        return extractor.extract(file_bytes)
