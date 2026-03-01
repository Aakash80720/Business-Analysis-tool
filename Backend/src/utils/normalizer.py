"""
Entity normalizer — aligns terminology across documents.

e.g.  "ROI", "Return on Investment", "R.O.I." → "Return on Investment"
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional


class EntityNormalizer:
    """
    Rule-based + synonym-dict normalizer.

    Usage::

        norm = EntityNormalizer()
        norm.add_synonym("ROI", "Return on Investment")
        norm.add_synonym("R.O.I.", "Return on Investment")
        cleaned = norm.normalize("Our ROI improved by 12%.")
        # → "Our Return on Investment improved by 12%."
    """

    def __init__(self) -> None:
        self._synonyms: Dict[str, str] = {}   # lowered-key → canonical
        self._compiled: Optional[re.Pattern] = None

    # ── public ──

    def add_synonym(self, variant: str, canonical: str) -> None:
        self._synonyms[variant.lower()] = canonical
        self._compiled = None  # invalidate cache

    def add_synonyms(self, mapping: Dict[str, str]) -> None:
        for variant, canonical in mapping.items():
            self.add_synonym(variant, canonical)

    def normalize(self, text: str) -> str:
        """Replace every known variant with its canonical form."""
        if not self._synonyms:
            return text
        pattern = self._get_pattern()
        return pattern.sub(self._replace, text)

    def extract_entities(self, text: str) -> List[str]:
        """Return list of canonical entities found in *text*."""
        if not self._synonyms:
            return []
        found: List[str] = []
        pattern = self._get_pattern()
        for match in pattern.finditer(text):
            canonical = self._synonyms[match.group(0).lower()]
            if canonical not in found:
                found.append(canonical)
        return found

    # ── private ──

    def _get_pattern(self) -> re.Pattern:
        if self._compiled is None:
            escaped = [re.escape(k) for k in sorted(self._synonyms, key=len, reverse=True)]
            self._compiled = re.compile("|".join(escaped), re.IGNORECASE)
        return self._compiled

    def _replace(self, match: re.Match) -> str:
        return self._synonyms[match.group(0).lower()]
