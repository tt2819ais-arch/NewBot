FROM python:3.11-slim

WORKDIR /app

# Устанавливаем зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем Python зависимости
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Создаем пустой файл imghdr.py
RUN touch imghdr.py

# Копируем код
COPY . .

# Запускаем
CMD ["python", "main.py"]
