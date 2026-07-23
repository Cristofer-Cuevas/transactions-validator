"""Coercion segura de tipos para datos crudos provenientes de CVS/JSON.

Los registros pueden llegar con NaN de pandas, strings numericos, floats que
son enteros, etc. Estas funciones normalizan sin lanzar excepciones: devolver
``None`` significa "valor ausente o no interpretable".
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Optional


def is_null(value: Any) -> bool:
    """True si el valor esta ausente: None, NaN o string vacio."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False

def safe_float(value: Any) -> Optional[float]:
    """Convierte a float. None si es nulo, booleano o no convertible."""
    if is_null(value) or isinstance(value, bool):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(result) else result


