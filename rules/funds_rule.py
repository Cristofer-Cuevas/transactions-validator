"""RG-006 - Fondos insuficientes - CRITICA"""
from __future__ import annotations

from typing import Optional

from .base_rule import BaseRule, RuleAction, Severity, ValidationContext, Violation
from .utils import safe_float, safe_str


class FundsRule(BaseRule):
    """Falla si ``amount`` es mayor que ``available_balance``.
    
    Postura conservadora: si el tipo es debito y ``balance_before`` no esta
    disponible, la transaccion tambien falla, un core bancario nunca deberia
    autorizar un debito sin poder verificar fondos.
    """

    rule_id = "RG-006"
    name = "Fondos insuficientes"
    severity = Severity.CRITICA
    action = RuleAction.REJECT

    DEFAULT_DEBIT_TYPES = ("WITHDRAWAL", "TRANSFER")

    def evaluate(self, tx: dict, ctx: ValidationContext) -> Optional[Violation]:
        debit_types = {
            str(t).upper()
            for t in self.params.get("debit_types", self.DEFAULT_DEBIT_TYPES)
        }
        tx_type = safe_str(tx.get("transaction_type"))
        if tx_type is None or tx_type.upper() not in debit_types:
            return None

        amount = safe_float(tx.get("amount"))
        if amount is None or amount <= 0:
            # Montos invalidos son competencia exclusiva de RG-001
            return None

        balance = safe_float(tx.get("balance_before"))
        if balance is None:
            return self.violation(
                "Cannot verify funds: balance_before is missing for a debit "
                "transaction",
                field="balance_before"
            )
        if amount > balance:
            return self.violation(
                f"Insufficient funds: amount ${amount:,.2f} exceeds available "
                f"balance ${balance:,.2f}",
                field="amount"
            )
        return None
