FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias
COPY requirements_minimal.txt .
RUN pip install --no-cache-dir -r requirements_minimal.txt

# Copiar codigo da aplicacao
COPY src ./src
COPY data ./data
COPY web ./web

# Variaveis padrao (sobrescrever no App Runner)
ENV PYTHONUNBUFFERED=1
ENV API_HOST=0.0.0.0
ENV API_PORT=8080
ENV CORS_ORIGINS=*

# Porta que o App Runner espera
EXPOSE 8080

CMD ["python", "-m", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
