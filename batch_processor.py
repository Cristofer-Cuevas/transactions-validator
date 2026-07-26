"""Tarea 2 · Procesamiento por lotes (batch validation).

Aplica el motor de reglas al dataset completo y genera un CSV con todas las
columnas originales + columnas de resultado de validación.

    python batch_processor.py \
        --input data/transactions.csv \
        --output data/validation_results.csv \
        [--config config/rules_config.yaml] [--workers 4]

Notas de diseño:
  * El acumulado diario por cuenta (insumo de RG-002) se pre-calcula de forma
    vectorizada con una suma acumulada por (account_id, fecha UTC) ordenada
    por timestamp, incluyendo la transacción actual.
  * Registros nulos o malformados nunca detienen el lote: la coerción segura
    vive en las reglas y, como última barrera, cada registro se valida dentro
    de un try/except que degrada a status ERROR.
  * ``--workers N`` paraleliza con ProcessPoolExecutor repartiendo el lote en
    chunks. Para 10k filas el modo secuencial ya es suficiente; el flag existe
    para demostrar el patrón de escalamiento (ver README para el trade-off).
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import time
from collections import Counter
from concurrent import futures
from typing import Optional

import pandas as pd

from rules import ValidationContext
from validator import TransactionValidator, _utc_now_iso, load_config

logger = logging.getLogger("batch_processor")

RESULT_COLUMNS = (
    "validation_status",
    "violated_rules",
    "violation_count",
    "violations_json",
    "rules_evaluated",
    "processing_ms",
    "evaluated_at",
)


def compute_daily_accumulated(df: pd.DataFrame) -> pd.Series:
    """Suma acumulada de montos por (cuenta, día UTC), incluyendo la fila actual.

    Decisiones:
      * Montos nulos o negativos aportan 0 al acumulado: son inválidos por
        RG-001 y no deben inflar el límite diario del resto de la cuenta.
      * Filas con timestamp no parseable no pueden asignarse a un día: su
        acumulado degrada al monto propio de la transacción.
    """
    timestamps = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
    amounts = pd.to_numeric(df["amount"], errors="coerce").fillna(0.0).clip(lower=0.0)

    frame = pd.DataFrame(
        {
            "account_id": df["account_id"],
            "day": timestamps.dt.date,
            "amount": amounts,
        }
    )
    chronological = frame.loc[timestamps.sort_values(kind="stable").index]
    accumulated = chronological.groupby(["account_id", "day"], dropna=False)[
        "amount"
    ].cumsum()
    accumulated = accumulated.reindex(df.index)
    # Sin fecha válida no hay "día": degradar al monto propio.
    return accumulated.where(timestamps.notna(), amounts)


def to_records(df: pd.DataFrame) -> list[dict]:
    """Convierte el DataFrame en dicts nativos, con None en lugar de NaN/NaT."""
    sanitized = df.astype(object).where(pd.notna(df), None)
    return sanitized.to_dict(orient="records")


def validate_records(
    records: list[dict],
    accumulated: list[Optional[float]],
    config: dict,
) -> list[dict]:
    """Valida una secuencia de registros. Nunca lanza: degrada a status ERROR."""
    validator = TransactionValidator(config)
    results: list[dict] = []
    for tx, daily_total in zip(records, accumulated):
        try:
            ctx = ValidationContext(daily_accumulated_usd=daily_total)
            results.append(validator.validate(tx, ctx))
        except Exception as exc:  # noqa: BLE001 — un registro corrupto no detiene el lote
            logger.warning(
                "Registro no procesable (tx=%s): %s", tx.get("transaction_id"), exc
            )
            results.append(
                {
                    "transaction_id": tx.get("transaction_id"),
                    "status": "ERROR",
                    "evaluated_at": _utc_now_iso(),
                    "violations": [],
                    "rules_evaluated": 0,
                    "processing_ms": 0.0,
                }
            )
    return results


def _worker(payload: tuple[list[dict], list[Optional[float]], dict]) -> list[dict]:
    records, accumulated, config = payload
    return validate_records(records, accumulated, config)


def _chunk(sequence: list, n_chunks: int) -> list[list]:
    size = math.ceil(len(sequence) / n_chunks)
    return [sequence[i : i + size] for i in range(0, len(sequence), size)]


def run_batch(
    df: pd.DataFrame, config: dict, workers: int = 1
) -> tuple[pd.DataFrame, list[dict]]:
    """Ejecuta la validación sobre el DataFrame y adjunta las columnas de resultado."""
    accumulated = compute_daily_accumulated(df)
    records = to_records(df)
    accumulated_list = [None if pd.isna(x) else float(x) for x in accumulated]

    if workers > 1:
        payloads = list(
            zip(
                _chunk(records, workers),
                _chunk(accumulated_list, workers),
                [config] * workers,
            )
        )
        with futures.ProcessPoolExecutor(max_workers=workers) as pool:
            chunks = list(pool.map(_worker, payloads))
        results = [row for chunk in chunks for row in chunk]
    else:
        results = validate_records(records, accumulated_list, config)

    output = df.copy()
    output["validation_status"] = [r["status"] for r in results]
    output["violated_rules"] = [
        "|".join(v["rule_id"] for v in r["violations"]) for r in results
    ]
    output["violation_count"] = [len(r["violations"]) for r in results]
    output["violations_json"] = [
        json.dumps(r["violations"], ensure_ascii=False) for r in results
    ]
    output["rules_evaluated"] = [r["rules_evaluated"] for r in results]
    output["processing_ms"] = [r["processing_ms"] for r in results]
    output["evaluated_at"] = [r["evaluated_at"] for r in results]
    return output, results


def log_summary(results: list[dict], elapsed_seconds: float) -> None:
    status_counts = Counter(r["status"] for r in results)
    rule_counts = Counter(v["rule_id"] for r in results for v in r["violations"])

    logger.info("=" * 62)
    logger.info("Resumen del lote")
    logger.info("-" * 62)
    logger.info("Total procesado : %6d", len(results))
    logger.info("Aprobadas       : %6d", status_counts.get("APPROVED", 0))
    logger.info("Rechazadas      : %6d", status_counts.get("REJECTED", 0))
    logger.info("En revisión     : %6d", status_counts.get("REVIEW", 0))
    logger.info("Errores         : %6d", status_counts.get("ERROR", 0))
    logger.info("Tiempo total    : %6.2f s", elapsed_seconds)
    logger.info("-" * 62)
    logger.info("Violaciones por regla:")
    for rule_id in sorted(rule_counts):
        logger.info("  %s -> %d", rule_id, rule_counts[rule_id])
    logger.info("=" * 62)


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Valida un dataset completo de transacciones.")
    parser.add_argument("--input", default="data/transactions.csv")
    parser.add_argument("--output", default="data/validation_results.csv")
    parser.add_argument("--config", default=None, help="Ruta alternativa al YAML de configuración.")
    parser.add_argument("--workers", type=int, default=1, help="Procesos en paralelo (default: 1).")
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    )
    args = _parse_args(argv)
    config = load_config(args.config)

    logger.info("Leyendo dataset: %s", args.input)
    df = pd.read_csv(args.input)
    logger.info("Registros leídos: %d | columnas: %d", len(df), df.shape[1])

    start = time.perf_counter()
    output, results = run_batch(df, config, workers=max(1, args.workers))
    elapsed = time.perf_counter() - start

    output.to_csv(args.output, index=False)
    logger.info("Resultados escritos en: %s", args.output)
    log_summary(results, elapsed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
