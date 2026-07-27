# Motor de Validación de Transacciones · Prueba Técnica Data Engineer

Motor de reglas de negocio para un banco digital: valida transacciones entrantes contra 8 reglas de cumplimiento, procesa el dataset histórico completo por lotes, y expone métricas analíticas y queries de reporte sobre los resultados.

## Estructura del repositorio

```
data-engineer-test/
├── validator.py            # Tarea 1 · Motor de reglas (CLI incluido)
├── rules/                  # Reglas individuales, una por archivo
│   ├── base_rule.py        #   Contrato BaseRule + Violation + ValidationContext
│   ├── utils.py            #   Coerción segura de tipos (CSV/JSON crudo)
│   ├── amount_rule.py      #   RG-001 · CRÍTICA
│   ├── daily_limit_rule.py #   RG-002 · ALTA
│   ├── frequency_rule.py   #   RG-003 · ALTA
│   ├── currency_rule.py    #   RG-004 · CRÍTICA
│   ├── country_risk_rule.py#   RG-005 · MEDIA  → REVIEW
│   ├── funds_rule.py       #   RG-006 · CRÍTICA
│   ├── unusual_hour_rule.py#   RG-007 · BAJA   → REVIEW
│   └── schema_rule.py      #   RG-008 · CRÍTICA
├── batch_processor.py      # Tarea 2 · Validación por lotes (+ paralelización opcional)
├── analysis.ipynb          # Tarea 3 · EDA ejecutado, 9 visualizaciones + hallazgos
├── queries.sql             # Tarea 4 · 4 queries (DuckDB, con notas de portabilidad)
├── config/
│   └── rules_config.yaml   # Configuración externalizada (límites, listas, campos)
├── data/
│   ├── transactions.csv        # Dataset proporcionado (10,000 registros)
│   └── validation_results.csv  # Salida generada por batch_processor.py
├── tests/                  # 48 tests (pytest): por regla + integración del motor
├── examples/               # Transacciones JSON de ejemplo para el CLI y la API
├── api.py                  # Bonus · API REST mínima (FastAPI)
├── Dockerfile              # Bonus · Contenedorización
└── requirements.txt
```

## Cómo ejecutar

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

**Tarea 1 · Validar una transacción individual**

```bash
python validator.py --file examples/tx_valid.json --pretty
python validator.py --file examples/tx_invalid.json --pretty
python validator.py --json '{"transaction_id": "t1", "amount": -5}' --pretty
# El acumulado diario de la cuenta puede inyectarse para RG-002:
python validator.py --file examples/tx_valid.json --accumulated 52400 --pretty
```

**Tarea 2 · Batch completo**

```bash
python batch_processor.py --input data/transactions.csv --output data/validation_results.csv
python batch_processor.py --workers 4        # variante paralelizada
```

**Tests**

```bash
python -m pytest tests/ -v
```

**Tarea 3 · Notebook** (requiere haber corrido el batch primero)

```bash
jupyter notebook analysis.ipynb
```

**Tarea 4 · SQL** (DuckDB)

```bash
duckdb -c "CREATE TABLE validation_results AS SELECT * REPLACE (CAST(timestamp AS TIMESTAMP) AS timestamp) FROM read_csv_auto('data/validation_results.csv');" -c ".read queries.sql"
```

**Bonus · API REST y Docker**

```bash
uvicorn api:app --reload
curl -X POST localhost:8000/validate -H 'Content-Type: application/json' -d @examples/tx_invalid.json

docker build -t data-engineer-test .
docker run data-engineer-test                                        # batch
docker run -p 8000:8000 data-engineer-test uvicorn api:app --host 0.0.0.0   # API
```

## Decisiones de arquitectura

### Patrón: Chain of Responsibility con reglas tipo Strategy

Cada regla es una clase independiente que implementa el contrato `BaseRule.evaluate(tx, ctx) -> Violation | None` (las reglas son estrategias intercambiables). El encadenamiento, el orden y el cortocircuito no viven en las reglas sino en el orquestador `TransactionValidator`, que recorre `RULE_REGISTRY` como una cadena. Agregar una regla nueva = crear la clase + registrarla en la lista + parametrizarla en el YAML; ninguna regla conoce a las demás.

Se descartó el encadenamiento clásico "cada handler llama al siguiente" porque acopla el orden dentro de las reglas y complica reportar *todas* las violaciones acumuladas (requisito explícito de la prueba).

### Orden de evaluación y semántica del cortocircuito

Las reglas se evalúan en **orden ascendente de ID** y la **primera violación CRÍTICA corta la cadena** (las violaciones ya acumuladas sí se reportan, y `rules_evaluated` refleja cuántas se alcanzaron). Esto reproduce exactamente el ejemplo de la prueba: una transacción que solo viola RG-002 (ALTA) termina `REJECTED` con `rules_evaluated: 8`, porque las severidades ALTA/MEDIA/BAJA no cortan.

Consecuencia deliberada: un registro con `amount = null` corta en RG-001 y nunca llega a RG-008. Cada regla es dueña de su dominio (RG-001 gobierna el monto, RG-008 el resto del esquema) y las reglas intermedias con insumos faltantes se abstienen en lugar de duplicar el diagnóstico.

### Consolidación del estado

