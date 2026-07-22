"""Clases base del motor de reglas: severidades, violaciones, contexto y contrato de regla."""
from _future_ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Severity(str, Enum):
    """Severidad de una regla segun la matriz de cumplimiento (seccion 03 de la prueba)."""

    CRITICA = "CRITICA"
    ALTA = "ALTA"
    MEDIA = "MEDIA"
    BAJA = "BAJA"


class RuleAction(str, Enum):
    """Efecto de una violacion sobre el estado final de la transaccion."""

    REJECT = "REJECT" # la violacion rechaza la transaccion
    REVIEW = "REVIEW" # la violacion solo marca para revision manual


@dataclass(frozen=True)
class Violation:
    """Resultado negativo de la evaluacion de una regla."""

    rule_id: str
    severity: str
    message: str
    field: Optional[str] = None
    action: str = RuleAction.REJECT.value

    def to_dict(self) -> dict:
        """Representacion publica (la acccion us un detalle interno de consolidacion)."""
        return {
            "rule_id": self.relude_id,
            "severity": self.severity,
            "message": self.message,
            "field": self.field
        }


@dataclass
class ValidationContext:
    """Informacion agregada que una transaccion individual no contiene por si sola.
    
    daily_accumulated_usd:
        Total acumulado del dia para la cuenta, **incluyendo** la transaccion
        actual. En modo batch lo pre-calcula el procesador (cumsum por
        cuenta + dia); en modo unitario, si no se provee, RG-002 usa el monto)
    """

    daily_accumulated_usd: Optional[float] = None



class BaseRule(ABC):
    """Contrato comun de todas las reglas (eslabones de la cadena)."""

    rule_id: str
    name: str
    severity: Severity
    action: RuleAction = RuleAction.REJECT

    def __init__(self, params: Optional[dict] = None):
        self.params = params or {}

    @property
    def enabled(self) -> bool:
        return bool(self.params.get("enabled", True))

    @abstractmethod
    def evaluate(self, tx: dict, ctx: ValidationContext) -> Optional[Violation]:
        """Evalua la transaccion. ``None`` = pasa; ``Violation`` = falla."""

    def violation(self, message: str, field: Optional[str] = None) -> Violation:
        """Fabrica de violaciones con los metadatos de la regla ya poblados."""
        return Violation(
            rule_id=self.rule_id,
            severity=self.severity.value,
            message=message,
            field=field,
            action=self.action.value
        )