"""RG-007 - Horario inusual - BAJA - marca REVIEW (no rechaza)"""
from __future__ import annotations

from typing import Optional

from .base_rule import BaseRule, RuleAction, Severity, ValidationContext, Violation
from .utils import parse_utc_timestamp, safe_float


class UnusualHourRule(BaseRule):
    """Marca REVIEW si hay monto alto en la ventana nocturna UTC configurada.
    
    Ventana semiabierta ``[start, end)``: 02:00:00 esta dentro y 05:00:00 ya 
    queda fuera, para que dos ventanas contiguas nunca solapen.
    """

    rule_id = "RG-007"
    name = "Horario inusual"
    severity = Severity.BAJA
    action = RuleAction.REVIEW

    def evaluate(self, tx: dict, ctx: ValidationContext) -> Optional[Violation]:
        start_hour = int(self.params.get("start_hour_utc", 2))
        end_hour = int(self.params.get("end_hour_utc", 5))
        threshold = float(self.params.get("amount_threshold_usd", 5_000))

        timestamp = parse_utc_timestamp(tx.get("timestamp"))
        amount = safe_float(tx.get("amount"))
        if timestamp is None or amount is None:
            # Timestamp/monto malformados los diagnostican RG-008 y RG-001.
            return None

        if start_hour <= timestamp.hour < end_hour and amount > threshold:
            return self.violation(
                f"High amount ${amount:,.2f} at unusual hour "
                f"{timestamp.strftime('$H:%M')} UTC "
                f"({start_hour:02d}:00-{end_hour:02d}:00 window)",
                field="timestamp"
            )
        return None