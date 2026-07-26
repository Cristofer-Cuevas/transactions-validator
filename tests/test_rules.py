"""Tests unitarios por regla: caso válido + casos de fallo (requisito de la prueba)."""
from __future__ import annotations

import pytest

from rules import (
    AmountRule,
    CountryRiskRule,
    CurrencyRule,
    DailyLimitRule,
    FrequencyRule,
    FundsRule,
    SchemaRule,
    UnusualHourRule,
    ValidationContext,
)


def make_rule(config, rule_cls):
    """Instancia la regla con los mismos parámetros del YAML del proyecto."""
    return rule_cls(config["rules"][rule_cls.rule_id])


# ------------------------------------------------------------------ RG-001
class TestAmountRule:
    def test_monto_positivo_pasa(self, config, valid_tx, ctx):
        assert make_rule(config, AmountRule).evaluate(valid_tx(amount=0.01), ctx) is None

    @pytest.mark.parametrize("bad_amount", [0, -25.5, None, "abc", float("nan")])
    def test_montos_invalidos_fallan(self, config, valid_tx, ctx, bad_amount):
        violation = make_rule(config, AmountRule).evaluate(valid_tx(amount=bad_amount), ctx)
        assert violation is not None
        assert violation.rule_id == "RG-001"
        assert violation.severity == "CRITICA"


# ------------------------------------------------------------------ RG-002
class TestDailyLimitRule:
    def test_bajo_el_limite_pasa(self, config, valid_tx):
        ctx = ValidationContext(daily_accumulated_usd=49_999.99)
        assert make_rule(config, DailyLimitRule).evaluate(valid_tx(), ctx) is None

    def test_acumulado_sobre_limite_falla(self, config, valid_tx):
        ctx = ValidationContext(daily_accumulated_usd=52_400.0)
        violation = make_rule(config, DailyLimitRule).evaluate(valid_tx(), ctx)
        assert violation is not None
        assert violation.severity == "ALTA"
        assert "$52,400" in violation.message and "$50,000" in violation.message

    def test_modo_unitario_usa_monto_propio(self, config, valid_tx, ctx):
        # Sin contexto de acumulado, un monto que por sí solo excede el límite falla.
        violation = make_rule(config, DailyLimitRule).evaluate(valid_tx(amount=60_000.0), ctx)
        assert violation is not None and violation.rule_id == "RG-002"

    def test_sin_monto_ni_contexto_no_evalua(self, config, valid_tx, ctx):
        # El monto nulo es competencia de RG-001, no de esta regla.
        assert make_rule(config, DailyLimitRule).evaluate(valid_tx(amount=None), ctx) is None


# ------------------------------------------------------------------ RG-003
class TestFrequencyRule:
    def test_cuenta_madura_con_alta_frecuencia_pasa(self, config, valid_tx, ctx):
        tx = valid_tx(account_age_days=365, daily_tx_count=30)
        assert make_rule(config, FrequencyRule).evaluate(tx, ctx) is None

    def test_cuenta_nueva_con_alta_frecuencia_falla(self, config, valid_tx, ctx):
        tx = valid_tx(account_age_days=10, daily_tx_count=25)
        violation = make_rule(config, FrequencyRule).evaluate(tx, ctx)
        assert violation is not None and violation.severity == "ALTA"

    def test_limite_es_estricto_mayor_que_20(self, config, valid_tx, ctx):
        tx = valid_tx(account_age_days=10, daily_tx_count=20)  # exactamente 20 no falla
        assert make_rule(config, FrequencyRule).evaluate(tx, ctx) is None


# ------------------------------------------------------------------ RG-004
class TestCurrencyRule:
    @pytest.mark.parametrize("good", ["USD", "DOP", "eur"])  # case-insensitive
    def test_monedas_del_catalogo_pasan(self, config, valid_tx, ctx, good):
        assert make_rule(config, CurrencyRule).evaluate(valid_tx(currency=good), ctx) is None

    @pytest.mark.parametrize("bad", ["IRR", "KPW", "BTC", None])
    def test_monedas_fuera_del_catalogo_fallan(self, config, valid_tx, ctx, bad):
        violation = make_rule(config, CurrencyRule).evaluate(valid_tx(currency=bad), ctx)
        assert violation is not None
        assert violation.rule_id == "RG-004"
        assert violation.severity == "CRITICA"


