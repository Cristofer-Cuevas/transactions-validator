"""RG-001 MOnto minimo - CRITICA."""
from __future__ import annotations

from typing import Optional

from .base_rule import BaseRule, RuleAction, Severity, ValidationContext, Violation
from .utils import safe_float

class AmountRule(BaseRule):
    """Falla si ``amount`` es nulo, no numerico o menor o igual a cero."""

    rule_id = "RG-001"
    name = "Monto minimo"
    severity = Severity.CRTICA
    action = RuleAction.REJECT

    def evaluate(self, tx: dict, ctx: ValidationContext) -> Optional[Violation]:
        amount = safe_float(tx.get("amount"))
        if amount is None:
            return self.violation("Amount is null or not a valid number", field="amount")
        if amount <=0:
            return self.violation(
                f"Amount must be greater than 0, got {amount:,.2f}", field="amount"
            )
        return None

