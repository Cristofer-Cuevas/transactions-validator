"""Bonus · API REST mínima que expone el motor de validación (Tarea 1).

Levantar en local:
    uvicorn api:app --reload

Ejemplos:
    curl localhost:8000/health
    curl -X POST localhost:8000/validate \
         -H 'Content-Type: application/json' \
         -d @examples/tx_invalid.json
"""
from __future__ import annotations

from typing import Optional

from fastapi import Body, FastAPI

from rules import ValidationContext
from validator import TransactionValidator

app = FastAPI(
    title="Motor de Validación de Transacciones",
    description="Aplica las 8 reglas de negocio de cumplimiento a una transacción.",
    version="1.0.0",
)

_validator = TransactionValidator()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "rules_loaded": len(_validator.rules)}


@app.post("/validate")
def validate(
    tx: dict = Body(..., description="Transacción cruda a validar."),
    daily_accumulated_usd: Optional[float] = None,
) -> dict:
    """Valida una transacción individual.

    Decisión de diseño: el body se recibe como ``dict`` crudo en lugar de un
    modelo Pydantic estricto. La validación de esquema es responsabilidad de
    RG-008; un 422 automático de FastAPI ocultaría el diagnóstico estructurado
    (status + violations) que el área de cumplimiento espera del motor.
    """
    ctx = ValidationContext(daily_accumulated_usd=daily_accumulated_usd)
    return _validator.validate(tx, ctx)
