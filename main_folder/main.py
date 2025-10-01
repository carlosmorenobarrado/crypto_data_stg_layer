import logging
import os
from datetime import timedelta

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- DB ---
DB_HOST = "192.168.1.47"
DB_NAME = "criptodb"
DB_USER = "admincar"
DB_PASSWORD = "1234car"
DB_PORT = "5432"

SCHEMA = "crypto"
RAW_TABLE = "raw_btc_usdt_1m"          # entrada
FEATURES_TABLE = "features_1m"         # salida
SYMBOL = "BTCUSDT"

# --- Conexión ---
db_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
engine = create_engine(db_url)
logging.info(f"Conexión a PostgreSQL establecida exitosamente con SQLAlchemy en {DB_HOST}.")

# ========= Indicadores =========
def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(series: pd.Series, n: int = 14) -> pd.Series:
    delta = series.diff()
    up = pd.Series(np.where(delta > 0, delta, 0.0), index=series.index)
    down = pd.Series(np.where(delta < 0, -delta, 0.0), index=series.index)
    roll_up = up.ewm(alpha=1/n, adjust=False).mean()
    roll_down = down.ewm(alpha=1/n, adjust=False).mean()
    rs = roll_up / (roll_down.replace(0, np.nan))
    return 100 - (100 / (1 + rs))


