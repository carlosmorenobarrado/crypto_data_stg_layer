import logging
import psycopg2
import os
from binance import Client
import pandas as pd
from sqlalchemy import create_engine, text

# --- Configuración de Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

DB_HOST = "192.168.1.49"
DB_NAME = "criptodb"
DB_USER = "admincar"
DB_PASSWORD = "1234car"
DB_PORT = "5432"
SSL_MODE = 'require' 

# Crear el "motor" de SQLAlchemy para conectar con la base de datos
try:
    db_url = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    engine = create_engine(db_url)
    logging.info(f"Conexión a PostgreSQL establecida exitosamente con SQLAlchemy en {DB_HOST}.")
except Exception as e:
    logging.error(f"Error al crear el motor de SQLAlchemy: {e}")
    exit() # Salimos si no podemos conectar


def get_technical_indicators(dataset):
    # Create 7 and 21 days Moving Average
    dataset['ma7'] = dataset['price'].rolling(window=7).mean()
    dataset['ma21'] = dataset['price'].rolling(window=21).mean()
    
    # Create MACD
    dataset['26ema'] = pd.ewma(dataset['price'], span=26)
    dataset['12ema'] = pd.ewma(dataset['price'], span=12)
    dataset['MACD'] = (dataset['12ema']-dataset['26ema'])

    # Create Bollinger Bands
    dataset['20sd'] = pd.stats.moments.rolling_std(dataset['price'],20)
    dataset['upper_band'] = dataset['ma21'] + (dataset['20sd']*2)
    dataset['lower_band'] = dataset['ma21'] - (dataset['20sd']*2)
    
    # Create Exponential moving average
    dataset['ema'] = dataset['price'].ewm(com=0.5).mean()
    
    # Create Momentum
    dataset['momentum'] = dataset['price']-1
    
    return dataset


tabla_raw = 'raw_btc_usdt_1m'
schema = 'crypto'
tabla_stg = 'stg_btc_usdt_1m'

# !! IMPORTANTE: Cambia 'open_time' por el nombre real de tu columna de timestamp !!
columna_timestamp = 'Open_time'

# --- Proceso Principal Modificado ---
def main():
    # 1. OBTENER LA MARCA DE AGUA (ÚLTIMO TIMESTAMP PROCESADO)
    ultimo_timestamp_procesado = None
    try:
        # Consulta para obtener el valor máximo de la columna de tiempo en la tabla STG
        query_max_time = f"SELECT MAX({columna_timestamp}) FROM {schema}.{tabla_stg}"
        with engine.connect() as connection:
            result = connection.execute(text(query_max_time)).scalar()
            if result:
                ultimo_timestamp_procesado = result
                logging.info(f"Último timestamp encontrado en '{tabla_stg}': {ultimo_timestamp_procesado}")
            else:
                logging.info(f"La tabla '{tabla_stg}' está vacía. Se procesarán todos los datos.")
    except Exception as e:
        # Si la tabla STG no existe, procesaremos todo.
        logging.warning(f"No se pudo obtener el último timestamp (quizás la tabla no existe aún). Se procesarán todos los datos. Error: {e}")

    # 2. LEER SOLO LOS DATOS NUEVOS DE LA TABLA RAW
    if ultimo_timestamp_procesado:
        # Si ya hay datos, leemos solo los que son más nuevos
        query_nuevos_datos = f"SELECT * FROM {schema}.{tabla_raw} WHERE {columna_timestamp} > :last_time ORDER BY {columna_timestamp}"
        df_raw = pd.read_sql_query(query_nuevos_datos, engine, params={'last_time': ultimo_timestamp_procesado})
    else:
        # Si no hay datos, leemos la tabla completa (solo la primera vez)
        query_nuevos_datos = f"SELECT * FROM {schema}.{tabla_raw} ORDER BY {columna_timestamp}"
        df_raw = pd.read_sql_query(query_nuevos_datos, engine)

    if df_raw.empty:
        logging.info("No hay datos nuevos para procesar.")
        return

    logging.info(f"Se encontraron {len(df_raw)} nuevas filas para procesar.")

    # 3. PROCESAR los datos nuevos
    logging.info("Calculando indicadores técnicos para los nuevos datos...")
    df_stg = get_technical_indicators(df_raw)

    # 4. AÑADIR (APPEND) los nuevos datos a la tabla STG
    logging.info(f"Añadiendo nuevos datos a la tabla '{schema}.{tabla_stg}'...")
    try:
        df_stg.to_sql(
            name=tabla_stg,
            con=engine,
            schema=schema,
            if_exists='append', # <-- La clave está aquí: AÑADIR en vez de reemplazar
            index=False
        )
        logging.info("¡Proceso completado! Los nuevos datos han sido añadidos a la tabla de staging.")
    except Exception as e:
        logging.error(f"No se pudo añadir datos a la tabla de staging. Error: {e}")

if __name__ == "__main__":
    main()