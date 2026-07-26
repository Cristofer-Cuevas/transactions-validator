"""Tests de integración del motor: cortocircuito, consolidación de estado y contrato de salida."""
from __future__ import annotations

import copy

from rules import ValidationContext
from validator import TransactionValidator

EXPECTED_KEYS = {
    "transaction_id",
    "status",
    "evaluated_at",
    "violations",
    "rules_evaluated",
    "processing_ms",
}


class TestOutputContract:
    def test_estructura_de_respuesta(self, validator, valid_tx):
        result = validator.validate(valid_tx())
        assert set(result.keys()) == EXPECTED_KEYS
        assert result["transaction_id"] == valid_tx()["transaction_id"]
        assert result["evaluated_at"].endswith("Z")
        assert isinstance(result["processing_ms"], float)

    def test_transaccion_valida_es_aprobada(self, validator, valid_tx):
        result = validator.validate(valid_tx())
        assert result["status"] == "APPROVED"
        assert result["violations"] == []
        assert result["rules_evaluated"] == 8  # ninguna crítica cortó la cadena


class TestConsolidacionDeEstado:
    def test_violacion_alta_rechaza_pero_no_corta(self, validator, valid_tx):
        # Réplica del ejemplo de la prueba: solo RG-002 dispara -> rules_evaluated = 8.
        ctx = ValidationContext(daily_accumulated_usd=52_400.0)
        result = validator.validate(valid_tx(), ctx)
        assert result["status"] == "REJECTED"
        assert [v["rule_id"] for v in result["violations"]] == ["RG-002"]
        assert result["rules_evaluated"] == 8

    def test_solo_reglas_review_dan_status_review(self, validator, valid_tx):
        result = validator.validate(valid_tx(country_code="IR"))
        assert result["status"] == "REVIEW"
        assert [v["rule_id"] for v in result["violations"]] == ["RG-005"]

    def test_review_mas_rechazo_consolida_en_rejected(self, validator, valid_tx):
        ctx = ValidationContext(daily_accumulated_usd=60_000.0)
        result = validator.validate(valid_tx(country_code="IR"), ctx)
        assert result["status"] == "REJECTED"
        assert {v["rule_id"] for v in result["violations"]} == {"RG-002", "RG-005"}


class TestCortocircuito:
    def test_critica_temprana_corta_la_cadena(self, validator, valid_tx):
        # RG-001 (posición 1) dispara y evita evaluar el resto, incluida una
        # moneda inválida que habría disparado RG-004.
        result = validator.validate(valid_tx(amount=-10.0, currency="BTC"))
        assert result["status"] == "REJECTED"
        assert [v["rule_id"] for v in result["violations"]] == ["RG-001"]
        assert result["rules_evaluated"] == 1

    def test_critica_intermedia_conserva_violaciones_previas(self, validator, valid_tx):
        # RG-002 (ALTA) dispara y la cadena continúa hasta RG-006 (CRÍTICA),
        # que corta antes de RG-007/RG-008.
        ctx = ValidationContext(daily_accumulated_usd=80_000.0)
        tx = valid_tx(transaction_type="WITHDRAWAL", amount=80_000.0, balance_before=1_000.0)
        result = validator.validate(tx, ctx)
        assert result["status"] == "REJECTED"
        assert [v["rule_id"] for v in result["violations"]] == ["RG-002", "RG-006"]
        assert result["rules_evaluated"] == 6

    def test_critica_corta_antes_de_reglas_review(self, validator, valid_tx):
        # RG-004 (posición 4, CRÍTICA) corta antes de que RG-005 pudiera marcar.
        result = validator.validate(valid_tx(currency="IRR", country_code="IR"))
        assert [v["rule_id"] for v in result["violations"]] == ["RG-004"]
        assert result["rules_evaluated"] == 4


class TestConfigurabilidad:
    def test_regla_deshabilitada_sale_de_la_cadena(self, config, valid_tx):
        modified = copy.deepcopy(config)
        modified["rules"]["RG-005"]["enabled"] = False
        validator = TransactionValidator(modified)
        result = validator.validate(valid_tx(country_code="IR"))
        assert result["status"] == "APPROVED"  # nadie marca el país de riesgo
        assert result["rules_evaluated"] == 7

    def test_parametros_del_yaml_gobiernan_la_regla(self, config, valid_tx):
        modified = copy.deepcopy(config)
        modified["rules"]["RG-002"]["daily_limit_usd"] = 100.0
        validator = TransactionValidator(modified)
        result = validator.validate(valid_tx(amount=150.0))
        assert any(v["rule_id"] == "RG-002" for v in result["violations"])


class TestResiliencia:
    def test_transaccion_vacia_no_lanza(self, validator):
        result = validator.validate({})
        assert result["status"] == "REJECTED"
        assert result["violations"][0]["rule_id"] == "RG-001"  # corta en la primera crítica

    def test_tipos_absurdos_no_lanzan(self, validator, valid_tx):
        tx = valid_tx(amount=[1, 2], timestamp={"a": 1}, daily_tx_count="muchas")
        result = validator.validate(tx)  # no debe lanzar excepción
        assert result["status"] == "REJECTED"