# ------------------------------------------------------------------ RG-005
class TestCountryRiskRule:
    def test_pais_seguro_pasa(self, config, valid_tx, ctx):
        assert make_rule(config, CountryRiskRule).evaluate(valid_tx(country_code="DO"), ctx) is None

    def test_pais_de_riesgo_marca_review(self, config, valid_tx, ctx):
        violation = make_rule(config, CountryRiskRule).evaluate(valid_tx(country_code="VE"), ctx)
        assert violation is not None
        assert violation.severity == "MEDIA"
        assert violation.action == "REVIEW"  # marca, no rechaza

    def test_pais_nulo_no_dispara(self, config, valid_tx, ctx):
        assert make_rule(config, CountryRiskRule).evaluate(valid_tx(country_code=None), ctx) is None


# ------------------------------------------------------------------ RG-006
class TestFundsRule:
    def test_debito_con_fondos_pasa(self, config, valid_tx, ctx):
        tx = valid_tx(transaction_type="WITHDRAWAL", amount=100.0, balance_before=500.0)
        assert make_rule(config, FundsRule).evaluate(tx, ctx) is None

    @pytest.mark.parametrize("debit_type", ["WITHDRAWAL", "TRANSFER"])
    def test_debito_sin_fondos_falla(self, config, valid_tx, ctx, debit_type):
        tx = valid_tx(transaction_type=debit_type, amount=900.0, balance_before=100.0)
        violation = make_rule(config, FundsRule).evaluate(tx, ctx)
        assert violation is not None and violation.severity == "CRITICA"

    def test_deposito_sin_fondos_no_aplica(self, config, valid_tx, ctx):
        tx = valid_tx(transaction_type="DEPOSIT", amount=900.0, balance_before=100.0)
        assert make_rule(config, FundsRule).evaluate(tx, ctx) is None

    def test_debito_sin_balance_falla_conservadoramente(self, config, valid_tx, ctx):
        tx = valid_tx(transaction_type="TRANSFER", balance_before=None)
        violation = make_rule(config, FundsRule).evaluate(tx, ctx)
        assert violation is not None and violation.field == "balance_before"


# ------------------------------------------------------------------ RG-007
class TestUnusualHourRule:
    def test_monto_alto_en_horario_normal_pasa(self, config, valid_tx, ctx):
        tx = valid_tx(timestamp="2025-01-10T14:30:00Z", amount=9_000.0)
        assert make_rule(config, UnusualHourRule).evaluate(tx, ctx) is None

    def test_monto_bajo_en_madrugada_pasa(self, config, valid_tx, ctx):
        tx = valid_tx(timestamp="2025-01-10T03:15:00Z", amount=4_999.0)
        assert make_rule(config, UnusualHourRule).evaluate(tx, ctx) is None

    def test_monto_alto_en_madrugada_marca_review(self, config, valid_tx, ctx):
        tx = valid_tx(timestamp="2025-01-10T03:15:00Z", amount=6_000.0)
        violation = make_rule(config, UnusualHourRule).evaluate(tx, ctx)
        assert violation is not None
        assert violation.severity == "BAJA"
        assert violation.action == "REVIEW"

    def test_ventana_semiabierta(self, config, valid_tx, ctx):
        rule = make_rule(config, UnusualHourRule)
        inside = valid_tx(timestamp="2025-01-10T02:00:00Z", amount=6_000.0)
        outside = valid_tx(timestamp="2025-01-10T05:00:00Z", amount=6_000.0)
        assert rule.evaluate(inside, ctx) is not None   # 02:00 pertenece a la ventana
        assert rule.evaluate(outside, ctx) is None      # 05:00 ya queda fuera


# ------------------------------------------------------------------ RG-008
class TestSchemaRule:
    def test_esquema_completo_pasa(self, config, valid_tx, ctx):
        assert make_rule(config, SchemaRule).evaluate(valid_tx(), ctx) is None

    def test_campo_obligatorio_nulo_falla(self, config, valid_tx, ctx):
        violation = make_rule(config, SchemaRule).evaluate(valid_tx(account_id=None), ctx)
        assert violation is not None
        assert violation.severity == "CRITICA"
        assert "account_id" in violation.message

    def test_tipo_invalido_falla(self, config, valid_tx, ctx):
        rule = make_rule(config, SchemaRule)
        assert rule.evaluate(valid_tx(transaction_type="CRYPTO_SWAP"), ctx) is not None
        assert rule.evaluate(valid_tx(timestamp="ayer en la tarde"), ctx) is not None
        assert rule.evaluate(valid_tx(account_age_days=-3), ctx) is not None

    def test_opcionales_nulos_no_fallan(self, config, valid_tx, ctx):
        tx = valid_tx(country_code=None, merchant_category=None)
        assert make_rule(config, SchemaRule).evaluate(tx, ctx) is None
