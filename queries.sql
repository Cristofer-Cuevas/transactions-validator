-- ============================================================================
-- Tarea 4 · Queries de reporte sobre la tabla validation_results
-- Dialecto: DuckDB (notas de portabilidad a PostgreSQL donde aplica).
--
-- Carga de la tabla en DuckDB (el cast garantiza timestamp comparable):
--
--   CREATE OR REPLACE TABLE validation_results AS
--   SELECT * REPLACE (CAST(timestamp AS TIMESTAMP) AS timestamp)
--   FROM read_csv_auto('data/validation_results.csv');
--
-- Nota sobre ventanas temporales: el dataset es histórico (enero 2025), por lo
-- que "últimos 7 días" y "últimas 24 horas" se anclan al MAX(timestamp) de la
-- tabla para que las queries sean determinísticas y verificables. En
-- producción el ancla sería NOW().
-- ============================================================================


-- ----------------------------------------------------------------------------
-- Q1 · Top 10 cuentas con mayor monto total rechazado en los últimos 7 días
-- ----------------------------------------------------------------------------
WITH ref AS (
    SELECT MAX(timestamp) AS max_ts
    FROM validation_results
)
SELECT
    vr.account_id,
    COUNT(*)                        AS rejected_tx,
    ROUND(SUM(vr.amount), 2)        AS total_rejected_usd,
    ROUND(AVG(vr.amount), 2)        AS avg_rejected_usd
FROM validation_results AS vr
CROSS JOIN ref
WHERE vr.validation_status = 'REJECTED'
  AND vr.timestamp >= ref.max_ts - INTERVAL 7 DAY   -- PostgreSQL: INTERVAL '7 days'
GROUP BY vr.account_id
ORDER BY total_rejected_usd DESC
LIMIT 10;


-- ----------------------------------------------------------------------------
-- Q2 · Tasa de rechazo (%) por transaction_type y merchant_category
--      Versión tabla pivote nativa de DuckDB: tipos como filas,
--      categorías como columnas.
-- ----------------------------------------------------------------------------
PIVOT (
    SELECT
        transaction_type,
        COALESCE(merchant_category, '(sin categoria)') AS merchant_category,
        CASE WHEN validation_status = 'REJECTED' THEN 1.0 ELSE 0.0 END AS is_rejected
    FROM validation_results
)
ON merchant_category
USING ROUND(AVG(is_rejected) * 100, 1)
GROUP BY transaction_type
ORDER BY transaction_type;

-- Variante portable (PostgreSQL/SQLite) en formato largo, con volumen para
-- dar contexto a la tasa:
--
-- SELECT
--     transaction_type,
--     COALESCE(merchant_category, '(sin categoria)')                AS merchant_category,
--     COUNT(*)                                                      AS total_tx,
--     ROUND(AVG(CASE WHEN validation_status = 'REJECTED'
--                    THEN 1.0 ELSE 0.0 END) * 100, 1)               AS rejection_rate_pct
-- FROM validation_results
-- GROUP BY transaction_type, COALESCE(merchant_category, '(sin categoria)')
-- ORDER BY transaction_type, rejection_rate_pct DESC;


-- ----------------------------------------------------------------------------
-- Q3 · Regla más frecuente por país (window function: RANK)
--      violated_rules viene como lista separada por '|'; se explota a una
--      fila por (transacción, regla) y se rankea dentro de cada país.
--      RANK() conserva empates (dos reglas co-líderes aparecen ambas).
-- ----------------------------------------------------------------------------
WITH exploded AS (
    SELECT
        country_code,
        UNNEST(string_split(violated_rules, '|')) AS rule_id
        -- PostgreSQL: UNNEST(string_to_array(violated_rules, '|'))
    FROM validation_results
    WHERE violated_rules IS NOT NULL
      AND violated_rules <> ''
      AND country_code IS NOT NULL
),
rule_counts AS (
    SELECT
        country_code,
        rule_id,
        COUNT(*) AS violations
    FROM exploded
    GROUP BY country_code, rule_id
),
ranked AS (
    SELECT
        country_code,
        rule_id,
        violations,
        RANK() OVER (
            PARTITION BY country_code
            ORDER BY violations DESC
        ) AS rule_rank
    FROM rule_counts
)
SELECT
    country_code,
    rule_id  AS most_frequent_rule,
    violations
FROM ranked
WHERE rule_rank = 1
ORDER BY country_code;


-- ----------------------------------------------------------------------------
-- Q4 · Alerta: cuentas con más de 3 transacciones REVIEW en las últimas 24 h
--
-- Sobre este dataset la alerta (correctamente) no dispara: el máximo de
-- REVIEWs por cuenta en la última ventana de 24 h es 1. Para verificar la
-- mecánica de la query se puede bajar temporalmente el HAVING a COUNT(*) > 0.
-- ----------------------------------------------------------------------------
WITH ref AS (
    SELECT MAX(timestamp) AS max_ts
    FROM validation_results
)
SELECT
    vr.account_id,
    COUNT(*)              AS review_tx_24h,
    MIN(vr.timestamp)     AS first_review,
    MAX(vr.timestamp)     AS last_review,
    ROUND(SUM(vr.amount), 2) AS total_amount_usd
FROM validation_results AS vr
CROSS JOIN ref
WHERE vr.validation_status = 'REVIEW'
  AND vr.timestamp >= ref.max_ts - INTERVAL 24 HOUR  -- PostgreSQL: INTERVAL '24 hours'
GROUP BY vr.account_id
HAVING COUNT(*) > 3
ORDER BY review_tx_24h DESC, total_amount_usd DESC;
