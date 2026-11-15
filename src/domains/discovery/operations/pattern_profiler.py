import re
from typing import List, Optional, Any


class PatternProfiler:
    """Profiles attribute values using regex heuristics and cardinality."""

    # Regex definitions
    _UUID_RE = re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    )
    _HASH_RE = re.compile(
        r"^([0-9a-fA-F]{32}|[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$"
    )
    _ISO_TIME_RE = re.compile(
        r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:?\d{2})?$"
    )
    _UNIX_TIME_RE = re.compile(r"^\d{9,13}$")
    _IPV4_RE = re.compile(
        r"^((25[0-5]|(2[0-4]|1\d|[1-9]|)\d)\.?\b){4}$"
    )
    _IPV6_RE = re.compile(
        r"^([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$|^::$|^::1$|^([0-9a-fA-F]{1,4}:)+(:[0-9a-fA-F]{1,4})+$"
    )
    _URL_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*://\S+$")
    _EMAIL_RE = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
    _PHONE_RE = re.compile(r"^\+?[0-9\s().-]{7,25}$")
    _COORD_RE = re.compile(
        r"^[-+]?([1-8]?\d(\.\d+)?|90(\.0+)?),\s*[-+]?(180(\.0+)?|((1[0-7]\d)|([1-9]?\d))(\.\d+)?)$"
    )

    PATTERNS = [
        ("UUID", _UUID_RE),
        ("HASH", _HASH_RE),
        ("ISO_TIMESTAMP", _ISO_TIME_RE),
        ("UNIX_TIMESTAMP", _UNIX_TIME_RE),
        ("EMAIL", _EMAIL_RE),
        ("URL", _URL_RE),
        ("COORDINATES", _COORD_RE),
    ]

    def detect_single_value(self, val_str: str) -> Optional[str]:
        """Classifies a single string value into a pattern."""
        s = val_str.strip()
        if not s:
            return None

        # Check IP address first
        if self._IPV4_RE.match(s) or self._IPV6_RE.match(s):
            return "IP_ADDRESS"

        # Check standard patterns
        for name, rx in self.PATTERNS:
            if rx.match(s):
                return name

        # Phone check: ensure at least 7 digits to avoid matching plain short numbers or expressions
        if self._PHONE_RE.match(s):
            digits = sum(1 for c in s if c.isdigit())
            if digits >= 7 and not s.isdigit():  # pure digits without phone chars handled by unix time or int
                return "PHONE"
            elif digits >= 10:
                return "PHONE"

        return None

    def detect_pattern(self, samples: List[Any], threshold: float = 0.80) -> Optional[str]:
        """Returns the dominant pattern name if >= threshold of non-null samples match."""
        valid_samples = [str(s).strip() for s in samples if s is not None and str(s).strip() != ""]
        if not valid_samples:
            return None

        total = len(valid_samples)
        counts = {}

        for val in valid_samples:
            pat = self.detect_single_value(val)
            if pat:
                counts[pat] = counts.get(pat, 0) + 1

        for pat, count in counts.items():
            if (count / total) >= threshold:
                return pat

        return None

    def is_entity_candidate(
        self,
        pattern: Optional[str],
        cardinality_ratio: float = 0.0,
        physical_type: str = "VARCHAR",
    ) -> bool:
        """Determines if an attribute represents identifiable entities."""
        type_upper = physical_type.upper()
        if any(t in type_upper for t in ("DOUBLE", "FLOAT", "REAL", "DECIMAL", "NUMERIC", "BOOL", "DATE", "TIME")):
            return False

        if pattern in ("UUID", "HASH", "IP_ADDRESS", "EMAIL", "PHONE"):
            return True
        if pattern in ("ISO_TIMESTAMP", "UNIX_TIMESTAMP", "COORDINATES"):
            return False

        # Only high-cardinality string/id columns are treated as generic entities
        if cardinality_ratio >= 0.90:
            return True
        return False