Las reglas declaran una **acción** además de su severidad: RG-005 y RG-007 marcan `REVIEW` (no rechazan, tal como exige la prueba), el resto rechaza. La consolidación es: cualquier violación de acción REJECT → `REJECTED`; solo violaciones REVIEW → `REVIEW`; sin violaciones → `APPROVED`. Separar severidad (criticidad para cumplimiento + cortocircuito) de acción (efecto sobre el estado) evita el error de inferir "MEDIA/BAJA = revisar", que es una casualidad de estas 8 reglas y no una ley.

### RG-002 y el problema del estado: `ValidationContext`

El límite diario acumulado es la única regla que necesita información que la transacción no trae. En lugar de darle al motor acceso a una base de datos (acoplamiento) o de recalcular por transacción (O(n²)), el motor recibe un `ValidationContext` con el acumulado ya resuelto:

* **En batch:** `batch_processor` lo pre-calcula vectorizado con una suma acumulada por `(account_id, día UTC)` ordenada por timestamp, **incluyendo la transacción actual** (interpretación: la transacción que hace superar el límite es la primera rechazada). Montos nulos/negativos aportan 0 al acumulado — son inválidos por RG-001 y no deben contaminar el límite del resto de la cuenta.
* **En modo unitario / API:** el acumulado se inyecta opcionalmente (`--accumulated`, query param); si no está disponible, RG-002 usa el monto propio como mejor aproximación. En producción este contexto vendría de un store de agregados en línea (p. ej. Redis por cuenta+día).

### Manejo de nulos y datos malformados (tres capas)

1. **Coerción segura** (`rules/utils.py`): `safe_float/safe_int/safe_str/parse_utc_timestamp` normalizan NaN de pandas, strings numéricos y tipos absurdos sin lanzar excepciones.
2. **Abstención por regla:** una regla sin insumos suficientes se abstiene y deja el diagnóstico a la regla dueña del campo (RG-001 para monto, RG-008 para esquema). Excepción deliberada y documentada: RG-006 **rechaza** un débito sin `balance_before` — un core bancario no autoriza débitos sin poder verificar fondos.
3. **Última barrera:** el batch envuelve cada registro en try/except y degrada a status `ERROR` sin detener el lote; el motor además aísla excepciones de reglas individuales. En el dataset real: 0 errores.

Campos obligatorios vs opcionales: el dataset trae nulos intencionales en `country_code` y `merchant_category`, que se declararon opcionales en `required_fields` (configurable). Por eso RG-008 no dispara en este lote — su comportamiento está garantizado por tests.

### Configuración externalizada

Todos los umbrales, catálogos y listas viven en `config/rules_config.yaml`: límite diario, máximo de transacciones, monedas aprobadas, países de riesgo, ventana horaria, campos requeridos, y un flag `enabled` por regla. La ruta se puede sobreescribir con la variable de entorno `RULES_CONFIG_PATH` o con `--config`, lo que permite un YAML distinto por ambiente sin tocar código.

### Pandas vs Polars

Se eligió **pandas** por ser el estándar del ecosistema y suficiente para 10k filas (batch completo: ~0.6 s). El único cómputo pesado (acumulado diario) ya es vectorizado. Polars aportaría en el orden de millones de filas vía lazy evaluation y paralelismo nativo; con la arquitectura actual el cambio estaría contenido en `compute_daily_accumulated` y la E/S del batch.

### Paralelización (`--workers N`)

Implementada con `ProcessPoolExecutor` repartiendo el lote en chunks (el pre-cálculo del acumulado se hace antes de partir, así cada chunk es independiente). Trade-off honesto: para 10k filas el overhead de serializar procesos hace que el modo secuencial sea igual o más rápido; el flag demuestra el patrón de escalamiento para volúmenes donde sí paga (cientos de miles de filas o reglas costosas por I/O).

### Ancla temporal en SQL

"Últimos 7 días" y "últimas 24 horas" se anclan a `MAX(timestamp)` de la tabla para que las queries sean determinísticas sobre un dataset histórico (enero 2025). En producción el ancla sería `NOW()`. Q4 (alerta de REVIEWs) correctamente no dispara en este dataset: el máximo de REVIEWs por cuenta en 24 h es 1.

## Resultados sobre el dataset (resumen del batch)

| Métrica | Valor |
|---|---|
| Total procesado | 10,000 |
| Aprobadas | 2,119 (21.2%) |
| Rechazadas | 7,474 (74.7%) |
| En revisión | 407 (4.1%) |
| Errores | 0 |
| Tiempo | ~0.6 s |

Violaciones por regla: RG-002: 6,965 · RG-006: 1,182 · RG-007: 1,132 · RG-003: 459 · RG-004: 421 · RG-005: 324 · RG-001: 49 · RG-008: 0.

Motor vs `is_flagged`: precision 0.049 · recall 0.757 · F1 0.092 (definición estricta). La lectura completa — por qué la precisión coincide con la tasa base de fraude, la descalibración de RG-002 frente a la distribución de montos, y la cohorte países-de-riesgo ∩ cuentas-nuevas — está en la sección de hallazgos de `analysis.ipynb`.

## Mejoras futuras

* Store de agregados en línea (Redis) para alimentar el `ValidationContext` de RG-002 en tiempo real.
* Score supervisado de fraude entrenado con `is_flagged`, complementando (no reemplazando) las reglas determinísticas.
* Métricas Prometheus del batch/API (tasa de rechazo por regla como señal de salud).
* Versionado del YAML de reglas con auditoría de cambios (quién movió qué umbral y cuándo).