def macd(series: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

def bbands(series: pd.Series, n=20, k=2):
    ma = series.rolling(n).mean()
    sd = series.rolling(n).std(ddof=0)
    upper = ma + k * sd
    lower = ma - k * sd
    width = (upper - lower) / ma.replace(0, np.nan).abs()
    return upper, lower, width

def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    sign = np.sign(close.diff().fillna(0))
    return (sign * volume).fillna(0).cumsum()

# ========= DDL destino =========
def ensure_tables():
    with engine.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS {SCHEMA}'))
        conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {SCHEMA}.{FEATURES_TABLE} (
          ts                 timestamptz NOT NULL,
          symbol             text        NOT NULL,

          -- Precio/retornos/vol
          close              numeric,
          ret_1m             numeric,
          ret_5m             numeric,
          rv_5m              numeric,
          rv_15m             numeric,
          vwap_tick_1m       numeric,
          rv_tick_1m         numeric,

          -- Técnicos (tus cálculos incluidos)
          ma7                numeric,
          ma21               numeric,
          ema21              numeric,
          rsi_14             numeric,
          macd_12_26         numeric,
          macd_signal_9      numeric,
          macd_hist          numeric,
          bb_upper_20_2      numeric,
          bb_lower_20_2      numeric,
          bb_width_20_2      numeric,
          obv                numeric,
          momentum_1m        numeric,
          momentum_7m        numeric,

          -- Microestructura
          spread_bps         numeric,
          obi5               numeric,
          depth_bid5_delta   numeric,
          depth_ask5_delta   numeric,
          trade_imb_1m       numeric,

          -- Derivados / perps
          funding_rate       numeric,
          basis_rel          numeric,
          oi                 numeric,
          oi_delta_1m        numeric,

          -- Liquidaciones (stream -> agregado 1m)
          liq_buy_qty_1m     numeric,
          liq_sell_qty_1m    numeric,
          liq_count_1m       integer,

          PRIMARY KEY (ts, symbol)
        );
        """))

# ========= Incremental =========
def get_last_ts_processed(symbol: str):
    q = f"""SELECT MAX(ts) FROM {SCHEMA}.{FEATURES_TABLE} WHERE symbol=:s"""
    with engine.connect() as conn:
        return conn.execute(text(q), {"s": symbol}).scalar()

def load_raw_with_context(last_ts, symbol: str) -> pd.DataFrame:
    if last_ts:
        ctx_from = last_ts - timedelta(minutes=300)
        q = f"""
        SELECT
          "Open_time" AS ts,
          CAST("Close" AS DOUBLE PRECISION)  AS close,
          CAST("Volume" AS DOUBLE PRECISION) AS volume
        FROM {SCHEMA}.{RAW_TABLE}
        WHERE "Open_time" >= :from_ts
        ORDER BY "Open_time"
        """
        params = {"from_ts": ctx_from}
        logging.info(f"Leyendo RAW desde {ctx_from} (con contexto)")
    else:
        q = f"""
        SELECT
          "Open_time" AS ts,
          CAST("Close" AS DOUBLE PRECISION)  AS close,
          CAST("Volume" AS DOUBLE PRECISION) AS volume
        FROM {SCHEMA}.{RAW_TABLE}
        ORDER BY "Open_time"
        """
        params = {}
        logging.info("Leyendo RAW completo (primera ejecución)")

    df = pd.read_sql_query(text(q), engine, params=params, parse_dates=["ts"])
    df["symbol"] = symbol
    return df

# ========= Técnicos (incluye tus cálculos) =========
def compute_technicals(df_ohlcv: pd.DataFrame) -> pd.DataFrame:
    df = df_ohlcv.sort_values("ts").copy()

    # Retornos log e intraperiodo
    df["log_ret"] = np.log(df["close"] / df["close"].shift(1))
    df["ret_1m"]  = df["log_ret"]
    df["ret_5m"]  = df["log_ret"].rolling(5).sum()
    df["rv_5m"]   = df["log_ret"].rolling(5).std()
    df["rv_15m"]  = df["log_ret"].rolling(15).std()

    # Tus MAs (corregidas a pandas moderno)
    df["ma7"]     = df["close"].rolling(7).mean()
    df["ma21"]    = df["close"].rolling(21).mean()

    # EMA “útil” (sustituimos com=0.5 por EMA21)
    df["ema21"]   = ema(df["close"], 21)

    # MACD (12/26/9)
    macd_line, signal, hist = macd(df["close"], 12, 26, 9)
    df["macd_12_26"]   = macd_line
    df["macd_signal_9"]= signal
    df["macd_hist"]    = hist

    # Bollinger 20,2
    upper, lower, width = bbands(df["close"], 20, 2)
    df["bb_upper_20_2"] = upper
    df["bb_lower_20_2"] = lower
    df["bb_width_20_2"] = width

    # RSI y OBV
    df["rsi_14"] = rsi(df["close"], 14)
    df["obv"]    = obv(df["close"], df["volume"])

    # Momentum correcto (rate of change)
    df["momentum_1m"] = df["close"].pct_change(1)
    df["momentum_7m"] = df["close"].pct_change(7)

    keep = [
        "ts","symbol","close","ret_1m","ret_5m","rv_5m","rv_15m",
        "ma7","ma21","ema21",
        "rsi_14","macd_12_26","macd_signal_9","macd_hist",
        "bb_upper_20_2","bb_lower_20_2","bb_width_20_2","obv",
        "momentum_1m","momentum_7m"
    ]
    return df[keep]

# ========= Joins =========
def join_agg_trades(features_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if features_df.empty: return features_df
    tmin, tmax = features_df["ts"].min(), features_df["ts"].max()
    q = f"""
    SELECT
      ts_window_start AS ts,
      symbol,
      CAST(vwap_tick AS DOUBLE PRECISION) AS vwap_tick_1m,
      CAST(rv_tick AS DOUBLE PRECISION)   AS rv_tick_1m,
      CASE WHEN total_vol>0
           THEN (buy_vol - sell_vol)/total_vol
           ELSE NULL END                  AS trade_imb_1m
    FROM {SCHEMA}.agg_trades_1m
    WHERE symbol=:s AND ts_window_start BETWEEN :tmin AND :tmax
    """
    agg = pd.read_sql_query(text(q), engine, params={"s": symbol, "tmin": tmin, "tmax": tmax}, parse_dates=["ts"])
    return features_df.merge(agg, on=["ts","symbol"], how="left")

def join_orderbook(features_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if features_df.empty: return features_df
    tmin, tmax = features_df["ts"].min(), features_df["ts"].max()
    q = f"""
    SELECT
      ts,
      symbol,
      CAST(spread_bps AS DOUBLE PRECISION)         AS spread_bps,
      CAST(obi5 AS DOUBLE PRECISION)               AS obi5,
      CAST(bid_qty_top5_delta AS DOUBLE PRECISION) AS depth_bid5_delta,
      CAST(ask_qty_top5_delta AS DOUBLE PRECISION) AS depth_ask5_delta
    FROM {SCHEMA}.orderbook_snapshot_1m
    WHERE symbol=:s AND ts BETWEEN :tmin AND :tmax
    """
    ob = pd.read_sql_query(text(q), engine, params={"s": symbol, "tmin": tmin, "tmax": tmax}, parse_dates=["ts"])
    return features_df.merge(ob, on=["ts","symbol"], how="left")

def join_perp_metrics(features_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if features_df.empty: return features_df
    tmin, tmax = features_df["ts"].min(), features_df["ts"].max()
    q = f"""
    SELECT
      ts,
      symbol,
      CAST(funding_rate AS DOUBLE PRECISION)   AS funding_rate,
      CAST(basis_rel AS DOUBLE PRECISION)      AS basis_rel,
      CAST(open_interest AS DOUBLE PRECISION)  AS oi
    FROM {SCHEMA}.perp_metrics_1m
    WHERE symbol=:s AND ts BETWEEN :tmin AND :tmax
    """
    pm = pd.read_sql_query(text(q), engine, params={"s": symbol, "tmin": tmin, "tmax": tmax}, parse_dates=["ts"])
    df = features_df.merge(pm, on=["ts","symbol"], how="left").sort_values(["symbol","ts"])
    df["oi_delta_1m"] = df.groupby("symbol")["oi"].diff()
    return df

def join_liquidations_agg(features_df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if features_df.empty: return features_df
    tmin, tmax = features_df["ts"].min(), features_df["ts"].max()
    q = f"""
    WITH liq AS (
      SELECT date_trunc('minute', event_time) AS ts,
             symbol,
             SUM(CASE WHEN side='BUY'  THEN COALESCE(orig_qty,0) ELSE 0 END) AS liq_buy_qty_1m,
             SUM(CASE WHEN side='SELL' THEN COALESCE(orig_qty,0) ELSE 0 END) AS liq_sell_qty_1m,
             COUNT(*) AS liq_count_1m
      FROM {SCHEMA}.liquidations_stream
      WHERE symbol=:s AND event_time >= :tmin AND event_time < :tmax + interval '1 minute'
      GROUP BY 1,2
    )
    SELECT * FROM liq WHERE ts BETWEEN :tmin AND :tmax
    """
    liq = pd.read_sql_query(text(q), engine, params={"s": symbol, "tmin": tmin, "tmax": tmax}, parse_dates=["ts"])
    return features_df.merge(liq, on=["ts","symbol"], how="left")

# ========= Inserción =========
def insert_new_features(df_all: pd.DataFrame, last_ts, symbol: str):
    if df_all.empty:
        logging.info("No hay features calculadas.")
        return
    df_ins = df_all[df_all["ts"] > last_ts] if last_ts is not None else df_all.copy()
    if df_ins.empty:
        logging.info("No hay filas nuevas para insertar en features_1m.")
        return

    cols = [
        "ts","symbol","close","ret_1m","ret_5m","rv_5m","rv_15m",
        "vwap_tick_1m","rv_tick_1m",
        "ma7","ma21","ema21","rsi_14","macd_12_26","macd_signal_9","macd_hist",
        "bb_upper_20_2","bb_lower_20_2","bb_width_20_2","obv","momentum_1m","momentum_7m",
        "spread_bps","obi5","depth_bid5_delta","depth_ask5_delta","trade_imb_1m",
        "funding_rate","basis_rel","oi","oi_delta_1m",
        "liq_buy_qty_1m","liq_sell_qty_1m","liq_count_1m"
    ]
    with engine.begin() as conn:
        tmp = "_tmp_features_1m"
        df_ins[cols].to_sql(tmp, con=conn, schema=SCHEMA, if_exists="replace", index=False)
        conn.execute(text(f"""
        INSERT INTO {SCHEMA}.{FEATURES_TABLE}
        ({", ".join(cols)})
        SELECT {", ".join(cols)} FROM {SCHEMA}.{tmp}
        ON CONFLICT (ts, symbol) DO NOTHING;
        """))
        conn.execute(text(f"DROP TABLE {SCHEMA}.{tmp}"))
    logging.info(f"Insertadas {len(df_ins)} filas nuevas en {SCHEMA}.{FEATURES_TABLE} ({symbol}).")

# ========= MAIN =========
def main():
    ensure_tables()
    last_ts = get_last_ts_processed(SYMBOL)
    if last_ts:
        logging.info(f"Último ts en {SCHEMA}.{FEATURES_TABLE} para {SYMBOL}: {last_ts}")
    else:
        logging.info(f"Sin registros previos en {SCHEMA}.{FEATURES_TABLE} para {SYMBOL}.")

    df_raw = load_raw_with_context(last_ts, SYMBOL)
    if df_raw.empty:
        logging.info("RAW vacío, nada que hacer.")
        return

    df_feat = compute_technicals(df_raw)
    df_feat = join_agg_trades(df_feat, SYMBOL)
    df_feat = join_orderbook(df_feat, SYMBOL)
    df_feat = join_perp_metrics(df_feat, SYMBOL)
    df_feat = join_liquidations_agg(df_feat, SYMBOL)

    insert_new_features(df_feat, last_ts, SYMBOL)
    logging.info("ETL de features_1m finalizado correctamente.")

if __name__ == "__main__":
    main()
