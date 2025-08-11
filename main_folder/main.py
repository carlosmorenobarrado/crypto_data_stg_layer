import logging
import psycopg2
import os
from binance import Client
import pandas as pd
from sqlalchemy import create_engine

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


##TU CÓDIGO AQUÍ