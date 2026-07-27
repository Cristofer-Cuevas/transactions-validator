FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Por defecto ejecuta el batch completo sobre el dataset incluido.
# Para levantar la API REST:
#   docker run -p 8000:8000 data-engineer-test uvicorn api:app --host 0.0.0.0
CMD ["python", "batch_processor.py", "--input", "data/transactions.csv", "--output", "data/validation_results.csv"]
