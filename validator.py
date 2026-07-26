"""Tarea 1 · Motor de reglas de negocio.

Recibe una transacción como JSON/dict y devuelve el resultado de validación
con el formato exigido por la prueba (seccion 04). Ejemplos de uso por CLI:

    python validator.py --file examples/tx_valid.json --pretty
    python validator.py --json '{"transaction_id": "abc", "amount": -5, ...}'

La configuración se resuelve con esta prioridad:
    argumento --config  >  variable de entorno RULES_CONFIG_PATH  >  config/rules_config.yaml
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import yaml

from rules import (
    RULE_REGISTRY,
    BaseRule,
    RuleAction,
    Severity,
    ValidationContext,
    Violation,
)

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "config" / "rules_config.yaml"


def load_config(path: Optional[str | Path] = None) -> dict:
    """Carga la configuración YAML externalizada del motor."""
    config_path = Path(path or os.environ.get("RULES_CONFIG_PATH", DEFAULT_CONFIG_PATH))
    with open(config_path, encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


class TransactionValidator:
    """Orquestador de la cadena de reglas (Chain of Responsibility).

    Contrato de la cadena:
      * Las reglas habilitadas se evalúan en orden ascendente de ID.
      * Una violación de severidad CRÍTICA hace cortocircuito: el resto de la
        cadena no se evalúa (las violaciones ya acumuladas sí se reportan).
      * Consolidación del estado final:
          - REJECTED  si existe al menos una violación con acción REJECT
                      (severidades CRÍTICA/ALTA).
          - REVIEW    si solo existen violaciones con acción REVIEW
                      (RG-005 y RG-007, que marcan sin rechazar).
          - APPROVED  si no hubo violaciones.
    """

    def __init__(self, config: Optional[dict] = None) -> None:
        if config is None:
            config = load_config()
        rule_params: dict = config.get("rules", {})
        self.rules: list[BaseRule] = []
        for rule_cls in RULE_REGISTRY:
            rule = rule_cls(rule_params.get(rule_cls.rule_id, {}))
            if rule.enabled:
                self.rules.append(rule)

    def validate(self, tx: dict, ctx: Optional[ValidationContext] = None) -> dict:
        """Evalúa la cadena completa para una transacción y consolida el resultado."""
        start = time.perf_counter()
        ctx = ctx or ValidationContext()
        violations: list[Violation] = []
        rules_evaluated = 0

        for rule in self.rules:
            rules_evaluated += 1
            try:
                result = rule.evaluate(tx, ctx)
            except Exception as exc:  # noqa: BLE001 — una regla defectuosa no tumba el motor
                result = Violation(
                    rule_id=rule.rule_id,
                    severity=rule.severity.value,
                    message=f"Internal error evaluating rule: {exc}",
                    field=None,
                    action=RuleAction.REJECT.value,
                )
            if result is not None:
                violations.append(result)
                if rule.severity is Severity.CRITICA:
                    break  # cortocircuito exigido por la prueba

        processing_ms = round((time.perf_counter() - start) * 1000, 3)
        return {
            "transaction_id": tx.get("transaction_id"),
            "status": self._consolidate(violations),
            "evaluated_at": _utc_now_iso(),
            "violations": [violation.to_dict() for violation in violations],
            "rules_evaluated": rules_evaluated,
            "processing_ms": processing_ms,
        }

    @staticmethod
    def _consolidate(violations: list[Violation]) -> str:
        if any(v.action == RuleAction.REJECT.value for v in violations):
            return "REJECTED"
        if violations:
            return "REVIEW"
        return "APPROVED"


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Valida una transacción individual.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--json", help="Transacción como string JSON.")
    source.add_argument("--file", help="Ruta a un archivo JSON con la transacción.")
    parser.add_argument("--config", help="Ruta alternativa al YAML de configuración.")
    parser.add_argument(
        "--accumulated",
        type=float,
        default=None,
        help="Acumulado diario de la cuenta en USD (opcional, alimenta RG-002).",
    )
    parser.add_argument("--pretty", action="store_true", help="Salida indentada.")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    if args.json:
        tx = json.loads(args.json)
    else:
        with open(args.file, encoding="utf-8") as handle:
            tx = json.load(handle)

    validator = TransactionValidator(load_config(args.config))
    ctx = ValidationContext(daily_accumulated_usd=args.accumulated)
    result = validator.validate(tx, ctx)
    print(json.dumps(result, indent=2 if args.pretty else None, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
