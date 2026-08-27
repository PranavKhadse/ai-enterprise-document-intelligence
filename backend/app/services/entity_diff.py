"""
Deterministic Entity & Metric Diff Engine.
Extracts and compares enterprise entities (durations, currency, percentages, dates,
versions, RFC/ISO standards, clause references, and numbers) between aligned clauses.
"""
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from backend.app.schemas.comparison import EntityDiffItem, EntityType

# Specialized Entity Patterns
DURATION_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(days?|months?|years?|weeks?|hours?|minutes?|secs?|seconds?|business\s+days?)\b",
    re.IGNORECASE,
)
CURRENCY_PATTERN = re.compile(
    r"(?:([\$€£¥₹])\s*(\d+(?:,\d{3})*(?:\.\d+)?)|(?:USD|EUR|GBP|INR|dollars?|cents?)\s*(\d+(?:,\d{3})*(?:\.\d+)?)|(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:USD|EUR|GBP|INR|dollars?|cents?))\b",
    re.IGNORECASE,
)
PERCENTAGE_PATTERN = re.compile(r"\b(\d+(?:\.\d+)?)\s*%", re.IGNORECASE)
DATE_ISO_PATTERN = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
DATE_STANDARD_PATTERN = re.compile(
    r"\b((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4}|\d{1,2}/\d{1,2}/\d{2,4})\b",
    re.IGNORECASE,
)
VERSION_PATTERN = re.compile(r"\bv?(\d+(?:\.\d+)+(?:-[a-zA-Z0-9]+)?)\b", re.IGNORECASE)
RFC_ISO_PATTERN = re.compile(r"\b(RFC-\d+|ISO-\d+|SOC-\d+|HIPAA|GDPR|NIST-\d+)\b", re.IGNORECASE)
CLAUSE_REF_PATTERN = re.compile(r"\b(Clause_\d+(?:\.\d+)*|Clause\s+\d+(?:\.\d+)*|Section\s+\d+(?:\.\d+)*)\b", re.IGNORECASE)
RAW_NUMBER_PATTERN = re.compile(r"\b\d+(?:,\d{3})*(?:\.\d+)?\b")


