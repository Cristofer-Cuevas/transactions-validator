"""RG-004 - Moneda permitida - CRITICA"""
from __future__ import annotations

from typing import Optional

from .base_rule import BaseRule, RuleAction, Severity, ValidationContext, Violation
from .utils import safe_str


class CurrencyRule(BaseRule):
    """Falla si ``currency`` no pertenece al catalogo de monedas aprobadas."""

    rule_id = "RG-004"
    name = "Moneda permitida"
    severity = Severity.CRITICA
    action = RuleAction.REJECT

    DEFAULT_ALLOWED = ("USD", "DOP", "EUR", "CAD", "GBP")

    def evaluate(self, tx: dict, ctx: ValidationContext) -> Optional[Violation]:
        allowed = {
            str(code).upper()
            for code in self.params.get("allowed_currencies", self.DEFAULT_ALLOWED)
        }
        currency = safe_str(tx.get("currency"))
        if currency is None:
            return self.violation("Currency is missing", field="currency")
        if currency.upper() not in allowed:
            return self.violation(
                f"Currency '{currency}` is not in the approved catalog "
                f"{sorted(allowed)}",
                field="currency"
            )
        return None