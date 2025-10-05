
# 📘 Fase de transformación

## 🎯 Objetivo
Transformar los datos brutos de mercado (Fase 1) en **señales cuantitativas útiles** para modelos de machine learning y estrategias de trading algorítmico.

---

## 🧩 Arquitectura General
- **Fuente**: Tablas RAW y complementarias (`crypto.raw_*`, `agg_trades_1m`, `orderbook_snapshot_1m`, `perp_metrics_1m`, `liquidations_stream`).  
- **Proceso**: `crypto_data_stg_layer` (ETL incremental en Python + SQLAlchemy).  
- **Destino**: Tabla consolidada `crypto.features_1m`.  
- **Ejecución**: Automatizable vía CronJob (1m o 5m) dentro del clúster Kubernetes (gestionado por ArgoCD).

---

## 🧠 Lógica del Proceso

1. **Lectura incremental:**
   - Detecta el último `ts` procesado en `features_1m`.
   - Trae nuevas filas desde `raw_btc_usdt_1m` más una **ventana de contexto (300 minutos)** para cálculos rolling (EMA, RSI…).

2. **Cálculo de indicadores técnicos (OHLCV):**
   | Indicador | Descripción | Columna |
   |------------|-------------|----------|
   | MA7 / MA21 | Medias móviles simples (7 y 21 minutos). | `ma7`, `ma21` |
   | EMA21 | Media móvil exponencial, suaviza tendencias. | `ema21` |
   | RSI(14) | Índice de fuerza relativa (0–100). | `rsi_14` |
   | MACD(12,26,9) | Cruce de medias exponenciales, mide momentum. | `macd_12_26`, `macd_signal_9`, `macd_hist` |
   | Bollinger(20,2) | Bandas de volatilidad (superior/inferior/anchura). | `bb_upper_20_2`, `bb_lower_20_2`, `bb_width_20_2` |
   | OBV | On-Balance Volume (volumen direccional). | `obv` |
   | Momentum | Ratio de cambio de precio (1m y 7m). | `momentum_1m`, `momentum_7m` |

3. **Indicadores de microestructura (nivel 2 del mercado):**
   | Fuente | Descripción | Columnas |
   |---------|-------------|-----------|
   | `agg_trades_1m` | Volumen y desequilibrio de trades agresivos. | `vwap_tick_1m`, `rv_tick_1m`, `trade_imb_1m` |
   | `orderbook_snapshot_1m` | Profundidad del libro y spreads. | `spread_bps`, `obi5`, `depth_bid5_delta`, `depth_ask5_delta` |

4. **Indicadores derivados (perpetual futures):**
   | Fuente | Descripción | Columnas |
   |---------|-------------|-----------|
   | `perp_metrics_1m` | Funding, basis y open interest (OI). | `funding_rate`, `basis_rel`, `oi` |
   | — | Cambio en OI (señal de aperturas/cierres de posiciones). | `oi_delta_1m` |

5. **Eventos de riesgo (liquidaciones):**
   | Fuente | Descripción | Columnas |
   |---------|-------------|-----------|
   | `liquidations_stream` | Agregado por minuto desde WS. | `liq_buy_qty_1m`, `liq_sell_qty_1m`, `liq_count_1m` |

6. **Inserción incremental:**
   - Inserta solo filas nuevas (ON CONFLICT DO NOTHING).
   - Totalmente idempotente y segura para ejecución frecuente.

---

## 🧾 Estructura Final: `crypto.features_1m`

| Categoría | Columna | Descripción |
|------------|----------|-------------|
| Temporal | `ts`, `symbol` | Timestamp (UTC) y par. |
| Precio y volatilidad | `close`, `ret_1m`, `ret_5m`, `rv_5m`, `rv_15m` | Precio y retornos logarítmicos. |
| Técnicos | `ma7`, `ma21`, `ema21`, `rsi_14`, `macd_12_26`, `macd_signal_9`, `macd_hist`, `bb_upper_20_2`, `bb_lower_20_2`, `bb_width_20_2`, `obv`, `momentum_1m`, `momentum_7m` | Indicadores clásicos de tendencia y momentum. |
| Microestructura | `vwap_tick_1m`, `rv_tick_1m`, `trade_imb_1m`, `spread_bps`, `obi5`, `depth_bid5_delta`, `depth_ask5_delta` | Señales derivadas de order flow. |
| Derivados | `funding_rate`, `basis_rel`, `oi`, `oi_delta_1m` | Variables de futuros perpetuos. |
| Riesgo / liquidaciones | `liq_buy_qty_1m`, `liq_sell_qty_1m`, `liq_count_1m` | Métricas agregadas de liquidaciones. |

---

## ✅ Estado final
- ✔️ ETL incremental consolidado en `features_1m`.
- ✔️ Limpieza y normalización de timestamps (UTC).
- ✔️ Cálculo completo de indicadores técnicos, microestructura y derivados.
- ✔️ Datos listos para exploración y entrenamiento ML.

---