class EntityDiffEngine:
    """
    Deterministic extractor and differentiator for enterprise metrics and entities.
    """

    @staticmethod
    def normalize_currency(curr_match_tuple: tuple) -> Tuple[str, str]:
        """Normalizes diverse currency representations to standard code + number."""
        sym, amt1, amt2, amt3 = curr_match_tuple
        amt_raw = amt1 or amt2 or amt3
        clean_amt = amt_raw.replace(",", "").strip()

        sym_map = {"$": "USD", "€": "EUR", "£": "GBP", "₹": "INR", "¥": "JPY"}
        code = sym_map.get(sym, "USD")
        return f"{code} {clean_amt}", f"{sym or 'USD'}{clean_amt}"

    @staticmethod
    def normalize_duration(val: str, unit: str) -> str:
        """Standardizes duration into normalized unit representation."""
        num = float(val) if "." in val else int(val)
        unit_clean = unit.lower().rstrip("s")
        if unit_clean == "business day":
            return f"{num} business_days"
        return f"{num} {unit_clean}s" if num != 1 else f"{num} {unit_clean}"

    def extract_entities(self, text: str) -> Dict[str, List[Tuple[str, str]]]:
        """
        Extracts all recognized entity categories from text.
        Returns: {entity_type: [(raw_value, normalized_value), ...]}
        """
        if not text:
            return {}

        results: Dict[str, List[Tuple[str, str]]] = {
            EntityType.DURATION.value: [],
            EntityType.CURRENCY.value: [],
            EntityType.PERCENTAGE.value: [],
            EntityType.VERSION.value: [],
            EntityType.RFC.value: [],
            EntityType.ISO.value: [],
            EntityType.CLAUSE_REFERENCE.value: [],
            EntityType.DATE.value: [],
            EntityType.NUMBER.value: [],
        }

        # 1. Durations
        for m in DURATION_PATTERN.finditer(text):
            raw = m.group(0)
            norm = self.normalize_duration(m.group(1), m.group(2))
            results[EntityType.DURATION.value].append((raw, norm))

        # 2. Currency
        for m in CURRENCY_PATTERN.finditer(text):
            raw = m.group(0)
            norm, _ = self.normalize_currency(m.groups())
            results[EntityType.CURRENCY.value].append((raw, norm))

        # 3. Percentages
        for m in PERCENTAGE_PATTERN.finditer(text):
            raw = m.group(0)
            norm = f"{m.group(1)}%"
            results[EntityType.PERCENTAGE.value].append((raw, norm))

        # 4. Versions
        for m in VERSION_PATTERN.finditer(text):
            raw = m.group(0)
            norm = f"v{m.group(1)}"
            results[EntityType.VERSION.value].append((raw, norm))

        # 5. Standards (RFC / ISO)
        for m in RFC_ISO_PATTERN.finditer(text):
            raw = m.group(0)
            norm = raw.upper()
            if "RFC" in norm:
                results[EntityType.RFC.value].append((raw, norm))
            elif "ISO" in norm:
                results[EntityType.ISO.value].append((raw, norm))
            else:
                results[EntityType.IDENTIFIER.value if EntityType.IDENTIFIER.value in results else EntityType.ISO.value].append((raw, norm))

        # 6. Clause references
        for m in CLAUSE_REF_PATTERN.finditer(text):
            raw = m.group(0)
            norm = re.sub(r"\s+", "_", raw.lower())
            results[EntityType.CLAUSE_REFERENCE.value].append((raw, norm))

        # 7. Dates
        for m in DATE_ISO_PATTERN.finditer(text):
            raw = m.group(0)
            results[EntityType.DATE.value].append((raw, raw))
        for m in DATE_STANDARD_PATTERN.finditer(text):
            raw = m.group(0)
            results[EntityType.DATE.value].append((raw, raw))

        # 8. Raw Numbers (excluding numbers already captured in duration, currency, version, percentage)
        already_captured_nums = set()
        for cat in [EntityType.DURATION.value, EntityType.CURRENCY.value, EntityType.PERCENTAGE.value, EntityType.VERSION.value]:
            for raw, _ in results[cat]:
                for nm in RAW_NUMBER_PATTERN.findall(raw):
                    already_captured_nums.add(nm.replace(",", ""))

        for m in RAW_NUMBER_PATTERN.finditer(text):
            raw = m.group(0)
            clean_num = raw.replace(",", "")
            if clean_num not in already_captured_nums:
                results[EntityType.NUMBER.value].append((raw, clean_num))

        return {k: v for k, v in results.items() if v}

    def compute_entity_diffs(self, text_a: Optional[str], text_b: Optional[str]) -> List[EntityDiffItem]:
        """
        Compares entities extracted from Clause A against Clause B and identifies divergences.
        """
        if not text_a or not text_b:
            return []

        entities_a = self.extract_entities(text_a)
        entities_b = self.extract_entities(text_b)

        all_types = sorted(set(entities_a.keys()) | set(entities_b.keys()))
        diff_items: List[EntityDiffItem] = []

        for etype in all_types:
            items_a = entities_a.get(etype, [])
            items_b = entities_b.get(etype, [])

            # Pair items of same type
            max_len = max(len(items_a), len(items_b))
            for i in range(max_len):
                raw_a, norm_a = items_a[i] if i < len(items_a) else (None, None)
                raw_b, norm_b = items_b[i] if i < len(items_b) else (None, None)

                is_divergent = (norm_a != norm_b) or (norm_a is None) or (norm_b is None)

                diff_items.append(
                    EntityDiffItem(
                        entity_type=etype,
                        value_a=raw_a,
                        value_b=raw_b,
                        normalized_value_a=norm_a,
                        normalized_value_b=norm_b,
                        is_divergent=is_divergent,
                    )
                )

        return diff_items


# Global singleton
entity_diff_engine = EntityDiffEngine()
