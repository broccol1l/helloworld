FROM python:3.12-slim

# Системные зависимости для Postgres
RUN apt-get update && apt-get install -y \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем только нужные файлы
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Создаем папку для отчетов, если забыли
RUN mkdir -p temp

CMD ["python", "main.py"]