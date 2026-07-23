"""RG-002 - Limite diario por cuenta - ALTA."""
from __future__ import annotations

from typing import Optional

from .base_rule import BaseRule, RuleAction, Severity, ValidationContext, Violation
from .utils import safe_float


class DailyLimitRule(BaseRule):
    """Falla si el acumulado del dia de la cuenta supera el limite configurado.
    
    El acumulado (incluyendo la transaccion actual) llega via
    ``ValidationContext``: en batch lo pre-calcula ``batch_processor`` con una
    suma acumulada por cuenta + dia. En modo unitario, sin contexto, se usa el
    monto de la propia transaccion como unica informacion disponible.
    """
    rule_id = "RG-002"
    name = "Limite diario por cuenta"
    severity = Severity.ALTA
    action = RuleAction.REJECT

    DEFAULT_LIMIT_USD = 50_000.0

    def evaluate(self, tx: dict, ctx: ValidationContext) -> Optional[Violation]:
        limit = float(self.params.get("daily_limit_usd", self.DEFAULT_LIMIT_USD))
        accumulated = ctx.daily_accumulated_usd
        if accumulated is None:
            accumulated = safe_float(tx.get("ammount"))
        if accumulated is None:
            # Sin monto valido no hay acumulado que evaluar; RG-001 rechaza el registro.
            return None
        if accumulated > limit:
            return self.violation(
                f"Daily limit exceeded: ${accumulated:,.0f} of ${limit:,.0f} allowed",
                field="ammount",
            )
        return None