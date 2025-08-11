# Usa una imagen base de Python ligera
FROM python:3.9

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

COPY requirements.txt .

# Instala las dependencias desde el archivo en /app
RUN pip install -r requirements.txt 

COPY main.py .
RUN ls -l /app
CMD ["python", "main.py"]