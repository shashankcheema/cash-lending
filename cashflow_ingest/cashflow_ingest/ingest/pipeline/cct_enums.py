from __future__ import annotations

from enum import Enum


class CCT(str, Enum):
    FREE = "FREE"
    CONSTRAINED = "CONSTRAINED"
    PASS_THROUGH = "PASS_THROUGH"
    ARTIFICIAL = "ARTIFICIAL"
    CONDITIONAL = "CONDITIONAL"
    UNKNOWN = "UNKNOWN"
