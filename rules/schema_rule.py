"""RG-008 - Esquema de datos invalido - CRITICA."""
from __future__ import annotations

from typing import Optional

from .base_rule import BaseRule, RuleAction, Severity, ValidationContext, Violation
from .utils import is_null, parse_utc_timestamp, safe_float, safe_int, safe_str


class SchemaRule(BaseRule):
    """Fallla si un campo obligatorio es nulo o si un campo presente tiene tipo invalido.
    
    Dos verificaciones complementarias:
      1. Nulabilidad: los campos de ``required_fields`` (configurable) no
         pueden estar ausentes.
      2. Tipado: todo campo *presente* (obligatorio u opcional) debe respetar
         su tipo/dominio declarado en el esquema de la prueba.
    """

    rule_id = "RG-008"
    name = "Esquema completo"
    severity = Severity.CRITICA
    action = RuleAction.REJECT

    DEFAULT_REQUIRED = (
        "transaction_id",
        "account_id",
        "amount",
        "currency",
        "transaction_type",
        "timestamp",
        "account_age_days",
        "daily_tx_count",
        "balance_before"
    )

    def _type_checks(self) -> dict[str, callable]:
        valid_types = {
            str(t).upper()
            for t in self.params.get(
                "valid_transaction_types",
                ("TRANSFER, PAYMENT, WITHDRAWAL, DEPOSIT"),
            )
        }
        none_negative_int = lambda v: (n := safe_int(v)) is not None and n >= 0
        return {
            "transaction_id": lambda v: safe_str(v) is not None,
            "account_id": lambda v: safe_str(v) is not None,
            "amount": lambda v: safe_float(v) is not None,
            "currency": lambda v: safe_str(v) is not None,
            "transaction_type": lambda v: (safe_str(v) or "").upper() in valid_types,
            "timestamp": lambda v: parse_utc_timestamp(v) is not None,
            "country_code": lambda v: safe_str(v) is not None,
            "merchant_category": lambda v: safe_str(v) is not None,
            "account_age_days": none_negative_int,
            "daily_tx_count": none_negative_int,
            "balance_before": lambda v: safe_float(v) is not None,
        }

    def evaluate(self, tx: dict, ctx: ValidationContext) -> Optional[Violation]:
        required = self.params.get("required_fields", self.DEFAULT_REQUIRED)
        problems: list[str] = []
        first_field: Optional[str] = None

        for field_name in required:
            if is_null(tx.get(field_name)):
                problems.append(f" '{field_name}' is null or missing")
                first_field = first_field or field_name

        for field_name, check in self._type_checks().items():
            value = tx.get(field_name)
            if is_null(value):
                continue
            if not check(value):
                problems.append(f"'{field_name}' has invalid type or value: {value!r}")
                first_field = first_field or field_name

        if problems:
            summary = "; ".join(problems[:5])
            if len(problems) > 5:
                summary += f" (+{len(problems) - 5} more)"
            return self.violation(f"Schema validation failed: {summary}", field=first_field)
        return None