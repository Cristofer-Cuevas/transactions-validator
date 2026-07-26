"""Catalogo de reglas del motor de validacion.

``RULE_REGISTRY`` define la cadena (Chain of Responsibility): las reglas se
evaluan en orden ascendente de ID y la primera vilolacion de severidad CRITICA
corta la cadena. Registrar una regla nueva = agregar la clase a esta lista.
"""
from .base_rule import (
    BaseRule,
    RuleAction,
    Severity,
    ValidationContext,
    Violation,
)
from .amount_rule import AmountRule
from .daily_limit_rule import DailyLimitRule
from .frequency_rule import FrequencyRule
from .currency_rule import CurrencyRule
from .country_risk_rule import CountryRiskRule
from .funds_rule import FundsRule
from .unusual_hour_rule import UnusualHourRule
from .schema_rule import SchemaRule

RULE_REGISTRY: list[type[BaseRule]] = [
    AmountRule,        # RG-001 - CRITICA
    DailyLimitRule,    # RG-002 - ALTA
    FrequencyRule,     # RG-003 - ALTA
    CurrencyRule,      # RG-004 - CRITICA
    CountryRiskRule,   # RG-005 - MEDIA -> REVIEW
    FundsRule,         # RG-006 - CRITICA
    UnusualHourRule,   # RG-007 - BAJA -> REVIEW
    SchemaRule,        # RG-008 - CRITICA
]

__all__ = [
    "BaseRule",
    "RuleAction",
    "Severity",
    "ValidationContext",
    "Violation",
    "AmountRule",
    "DailyLimitRule",
    "FrequencyRule",
    "CurrencyRule",
    "CountryRiskRule",
    "FundsRule",
    "UnusualHourRule",
    "SchemaRule",
    "RULE_REGISTRY",
]