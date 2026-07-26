"""Fixtures compartidos: configuración real del proyecto y fábrica de transacciones."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import pytest  # noqa: E402

from rules import ValidationContext  # noqa: E402
from validator import TransactionValidator, load_config  # noqa: E402


@pytest.fixture(scope="session")
def config() -> dict:
    return load_config(REPO_ROOT / "config" / "rules_config.yaml")


@pytest.fixture
def validator(config) -> TransactionValidator:
    return TransactionValidator(config)


@pytest.fixture
def ctx() -> ValidationContext:
    return ValidationContext()


@pytest.fixture
def valid_tx():
    """Fábrica de transacciones válidas; `overrides` permite romper campos puntuales."""

    def _make(**overrides) -> dict:
        tx = {
            "transaction_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
            "account_id": "acc-0001",
            "amount": 150.0,
            "currency": "USD",
            "transaction_type": "PAYMENT",
            "timestamp": "2025-01-10T14:30:00Z",
            "country_code": "DO",
            "merchant_category": "grocery",
            "account_age_days": 400,
            "daily_tx_count": 3,
            "is_flagged": False,
            "balance_before": 10_000.0,
        }
        tx.update(overrides)
        return tx

    return _make
