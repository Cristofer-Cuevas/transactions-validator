"""RG-003 - Frecuencia de transacciones en cuentan nuevas - ALTA."""
from __future__ import annotations

from typing import Optional

from .base_rule import BaseRule, RuleAction, Severity, ValidationContext, Violation
from .utils import safe_int

class FrequencyRule(BaseRule):
    """Falla si ``daily_tx_count`` supera el maximo para cuentas jovenes."""

    rule_id = "RG-003"
    name = "Frecuencia de transacciones"
    severity = Severity.ALTA
    action = RuleAction.REJECT

    def evaluate(self, tx: dict, ctx: ValidationContext) -> Optional[Violation]:
        max_tx = int(self.params.get("max_daily_tx", 20))
        max_age = int(self.params.get("new_account_max_age_days", 30))
        tx_count = safe_int(tx.get("daily_tx_count"))
        age = safe_int(tx.get("account_age_days"))
        if tx_count is None or age is None:
            # Campos ausentes o malformados: los diagnostica RG-008 (esquema).
            return None
        if age < max_age and tx_count > max_tx:
            return self.violation(
                f"New account ({age} days old) exceeded frequency limit: "
                f"{tx_count} transactions today (max {max_tx})",
                field="daily_tx_count"
            )
        return None
