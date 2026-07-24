"""RG-005 - Pais de alto riesgo - MEDIA - marca REVIEW (no rechaza)."""
from __future__ import annotations

from typing import Optional

from .base_rule import BaseRule, RuleAction, Severity, ValidationContext, Violation
from .utils import safe_str


class CountryRiskRule(BaseRule):
    """Marca para revision manual si el pais origen esta en la lista de riesgo.
    
    La lista es 100% configurable (``high_risk_countries`` en el YAML); por
    defecto se alinea a jurisdicciones tipo FATF. Un pais nulo no dispara la
    regla: la obligatoriedad del campo es decision de RG-008.
    """

    rule_id = "RG-005"
    name = "Pais de alto riesgo"
    severity = Severity.MEDIA
    action = RuleAction.REVIEW

    def evaluate(self, tx: dict, ctx: ValidationContext) -> Optional[Violation]:
        risky = {
            str(code).upper()
            for code in self.params.get("high_risk_countries", [])
        }
        country = safe_str(tx.get("country_code"))
        if country is not None and country.upper() in risky:
            return self.violation(
                f"Origin country '{country.upper()}' is on the high-risk list; "
                "manual review required",
                field="country_code",
            )
        return None