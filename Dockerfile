FROM python:3.11-slim

WORKDIR /app

# Добавляем нужные системные пакеты для сборки psycopg2
RUN apt-get update && apt-get install -y gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["sleep", "999999"]  # переопределяется в docker-compose
